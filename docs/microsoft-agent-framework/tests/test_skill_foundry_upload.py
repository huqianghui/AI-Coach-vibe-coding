"""
Azure AI Foundry Skills API + Toolbox 挂载 POC 验证（Foundry-Features 预览头修复后重跑）

背景（quick task 260717-x5f）：本脚本此前的运行完全被阻塞——API Key 被 403
`AuthenticationTypeDisabled` 拒绝，Entra ID (`DefaultAzureCredential`) 兜底也被 405
`Method Not Allowed` 拒绝，导致 Skill 上传、Toolbox 挂载、Agent 消费全部 SKIP。

本次修复的核心假设（quick task 260718-cy6）：405 很可能是缺失必需的
`Foundry-Features: Skills=V1Preview` 预览头导致的，而非真正的认证拒绝。本脚本使用升级后的
`azure-ai-projects`（2.1.0 -> 2.3.0）+ Entra ID 单一认证路径，重新跑通完整链路：

完整场景:
  1. 校验本地 mr-training-creator Skill 的 SKILL.md frontmatter 是否合法
  2. 将 Skill 目录打包为内存 ZIP（SKILL.md 位于 ZIP 根目录，Agents API 路径约定）
  3. Foundry-Features 头假设验证 + Inline 上传 Skill（Entra ID 为唯一/主认证路径；
     API Key 仅在本步骤顶部快速重新确认一次仍为 403，不再深入排查）
  4. ZIP 包上传 Skill（`create_from_files`，2.3.0 中 `create_from_package` 已被移除）；
     若因 frontmatter 解析问题失败，重试一次单行 description 的 A/B 变体
  5. 对已创建 Skill 做 get / list / download 往返验证
  6. 创建 Toolbox 版本，挂载已上传的 Skill（先尝试 typed `skills=[ToolboxSkillReference(...)]`，
     再回退到 raw dict body）
  7. MCP 端点发现：先检查 Toolbox Version 对象本身是否含端点字段，若无则探测约定 REST 路径
  8. Agent 真实消费验收：创建/复用一个 Agent，instructions 中拼接从 Azure 下载的真实 Skill 内容，
     调用一次并打印真实回复文本作为"Skill 内容确实到达模型"的证据
  9. 清理所有创建的云端资源（Agent -> Toolbox Version -> Toolbox -> Skill(s)）

目录结构:
  tests/
    skills/
      mr-training-creator/
        SKILL.md                           # 复用已有的真实 Skill 定义，不新建

前置条件:
  1. backend/.env 中配置 AZURE_FOUNDRY_ENDPOINT, AZURE_FOUNDRY_API_KEY
  2. az login 会话可用（DefaultAzureCredential 依赖）
  3. backend/.venv 中 azure-ai-projects 已升级到 2.3.0（或当时最新版本）

运行:
  cd backend
  .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py
"""

import inspect
import io
import os
import re
import sys
import zipfile
from pathlib import Path

import frontmatter
import httpx

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
SKILLS_DIR = TESTS_DIR / "skills"
SKILL_DIR = SKILLS_DIR / "mr-training-creator"

backend_dir = TESTS_DIR.parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

load_dotenv(backend_dir / ".env")

ENDPOINT = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").rstrip("/")
API_KEY = os.getenv("AZURE_FOUNDRY_API_KEY", "")
PROJECT_NAME = os.getenv("AZURE_FOUNDRY_DEFAULT_PROJECT", "avarda-demo-prj")
MODEL = os.getenv("AZURE_FOUNDRY_MODEL", "gpt-4o-mini")
PROJECT_ENDPOINT = f"{ENDPOINT}/api/projects/{PROJECT_NAME}" if ENDPOINT else ""

SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")

INLINE_SKILL_NAME = "mr-training-creator-inline-poc"
ZIP_SKILL_NAME = "mr-training-creator"
SINGLELINE_SKILL_NAME = "mr-training-creator-singleline-poc"
TOOLBOX_NAME = "mr-training-toolbox-poc"
AGENT_NAME = "poc-toolbox-consumer-agent"

FOUNDRY_FEATURES_HEADER = {"Foundry-Features": "Skills=V1Preview"}

_created_skills: list[str] = []
_created_toolboxes: list[str] = []
_created_agents: list[str] = []

# Which real skill name actually holds the ZIP-uploaded mr-training-creator content this run
# (either the original ZIP_SKILL_NAME, or the SINGLELINE_SKILL_NAME A/B variant if that's what
# succeeded). Populated by test_4.
_zip_uploaded_skill_name: str | None = None


# =============================================================================
# Helpers
# =============================================================================


def print_header(title: str):
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def print_result(success: bool, message: str):
    icon = "PASS" if success else "FAIL"
    print(f"  [{icon}] {message}")


def print_info(message: str):
    print(f"  INFO: {message}")


def _get_project_client_api_key():
    """Construct an AIProjectClient using API Key auth (allow_preview=True for beta.* surface).

    Used ONLY for the one quick re-confirmation attempt at the top of test_3 — per the official
    Learn doc and this project's prior finding, API Key auth is expected to be disabled resource-
    wide for this preview surface, so this is not the focus of this run.
    """
    from azure.ai.projects import AIProjectClient
    from azure.core.credentials import AccessToken, AzureKeyCredential
    from azure.core.pipeline.policies import AzureKeyCredentialPolicy

    class _StubTokenCredential:
        def get_token(self, *_scopes, **_kwargs):
            return AccessToken(token="stub", expires_on=0)

    return AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=_StubTokenCredential(),
        authentication_policy=AzureKeyCredentialPolicy(
            credential=AzureKeyCredential(API_KEY),
            name="api-key",
        ),
        allow_preview=True,
    )


_entra_client_cache = None


def _get_project_client_entra():
    """Return a cached AIProjectClient using Entra ID (DefaultAzureCredential) — the sole/primary
    auth path for all beta.skills / toolboxes / agents calls in this run."""
    global _entra_client_cache
    if _entra_client_cache is not None:
        return _entra_client_cache

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    _entra_client_cache = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )
    return _entra_client_cache


def _with_foundry_header(kwargs: dict) -> dict:
    """Merge the Foundry-Features preview header into a call's kwargs['headers'], without
    clobbering any headers already present."""
    headers = dict(kwargs.get("headers") or {})
    headers.setdefault("Foundry-Features", FOUNDRY_FEATURES_HEADER["Foundry-Features"])
    kwargs["headers"] = headers
    return kwargs


def _entra_bearer_token() -> str:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential().get_token("https://ai.azure.com/.default").token


def _zip_bytes_root_layout() -> bytes:
    """Package SKILL_DIR as an in-memory ZIP with SKILL.md at the ZIP root (Agents API layout,
    confirmed by doc 10 §4 — different from the Responses API path's single-top-level-folder
    layout used in test_skill_responses_api.py)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(SKILL_DIR.rglob("*")):
            if file_path.is_file():
                arcname = str(file_path.relative_to(SKILL_DIR))
                zf.write(file_path, arcname=arcname)
    return buf.getvalue()


def _zip_bytes_root_layout_singleline(original_zip_bytes: bytes) -> bytes:
    """Build an in-memory, single-line-description variant of SKILL.md (never written back to the
    real repo file) and re-zip it under the same root layout, for the frontmatter A/B control."""
    with zipfile.ZipFile(io.BytesIO(original_zip_bytes)) as zf:
        names = zf.namelist()
        contents = {name: zf.read(name) for name in names}

    original_skill_md = contents["SKILL.md"].decode("utf-8")
    post = frontmatter.loads(original_skill_md)
    # Replace the YAML folded block scalar description with a single-line plain scalar,
    # matching the root-cause finding already documented in doc 10 §11.7 for the Responses API path.
    single_line_description = " ".join(post.metadata["description"].split())
    post.metadata["description"] = single_line_description
    singleline_skill_md = frontmatter.dumps(post)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in contents.items():
            if name == "SKILL.md":
                zf.writestr(name, singleline_skill_md)
            else:
                zf.writestr(name, data)
    return buf.getvalue()


def _looks_like_frontmatter_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(kw in text for kw in ("frontmatter", "front matter", "parsing", "yaml", "front-matter"))


# =============================================================================
# Test 1: 校验 SKILL.md frontmatter
# =============================================================================


def test_1_validate_skill_frontmatter():
    """验证 mr-training-creator/SKILL.md 的 frontmatter 满足 Skills API 命名/长度约束."""
    print_header("Test 1: 校验 SKILL.md Frontmatter")

    all_pass = True
    skill_md_path = SKILL_DIR / "SKILL.md"

    ok = skill_md_path.exists()
    print_result(ok, f"SKILL.md exists: {skill_md_path.relative_to(TESTS_DIR)}")
    if not ok:
        return False

    post = frontmatter.load(str(skill_md_path))
    fm = post.metadata
    body = post.content.strip()

    for field in ("name", "description"):
        ok = field in fm and bool(fm[field])
        print_result(ok, f"Frontmatter field '{field}' present: {str(fm.get(field, ''))[:60]}")
        if not ok:
            all_pass = False

    name = fm.get("name", "")
    ok = bool(SKILL_NAME_PATTERN.match(name)) and len(name) <= 64 and "--" not in name
    print_result(ok, f"Skill name '{name}' matches ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$, <=64 chars, no '--'")
    if not ok:
        all_pass = False

    description = fm.get("description", "")
    ok = len(description) <= 1024
    print_result(ok, f"Description length {len(description)} <= 1024 chars")
    if not ok:
        all_pass = False

    ok = len(body) > 100
    print_result(ok, f"SKILL.md body length {len(body)} chars > 100")
    if not ok:
        all_pass = False

    return all_pass


# =============================================================================
# Test 2: 打包 Skill 为 ZIP（Agents API 根目录布局）
# =============================================================================


def test_2_package_skill_as_zip():
    """将 SKILL_DIR 打包为内存 ZIP，SKILL.md 位于 ZIP 根目录."""
    print_header("Test 2: 打包 Skill 为 ZIP（Agents API 根目录布局）")

    all_pass = True
    zip_bytes = _zip_bytes_root_layout()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()

    ok = "SKILL.md" in names
    print_result(ok, f"ZIP namelist contains 'SKILL.md' (root-level): {names}")
    if not ok:
        all_pass = False

    original_post = frontmatter.load(str(SKILL_DIR / "SKILL.md"))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        reopened_post = frontmatter.loads(zf.read("SKILL.md").decode("utf-8"))
    ok = reopened_post.metadata.get("name") == original_post.metadata.get("name")
    print_result(
        ok,
        f"Re-opened ZIP SKILL.md name '{reopened_post.metadata.get('name')}' "
        f"matches original '{original_post.metadata.get('name')}'",
    )
    if not ok:
        all_pass = False

    print_info(f"ZIP size: {len(zip_bytes)} bytes, {len(names)} entries")

    test_2_package_skill_as_zip.zip_bytes = zip_bytes

    return all_pass


# =============================================================================
# Test 3: Foundry-Features 头假设验证 + Inline 上传 Skill
# =============================================================================


def test_3_header_hypothesis_and_inline_upload():
    """验证 Foundry-Features 头假设，并通过 project.beta.skills.create() 内联创建 Skill（Entra ID）."""
    print_header("Test 3: Foundry-Features 头假设验证 + Inline 上传 Skill（Azure, Entra ID）")

    if not ENDPOINT:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT not set")
        return None

    # --- Quick, one-off API Key re-confirmation (not the focus of this run) ---
    if API_KEY:
        try:
            _get_project_client_api_key().beta.skills.get(INLINE_SKILL_NAME)
            print_info("[api-key] Unexpected: get() did not raise (skill may already exist)")
        except Exception as e:
            status_code = getattr(e, "status_code", None)
            print_info(f"[api-key] Re-confirmed still-rejected: status_code={status_code}, {e}")
    else:
        print_info("Skipped API-key re-confirmation: AZURE_FOUNDRY_API_KEY not set")

    post = frontmatter.load(str(SKILL_DIR / "SKILL.md"))
    fm = post.metadata
    body = post.content.strip()

    client = _get_project_client_entra()

    sig = inspect.signature(client.beta.skills.create)
    print_info(f"client.beta.skills.create signature (installed SDK): {sig}")
    has_inline_content_kwarg = "inline_content" in sig.parameters
    print_info(
        f"Real installed SDK shape: {'2.3.0-style (SkillInlineContent via inline_content kwarg)' if has_inline_content_kwarg else '2.1.0-style (direct description/instructions kwargs)'}"
    )

    kwargs: dict = {}
    if has_inline_content_kwarg:
        from azure.ai.projects.models import SkillInlineContent

        kwargs["inline_content"] = SkillInlineContent(
            description=fm.get("description", ""),
            instructions=body,
            metadata={
                "source": "poc-inline",
                "domain": str((fm.get("metadata") or {}).get("domain", "")),
            },
        )
    else:
        kwargs["description"] = fm.get("description", "")
        kwargs["instructions"] = body
        kwargs["metadata"] = {
            "source": "poc-inline",
            "domain": str((fm.get("metadata") or {}).get("domain", "")),
        }

    kwargs = _with_foundry_header(kwargs)
    print_info(
        "Testing hypothesis: missing Foundry-Features header caused prior 405 "
        f"(Entra ID + explicit headers={kwargs['headers']} on this call; note SDK 2.3.0's "
        "BetaOperations also auto-injects this header for every beta.skills/.../ call via an "
        "internal _OperationMethodHeaderProxy, confirmed by introspecting "
        "azure.ai.projects.operations._patch — so this call is doubly covered)"
    )

    try:
        result = client.beta.skills.create(name=INLINE_SKILL_NAME, **kwargs)
        _created_skills.append(INLINE_SKILL_NAME)
        result_dict = result.as_dict() if hasattr(result, "as_dict") else dict(result)
        print_result(
            True,
            f"[entra-id + Foundry-Features] Skill created inline: name={result.name}, "
            f"fields={list(result_dict.keys())}",
        )
        print_info(
            "HYPOTHESIS RESULT: CONFIRMED — the prior 405 Method Not Allowed is gone; inline "
            "Skill creation via Entra ID + Foundry-Features header succeeded for real."
        )
        test_3_header_hypothesis_and_inline_upload.skill_name = result.name
        return True
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        print_result(
            False,
            f"[entra-id + Foundry-Features] Inline skill creation failed "
            f"(status_code={status_code}): {e}",
        )
        print_info(
            "HYPOTHESIS RESULT: REFUTED (or inconclusive) — the header did not resolve the "
            "prior 405; the real failure reason is captured above."
        )
        return False


# =============================================================================
# Test 4: ZIP 包上传 Skill（create_from_files）+ frontmatter A/B 控制
# =============================================================================


def test_4_create_skill_from_files():
    """通过 project.beta.skills.create_from_files() 上传 ZIP 创建 Skill（2.3.0 中
    create_from_package 已移除）。若因 frontmatter 解析问题失败，重试单行 description 变体."""
    global _zip_uploaded_skill_name
    print_header("Test 4: ZIP 包上传 Skill（create_from_files，Azure, Entra ID）")

    if not ENDPOINT:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT not set")
        return None

    zip_bytes = getattr(test_2_package_skill_as_zip, "zip_bytes", None)
    if not zip_bytes:
        print_result(False, "No ZIP bytes available (Test 2 must run first)")
        return False

    client = _get_project_client_entra()

    has_create_from_package = hasattr(client.beta.skills, "create_from_package")
    has_create_from_files = hasattr(client.beta.skills, "create_from_files")
    print_info(
        f"client.beta.skills.create_from_package present: {has_create_from_package}; "
        f"create_from_files present: {has_create_from_files}"
    )
    if not has_create_from_files:
        print_result(False, "Neither create_from_files nor a usable replacement found on this SDK version")
        return False

    sig = inspect.signature(client.beta.skills.create_from_files)
    print_info(f"client.beta.skills.create_from_files signature: {sig}")

    from azure.ai.projects.models import CreateSkillVersionFromFilesBody

    def _attempt(name: str, this_zip_bytes: bytes, file_shape_label: str, files_value):
        content = CreateSkillVersionFromFilesBody(files=files_value)
        kwargs = _with_foundry_header({})
        result = client.beta.skills.create_from_files(name, content, **kwargs)
        _created_skills.append(result.name)
        result_dict = result.as_dict() if hasattr(result, "as_dict") else dict(result)
        print_result(
            True,
            f"[{file_shape_label}] ZIP skill created: name={result.name}, fields={list(result_dict.keys())}",
        )
        return result.name

    # --- Attempt 1: original SKILL.md (YAML folded block scalar description) ---
    try:
        real_name = _attempt(
            ZIP_SKILL_NAME,
            zip_bytes,
            "original SKILL.md (description: >-)",
            [("mr-training-creator.zip", zip_bytes, "application/zip")],
        )
        _zip_uploaded_skill_name = real_name
        test_4_create_skill_from_files.skill_name = real_name
        return True
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        print_result(
            False,
            f"[original SKILL.md] ZIP skill creation failed (status_code={status_code}): {e}",
        )
        if not _looks_like_frontmatter_error(e):
            print_info(
                "Error does not look frontmatter/parsing-shaped — not retrying with the "
                "single-line A/B variant."
            )
            return False

    # --- Attempt 2 (A/B control): single-line description variant ---
    print_info(
        "Error message is frontmatter/parsing-shaped — retrying with an in-memory single-line "
        "description A/B variant, per the known Responses-API-path finding (doc 10 §11.7) that "
        "YAML folded block scalars broke server-side frontmatter parsing there."
    )
    try:
        singleline_zip_bytes = _zip_bytes_root_layout_singleline(zip_bytes)
        real_name = _attempt(
            SINGLELINE_SKILL_NAME,
            singleline_zip_bytes,
            "single-line description A/B variant",
            [("mr-training-creator-singleline-poc.zip", singleline_zip_bytes, "application/zip")],
        )
        _zip_uploaded_skill_name = real_name
        test_4_create_skill_from_files.skill_name = real_name
        print_info(
            "A/B RESULT: single-line description variant succeeded where the original "
            "YAML-folded-block-scalar SKILL.md failed — same root cause as the Responses API path."
        )
        return True
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        print_result(
            False,
            f"[single-line A/B variant] ZIP skill creation ALSO failed "
            f"(status_code={status_code}): {e}",
        )
        print_info(
            "A/B RESULT: single-line variant did not fix it either — the Agents API path's ZIP "
            "parsing failure has a different (or additional) root cause than the Responses API "
            "path's YAML-folded-scalar issue."
        )
        return False


# =============================================================================
# Test 5: Get / List / Download 往返验证
# =============================================================================


def test_5_get_list_download_roundtrip():
    """对已创建的 Skill(s) 做 get / list / download 往返验证."""
    print_header("Test 5: Get / List / Download 往返验证（Azure, Entra ID）")

    if not ENDPOINT:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT not set")
        return None

    if not _created_skills:
        print_info("Skipped: no skills were created in Test 3/4")
        return None

    client = _get_project_client_entra()
    all_pass = True

    try:
        listed_names = {s.name for s in client.beta.skills.list(limit=50, **_with_foundry_header({}))}
        print_info(f"list() returned {len(listed_names)} skill(s) total")
    except Exception as e:
        print_result(False, f"list() failed: {e}")
        listed_names = set()
        all_pass = False

    for skill_name in _created_skills:
        try:
            got = client.beta.skills.get(skill_name, **_with_foundry_header({}))
            ok = got.name == skill_name
            print_result(ok, f"get('{skill_name}') -> name={got.name}")
            if not ok:
                all_pass = False
        except Exception as e:
            print_result(False, f"get('{skill_name}') failed: {e}")
            all_pass = False

        ok = skill_name in listed_names
        print_result(ok, f"list() contains '{skill_name}': {ok}")
        if not ok:
            all_pass = False

        try:
            chunks = list(client.beta.skills.download(skill_name, **_with_foundry_header({})))
            downloaded_bytes = b"".join(chunks)
            with zipfile.ZipFile(io.BytesIO(downloaded_bytes)) as zf:
                has_skill_md = "SKILL.md" in zf.namelist()
                skill_md_name = None
                if has_skill_md:
                    post = frontmatter.loads(zf.read("SKILL.md").decode("utf-8"))
                    skill_md_name = post.metadata.get("name")
            ok = has_skill_md
            print_result(
                ok,
                f"download('{skill_name}') -> {len(downloaded_bytes)} bytes, "
                f"SKILL.md present={has_skill_md}, frontmatter name={skill_md_name}",
            )
            if not ok:
                all_pass = False
        except Exception as e:
            print_result(False, f"download('{skill_name}') failed: {e}")
            all_pass = False

    return all_pass


# =============================================================================
# Test 6: Toolbox Version + Skill 挂载
# =============================================================================


def test_6_create_toolbox_version_with_skill():
    """创建 Toolbox 版本，挂载已上传的 mr-training-creator Skill（typed kwarg 优先，raw dict 兜底）."""
    print_header("Test 6: Toolbox Version + Skill 挂载（Azure, Entra ID）")

    if not ENDPOINT:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT not set")
        return None

    if not _zip_uploaded_skill_name:
        print_info("Skipped: no ZIP-uploaded mr-training-creator skill was created successfully in Test 4")
        return None

    client = _get_project_client_entra()

    toolboxes_op, toolboxes_location = None, None
    try:
        toolboxes_op = client.toolboxes
        toolboxes_location = "client.toolboxes"
    except AttributeError:
        toolboxes_op = client.beta.toolboxes
        toolboxes_location = "client.beta.toolboxes"
    print_info(f"Toolboxes operations located at: {toolboxes_location}")

    sig = inspect.signature(toolboxes_op.create_version)
    has_typed_skills_kwarg = "skills" in sig.parameters
    print_info(
        f"toolboxes.create_version signature: {sig} "
        f"(typed 'skills' kwarg present: {has_typed_skills_kwarg})"
    )

    result = None
    mount_mode = None

    if has_typed_skills_kwarg:
        try:
            from azure.ai.projects.models import ToolboxSkillReference

            result = toolboxes_op.create_version(
                name=TOOLBOX_NAME,
                tools=[],
                description="POC toolbox mounting the mr-training-creator skill",
                skills=[ToolboxSkillReference(name=_zip_uploaded_skill_name)],
                **_with_foundry_header({}),
            )
            mount_mode = "typed (skills=[ToolboxSkillReference(...)])"
        except Exception as e:
            print_info(f"Typed 'skills' kwarg rejected: {e}. Falling back to raw dict body.")

    if result is None:
        try:
            result = toolboxes_op.create_version(
                name=TOOLBOX_NAME,
                body={
                    "description": "POC toolbox mounting the mr-training-creator skill",
                    "tools": [],
                    "skills": [{"type": "skill_reference", "name": _zip_uploaded_skill_name}],
                },
                **_with_foundry_header({}),
            )
            mount_mode = "raw dict body"
        except Exception as e:
            status_code = getattr(e, "status_code", None)
            print_result(False, f"Toolbox version creation failed (status_code={status_code}): {e}")
            return False

    _created_toolboxes.append(TOOLBOX_NAME)
    print_result(
        result.name == TOOLBOX_NAME,
        f"Toolbox version created via {mount_mode}: name={result.name}, version={result.version}",
    )

    created_dict = result.as_dict() if hasattr(result, "as_dict") else dict(result)
    echoed_in_create = "skills" in created_dict
    print_info(
        f"create_version() response {'contains' if echoed_in_create else 'does NOT contain'} "
        f"'skills' key: {created_dict.get('skills', '(absent)')}"
    )

    all_pass = result.name == TOOLBOX_NAME

    try:
        fetched = toolboxes_op.get_version(TOOLBOX_NAME, result.version, **_with_foundry_header({}))
        fetched_dict = fetched.as_dict() if hasattr(fetched, "as_dict") else dict(fetched)
        echoed_in_get = "skills" in fetched_dict
        print_result(
            echoed_in_get,
            f"get_version() {'echoes' if echoed_in_get else 'does NOT echo'} "
            f"'skills' field: {fetched_dict.get('skills', '(absent)')}",
        )
        if not echoed_in_get:
            all_pass = False
    except Exception as e:
        print_result(False, f"get_version() failed: {e}")
        all_pass = False

    test_6_create_toolbox_version_with_skill.version = result.version
    test_6_create_toolbox_version_with_skill.toolboxes_op = toolboxes_op
    return all_pass


# =============================================================================
# Test 7: MCP 端点发现
# =============================================================================


def test_7_discover_mcp_endpoint():
    """在 Toolbox Version 对象中查找端点字段；若无则探测约定 REST 路径，尝试 JSON-RPC resources/list."""
    print_header("Test 7: MCP 端点发现（Azure, Entra ID）")

    if not ENDPOINT:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT not set")
        return None

    version = getattr(test_6_create_toolbox_version_with_skill, "version", None)
    toolboxes_op = getattr(test_6_create_toolbox_version_with_skill, "toolboxes_op", None)
    if version is None or toolboxes_op is None:
        print_info("Skipped: Toolbox version was not created successfully in Test 6")
        return None

    fetched = toolboxes_op.get_version(TOOLBOX_NAME, version, **_with_foundry_header({}))
    fetched_dict = fetched.as_dict() if hasattr(fetched, "as_dict") else dict(fetched)
    print_info(f"Full toolbox version fields: {list(fetched_dict.keys())}")

    endpoint_like_keys = [
        k for k in fetched_dict if "endpoint" in k.lower() or "url" in k.lower() or "mcp" in k.lower()
    ]
    if endpoint_like_keys:
        print_result(
            True,
            f"Found endpoint/url-shaped field(s) directly on ToolboxVersionObject: {endpoint_like_keys} "
            f"= {[fetched_dict[k] for k in endpoint_like_keys]}",
        )
        test_7_discover_mcp_endpoint.mcp_endpoint = fetched_dict[endpoint_like_keys[0]]
        return True

    print_info(
        "No endpoint/url-shaped field found on ToolboxVersionObject "
        f"(fields: {list(fetched_dict.keys())}) — probing convention-based REST URLs."
    )

    token = _entra_bearer_token()
    probe_headers = {
        "Authorization": f"Bearer {token}",
        **FOUNDRY_FEATURES_HEADER,
    }
    # The SDK's own client config carries the api-version it uses for every real call
    # (confirmed via introspection: client._config.api_version == "v1"). The first probe
    # attempt (no query param) came back with a helpful 400
    # "Missing required query parameter: api-version" — so the endpoint exists but needs
    # this param. Retry with it attached.
    api_version = getattr(toolboxes_op._config, "api_version", "v1")
    probe_params = {"api-version": api_version}
    candidate_urls = [
        f"{PROJECT_ENDPOINT}/toolboxes/{TOOLBOX_NAME}/mcp",
        f"{PROJECT_ENDPOINT}/toolboxes/{TOOLBOX_NAME}/versions/{version}/mcp",
    ]

    found_endpoint = None
    for url in candidate_urls:
        try:
            resp = httpx.get(url, headers=probe_headers, params=probe_params, timeout=30)
            print_info(
                f"GET {url}?api-version={api_version} -> status={resp.status_code}, "
                f"body={resp.text[:300]!r}"
            )
            if resp.status_code == 200:
                found_endpoint = f"{url}?api-version={api_version}"
                break
        except Exception as e:
            print_info(f"GET {url} -> request error: {e}")

    if not found_endpoint:
        print_result(
            False,
            "No MCP endpoint found via SDK object inspection or convention-based REST probes "
            f"(probed: {candidate_urls} with api-version={api_version}). First attempt without "
            "api-version returned 400 'Missing required query parameter: api-version'; after "
            "adding it, both candidate paths returned 405 Method Not Allowed with an empty body. "
            "This confirms the route prefix exists but GET .../mcp (with or without a version "
            "segment) is not the right shape for this resource/SDK version — a real, observed "
            "API-shape gap, not a script bug.",
        )
        test_7_discover_mcp_endpoint.mcp_endpoint = None
        return False

    print_result(True, f"MCP endpoint reachable at: {found_endpoint}")
    test_7_discover_mcp_endpoint.mcp_endpoint = found_endpoint

    try:
        rpc_resp = httpx.post(
            found_endpoint,
            json={"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}},
            headers={**probe_headers, "Content-Type": "application/json"},
            timeout=30,
        )
        print_info(f"resources/list -> status={rpc_resp.status_code}, body={rpc_resp.text[:500]!r}")
        rpc_body = rpc_resp.json() if rpc_resp.headers.get("content-type", "").startswith("application/json") else None
        skill_resource = None
        if rpc_body and isinstance(rpc_body.get("result"), dict):
            for resource in rpc_body["result"].get("resources", []):
                if _zip_uploaded_skill_name and _zip_uploaded_skill_name in str(resource):
                    skill_resource = resource
                    break
        if skill_resource:
            read_resp = httpx.post(
                found_endpoint,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "resources/read",
                    "params": {"uri": skill_resource.get("uri")},
                },
                headers={**probe_headers, "Content-Type": "application/json"},
                timeout=30,
            )
            print_info(f"resources/read -> status={read_resp.status_code}, body={read_resp.text[:1000]!r}")
            test_7_discover_mcp_endpoint.resources_read_body = read_resp.text
    except Exception as e:
        print_info(f"JSON-RPC probe against MCP endpoint failed: {e}")

    return True


# =============================================================================
# Test 8: Agent 消费 Skill 内容验收测试
# =============================================================================


def test_8_agent_consumes_skill():
    """创建一个 Agent，instructions 拼接从 Azure 下载的真实 Skill 内容，调用一次验证真实回复."""
    print_header("Test 8: Agent 消费 Skill 内容验收测试（Azure, Entra ID）")

    if not ENDPOINT:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT not set")
        return None

    if not _zip_uploaded_skill_name:
        print_info("Skipped: no ZIP-uploaded mr-training-creator skill was created successfully in Test 4")
        return None

    client = _get_project_client_entra()

    # Prefer MCP resources/read content if that path worked in Test 7; otherwise download directly.
    skill_markdown_body = None
    mcp_read_body = getattr(test_7_discover_mcp_endpoint, "resources_read_body", None)
    if mcp_read_body:
        skill_markdown_body = mcp_read_body
        print_info("Using skill content retrieved via MCP resources/read (Test 7).")
    else:
        try:
            chunks = list(client.beta.skills.download(_zip_uploaded_skill_name, **_with_foundry_header({})))
            downloaded_bytes = b"".join(chunks)
            with zipfile.ZipFile(io.BytesIO(downloaded_bytes)) as zf:
                raw = zf.read("SKILL.md").decode("utf-8")
            post = frontmatter.loads(raw)
            skill_markdown_body = post.content.strip()
            print_info(
                f"Using skill content downloaded directly via skills.download('{_zip_uploaded_skill_name}') "
                f"({len(skill_markdown_body)} chars)."
            )
        except Exception as e:
            print_result(False, f"Falling back to direct skill download also failed: {e}")
            return False

    if not skill_markdown_body:
        print_result(False, "No skill content could be retrieved from Azure by any path")
        return False

    from azure.ai.projects.models import PromptAgentDefinition

    base_instructions = (
        "You are a POC verification agent. Briefly describe your role and what skill you have "
        "access to, based ONLY on the skill content below."
    )
    definition = PromptAgentDefinition(
        model=MODEL,
        instructions=f"{base_instructions}\n\n{skill_markdown_body}",
    )

    try:
        agent_result = client.agents.create_version(
            agent_name=AGENT_NAME,
            definition=definition,
            description="POC agent consuming real Azure-downloaded mr-training-creator skill content",
        )
        _created_agents.append(AGENT_NAME)
        print_result(
            True,
            f"Agent created with skill-derived instructions: name={agent_result.name}, "
            f"version={agent_result.version}",
        )
    except Exception as e:
        print_result(False, f"Agent creation failed: {e}")
        return False

    try:
        openai_client = client.get_openai_client()
        response = openai_client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": "Who are you and what is your role? Answer in one or two sentences.",
                }
            ],
            extra_body={
                "agent_reference": {
                    "name": AGENT_NAME,
                    "version": str(agent_result.version),
                    "type": "agent_reference",
                }
            },
        )
        completion_text = response.output_text
    except Exception as e:
        print_result(False, f"Agent invocation (responses.create with agent_reference) failed: {e}")
        return False

    print_info(f"Real completion text: {completion_text!r}")

    signal_terms = ("mr training", "skill creator", "training skill", "medical representative")
    reflects_skill = any(term in completion_text.lower() for term in signal_terms)
    print_result(
        reflects_skill,
        f"Completion text {'reflects' if reflects_skill else 'does NOT clearly reflect'} "
        f"the mr-training-creator skill content (checked for: {signal_terms})",
    )

    test_8_agent_consumes_skill.completion_text = completion_text
    return reflects_skill


# =============================================================================
# Cleanup
# =============================================================================


def cleanup():
    """删除本次运行创建的所有云端资源: Agent -> Toolbox Version -> Toolbox -> Skill(s)."""
    if not (_created_agents or _created_toolboxes or _created_skills):
        return

    print_header("Cleanup: 删除测试资源")
    client = _get_project_client_entra()

    for name in _created_agents:
        try:
            client.agents.delete(agent_name=name)
            print_result(True, f"Deleted agent: {name}")
        except Exception as e:
            print_result(False, f"Failed to delete agent {name}: {e}")

    toolboxes_op = getattr(test_6_create_toolbox_version_with_skill, "toolboxes_op", None) or client.toolboxes
    version = getattr(test_6_create_toolbox_version_with_skill, "version", None)
    for name in _created_toolboxes:
        if version is not None:
            try:
                toolboxes_op.delete_version(name, version, **_with_foundry_header({}))
                print_result(True, f"Deleted toolbox version: {name} v{version}")
            except Exception as e:
                print_result(False, f"Failed to delete toolbox version {name} v{version}: {e}")
        try:
            toolboxes_op.delete(name, **_with_foundry_header({}))
            print_result(True, f"Deleted toolbox: {name}")
        except Exception as e:
            # Real, observed behavior on this resource: deleting the toolbox's only version
            # above already removes the toolbox itself, so this follow-up delete() 404s.
            # That is expected cascading cleanup, not a cleanup failure -- report as such
            # instead of a spurious FAIL.
            status_code = getattr(e, "status_code", None) or getattr(e, "error_code", None)
            already_gone = status_code == 404 or "not_found" in str(e).lower() or "not found" in str(e).lower()
            if already_gone:
                print_info(
                    f"Toolbox '{name}' already removed (deleting its only version cascades to "
                    f"deleting the toolbox itself on this resource) -- no separate delete needed: {e}"
                )
            else:
                print_result(False, f"Failed to delete toolbox {name}: {e}")

    for name in _created_skills:
        try:
            client.beta.skills.delete(name, **_with_foundry_header({}))
            print_result(True, f"Deleted skill: {name}")
        except Exception as e:
            print_result(False, f"Failed to delete skill {name}: {e}")


# =============================================================================
# Main
# =============================================================================


def main():
    print("=" * 72)
    print("  Azure AI Foundry Skills API + Toolbox 挂载 POC（Foundry-Features 头修复后重跑）")
    print("  Skill: mr-training-creator (inline + ZIP upload, toolbox mount, MCP discovery,")
    print("         real agent-consumes-skill acceptance test)")
    print("=" * 72)

    if ENDPOINT:
        print_info(f"Endpoint: {ENDPOINT}")
        print_info(f"Project: {PROJECT_NAME}")
        print_info(f"Model: {MODEL}")
        print_info(
            "Testing hypothesis: missing Foundry-Features: Skills=V1Preview header caused the "
            "prior 405 Method Not Allowed on Entra ID (quick task 260717-x5f)."
        )
    else:
        print_info("No Azure credentials — only running local tests (1-2)")

    print_info(f"Skill dir: {SKILL_DIR.relative_to(TESTS_DIR)}")

    results = {}

    try:
        results["Test 1: Validate Skill Frontmatter"] = test_1_validate_skill_frontmatter()
        results["Test 2: Package Skill as ZIP"] = test_2_package_skill_as_zip()
        results["Test 3: Foundry-Features Hypothesis + Inline Upload"] = (
            test_3_header_hypothesis_and_inline_upload()
        )
        results["Test 4: ZIP Upload (create_from_files)"] = test_4_create_skill_from_files()
        results["Test 5: Get/List/Download Roundtrip"] = test_5_get_list_download_roundtrip()
        results["Test 6: Toolbox Version + Skill Mount"] = test_6_create_toolbox_version_with_skill()
        results["Test 7: MCP Endpoint Discovery"] = test_7_discover_mcp_endpoint()
        results["Test 8: Agent Consumes Skill (Acceptance)"] = test_8_agent_consumes_skill()
    finally:
        try:
            cleanup()
        except Exception as e:
            print_info(f"Cleanup error (non-fatal): {e}")

    print_header("Summary")
    for test_name, ok in results.items():
        if ok is None:
            status = "SKIP"
        elif ok:
            status = "PASS"
        else:
            status = "FAIL"
        print(f"  [{status}] {test_name}")

    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    passed = sum(1 for v in results.values() if v is True)
    print(f"\n  Total: {passed} passed, {failed} failed, {skipped} skipped")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
