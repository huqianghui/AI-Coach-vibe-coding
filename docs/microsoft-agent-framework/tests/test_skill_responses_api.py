"""
Azure OpenAI Responses API Skills 路径 POC 验证（openai/v1, 纯 openai SDK）

完整场景:
  1. 本地 SDK surface 发现：确认 openai==2.29.0 是否暴露 client.skills / client.containers 等资源
  2. 将 mr-training-creator Skill 目录打包为内存 ZIP（单一顶层文件夹布局，与 beta.skills 路径的
     ZIP-根目录布局不同）
  3. 通过 client.skills.create() 上传 ZIP，先尝试 API Key 认证，若 401/403 再尝试 Entra ID 兜底
  4. 通过 client.skills.versions.create() 上传第二个版本，校验 latest_version 是否递增
  5. 尝试 client.responses.create()，携带 shell 工具 + container_auto + skill_reference 挂载已上传的 Skill
  6. 独立尝试通过 client.containers.create() 携带 inline base64 ZIP Skill（不依赖上传是否成功）
  7. 清理本次运行创建的所有云端资源（container -> skill version -> skill）

目录结构:
  tests/
    skills/
      mr-training-creator/
        SKILL.md                           # 复用已有的真实 Skill 定义，不新建

前置条件:
  1. backend/.env 中配置 AZURE_FOUNDRY_ENDPOINT, AZURE_FOUNDRY_API_KEY
  2. pip install openai>=1.50.0 python-frontmatter python-dotenv azure-identity

运行:
  cd backend
  .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_skill_responses_api.py
"""

import base64
import inspect
import io
import os
import sys
import zipfile
from pathlib import Path

import frontmatter

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

BASE_URL = f"{ENDPOINT}/openai/v1/" if ENDPOINT else ""

INLINE_CONTAINER_NAME = "mr-training-creator-inline-poc"

_created_skill_ids: list[str] = []
_created_versions: list[tuple[str, str]] = []  # (skill_id, version)
_created_container_ids: list[str] = []


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


def _get_client_api_key():
    """Construct a plain openai SDK client using the API Key as the bearer-style api_key."""
    from openai import OpenAI

    return OpenAI(base_url=BASE_URL, api_key=API_KEY)


def _get_client_entra():
    """Construct a plain openai SDK client using an Entra ID (DefaultAzureCredential) token
    as the api_key fallback (only attempted when the API Key path is rejected with 401/403)."""
    from azure.identity import DefaultAzureCredential
    from openai import OpenAI

    token = DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
    return OpenAI(base_url=BASE_URL, api_key=token)


# Cache of which auth mode was empirically found to work against the openai/v1 Skills/Responses
# endpoints, populated the first time test_3 runs. Value: "api-key" | "entra-id" | None.
_auth_mode: str | None = None
_client_cache = None


def _get_client():
    """Return a client for skills/responses/containers calls, reusing whichever auth mode was
    empirically found to work (see _auth_mode). Defaults to the API-key client until a mode
    is recorded."""
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    if _auth_mode == "entra-id":
        _client_cache = _get_client_entra()
    else:
        _client_cache = _get_client_api_key()
    return _client_cache


def _record_auth_mode(mode: str):
    global _auth_mode, _client_cache
    _auth_mode = mode
    _client_cache = None  # force _get_client() to rebuild with the new mode


def _error_detail(e: Exception) -> str:
    """Extract status code + response body from an openai SDK exception without ever
    printing the API key / bearer token itself."""
    status_code = getattr(e, "status_code", None)
    body = getattr(e, "body", None)
    response = getattr(e, "response", None)
    text = None
    if response is not None:
        try:
            text = response.text
        except Exception:
            text = None
    return f"status_code={status_code}, body={body!r}, response_text={text!r}, message={e}"


# =============================================================================
# Test 1: 本地 SDK surface 发现
# =============================================================================


def test_1_sdk_surface_discovery():
    """确认本地安装的 openai SDK 是否暴露 client.skills / client.containers 等资源（不发起网络请求）."""
    print_header("Test 1: SDK Surface 发现（本地，无网络请求）")

    import openai

    print_info(f"openai.__version__ = {openai.__version__}")

    from openai import OpenAI

    probe_client = OpenAI(base_url=BASE_URL or "https://example.invalid/openai/v1/", api_key="probe")

    all_pass = True

    checks = [
        ("client.skills", hasattr(probe_client, "skills")),
        (
            "client.skills.versions",
            hasattr(probe_client, "skills") and hasattr(probe_client.skills, "versions"),
        ),
        (
            "client.skills.content",
            hasattr(probe_client, "skills") and hasattr(probe_client.skills, "content"),
        ),
        ("client.containers", hasattr(probe_client, "containers")),
    ]
    for label, present in checks:
        print_result(present, f"{label} exists: {present}")
        if not present:
            all_pass = False

    sig = inspect.signature(probe_client.containers.create)
    has_skills_kwarg = "skills" in sig.parameters
    print_result(has_skills_kwarg, f"client.containers.create() has a 'skills' kwarg: {has_skills_kwarg}")
    print_info(f"client.containers.create() signature: {sig}")
    if not has_skills_kwarg:
        all_pass = False

    return all_pass


# =============================================================================
# Test 2: 打包 Skill 为单一顶层文件夹 ZIP
# =============================================================================

MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_FILES = 500
MAX_FILE_BYTES = 25 * 1024 * 1024


def test_2_package_skill_zip():
    """将 SKILL_DIR 打包为内存 ZIP，采用单一顶层文件夹布局（mr-training-creator/SKILL.md），
    与 test_skill_foundry_upload.py 使用的 ZIP-根目录布局明确不同（Responses API 规范要求）."""
    print_header("Test 2: 打包 Skill 为单一顶层文件夹 ZIP")

    all_pass = True
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(SKILL_DIR.rglob("*")):
            if file_path.is_file():
                arcname = f"mr-training-creator/{file_path.relative_to(SKILL_DIR)}"
                zf.write(file_path, arcname=arcname)

    zip_bytes = buf.getvalue()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        infos = zf.infolist()

    ok = names.count("mr-training-creator/SKILL.md") == 1
    print_result(ok, f"ZIP namelist contains exactly one 'mr-training-creator/SKILL.md': {names}")
    if not ok:
        all_pass = False

    ok = len(zip_bytes) <= MAX_ZIP_BYTES
    print_result(ok, f"ZIP size {len(zip_bytes)} bytes <= {MAX_ZIP_BYTES} (50MB limit)")
    if not ok:
        all_pass = False

    ok = len(infos) <= MAX_FILES
    print_result(ok, f"ZIP file count {len(infos)} <= {MAX_FILES} (500 files limit)")
    if not ok:
        all_pass = False

    oversized = [i.filename for i in infos if i.file_size > MAX_FILE_BYTES]
    ok = not oversized
    print_result(ok, f"No individual uncompressed file exceeds {MAX_FILE_BYTES} bytes (25MB): {oversized or 'none'}")
    if not ok:
        all_pass = False

    print_info(f"ZIP size: {len(zip_bytes)} bytes, {len(infos)} entries")

    test_2_package_skill_zip.zip_bytes = zip_bytes

    return all_pass


# =============================================================================
# Test 3: 上传 Skill（client.skills.create）
# =============================================================================


def test_3_upload_skill():
    """通过 client.skills.create() 上传 ZIP 创建 Skill，先尝试 API Key，401/403 时兜底 Entra ID."""
    print_header("Test 3: 上传 Skill（client.skills.create，openai/v1）")

    if not ENDPOINT or not API_KEY:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT or AZURE_FOUNDRY_API_KEY not set")
        return None

    zip_bytes = getattr(test_2_package_skill_zip, "zip_bytes", None)
    if not zip_bytes:
        print_result(False, "No ZIP bytes available (Test 2 must run first)")
        return False

    def _attempt(client, mode_label: str):
        skill = client.skills.create(files=("mr-training-creator.zip", zip_bytes, "application/zip"))
        _created_skill_ids.append(skill.id)
        print_result(
            True,
            f"[{mode_label}] Skill created: id={skill.id}, "
            f"default_version={skill.default_version}, latest_version={skill.latest_version}",
        )
        test_3_upload_skill.skill_id = skill.id
        return True

    # --- Attempt 1: API Key ---
    try:
        ok = _attempt(_get_client_api_key(), "api-key")
        if ok:
            _record_auth_mode("api-key")
        return ok
    except Exception as e:
        print_result(False, f"[api-key] Skill upload failed ({_error_detail(e)})")
        status_code = getattr(e, "status_code", None)
        if status_code not in (401, 403):
            return False
        print_info(
            "NOTE: API-key auth rejected (401/403). Attempting Entra ID "
            "(DefaultAzureCredential) fallback since an `az login` session is available."
        )

    # --- Attempt 2 (fallback): Entra ID ---
    try:
        ok = _attempt(_get_client_entra(), "entra-id")
        if ok:
            _record_auth_mode("entra-id")
        return ok
    except Exception as e:
        print_result(False, f"[entra-id] Skill upload also failed ({_error_detail(e)})")
        return False


# =============================================================================
# Test 4: 版本管理（client.skills.versions.create）
# =============================================================================


def test_4_version_management():
    """上传第二个版本，校验 latest_version 是否递增."""
    print_header("Test 4: 版本管理（client.skills.versions.create）")

    skill_id = getattr(test_3_upload_skill, "skill_id", None)
    if not skill_id:
        print_info("Skipped: Test 3 did not produce a skill id")
        return None

    client = _get_client()
    zip_bytes = getattr(test_2_package_skill_zip, "zip_bytes", None)

    try:
        before = client.skills.retrieve(skill_id)
        print_info(
            f"Before: default_version={before.default_version}, latest_version={before.latest_version}"
        )
    except Exception as e:
        print_result(False, f"skills.retrieve() before version bump failed ({_error_detail(e)})")
        return False

    try:
        version = client.skills.versions.create(
            skill_id, files=("mr-training-creator.zip", zip_bytes, "application/zip")
        )
        _created_versions.append((skill_id, version.version))
        print_info(f"Created new version: {version.version}")
    except Exception as e:
        print_result(False, f"skills.versions.create() failed ({_error_detail(e)})")
        return False

    try:
        after = client.skills.retrieve(skill_id)
        print_info(
            f"After: default_version={after.default_version}, latest_version={after.latest_version}"
        )
    except Exception as e:
        print_result(False, f"skills.retrieve() after version bump failed ({_error_detail(e)})")
        return False

    ok = after.latest_version != before.latest_version
    print_result(
        ok,
        f"latest_version changed after second upload: {before.latest_version} -> {after.latest_version}",
    )
    return ok


# =============================================================================
# Test 5: Responses API shell 工具挂载
# =============================================================================


def test_5_responses_shell_tool_mount():
    """尝试 client.responses.create()，携带 shell 工具 + container_auto + skill_reference。"""
    print_header("Test 5: Responses shell 工具 + container_auto + skill_reference 挂载")

    skill_id = getattr(test_3_upload_skill, "skill_id", None)
    if not skill_id:
        print_info("Skipped: Test 3 did not produce a skill id")
        return None

    client = _get_client()
    tools = [
        {
            "type": "shell",
            "environment": {
                "type": "container_auto",
                "skills": [{"type": "skill_reference", "skill_id": skill_id}],
            },
        }
    ]

    try:
        response = client.responses.create(
            model=MODEL,
            tools=tools,
            input=(
                "List the skills available to you in this shell environment and describe "
                "what mr-training-creator does."
            ),
        )
    except Exception as e:
        print_result(False, f"responses.create() with shell tool + skill_reference failed ({_error_detail(e)})")
        print_info(
            "A 400/other API error citing the shell tool or model as unsupported is a VALID, "
            "recorded finding for this specific deployment/model, not a script bug."
        )
        return False

    output = getattr(response, "output", None)
    print_info(f"response.output: {output!r}")
    print_result(True, "responses.create() call succeeded (did not raise)")
    print_info(
        "Whether the model actually acknowledged/invoked the mounted skill must be judged from "
        "the printed output above — success of the call alone does not prove skill usage."
    )
    return True


# =============================================================================
# Test 6: Inline base64 ZIP Skill（containers.create）
# =============================================================================


def test_6_inline_base64_skill():
    """通过 client.containers.create() 携带 inline base64 ZIP Skill，独立于 Test 3 是否成功."""
    print_header("Test 6: Inline base64 ZIP Skill（client.containers.create）")

    if not ENDPOINT or not API_KEY:
        print_info("Skipped: AZURE_FOUNDRY_ENDPOINT or AZURE_FOUNDRY_API_KEY not set")
        return None

    zip_bytes = getattr(test_2_package_skill_zip, "zip_bytes", None)
    if not zip_bytes:
        print_result(False, "No ZIP bytes available (Test 2 must run first)")
        return False

    b64_data = base64.b64encode(zip_bytes).decode()
    client = _get_client()

    # The API validates that the inline skill's name/description match the values parsed from
    # the ZIP's SKILL.md frontmatter (empirically discovered: a mismatched POC-only name/description
    # is rejected with 400 "Inline skill name/description must match the values in
    # SKILL.md/Skills.md front matter."). The container itself may still use a distinct POC name.
    post = frontmatter.load(str(SKILL_DIR / "SKILL.md"))
    skill_name = post.metadata.get("name", "")
    skill_description = post.metadata.get("description", "")

    try:
        container = client.containers.create(
            name=INLINE_CONTAINER_NAME,
            skills=[
                {
                    "type": "inline",
                    "name": skill_name,
                    "description": skill_description,
                    "source": {
                        "type": "base64",
                        "media_type": "application/zip",
                        "data": b64_data,
                    },
                }
            ],
        )
        _created_container_ids.append(container.id)
        print_result(True, f"Container created with inline skill: id={container.id}, name={getattr(container, 'name', None)}")
        return True
    except Exception as e:
        print_result(False, f"containers.create() with inline base64 skill failed ({_error_detail(e)})")
        print_info(
            "Root-cause investigation (separate probe, same real Azure resource, not counted as a "
            "test case): the exact same error persists even when name/description are passed "
            "verbatim from the parsed frontmatter, and regardless of what name/description values "
            "are sent — but a minimal SKILL.md using a single-line plain-scalar `description:` "
            "(instead of this skill's YAML folded block scalar `description: >-`) succeeds "
            "immediately. This strongly suggests the server-side frontmatter parser used by "
            "containers.create()'s inline-skill validation does not correctly handle YAML folded "
            "block scalars, so it fails to extract any name/description to match against — not an "
            "auth or SDK issue, but a server-side SKILL.md-in-ZIP parsing limitation specific to "
            "this inline path."
        )
        return False


# =============================================================================
# Cleanup
# =============================================================================


def cleanup():
    """删除本次运行创建的所有云端资源：container -> skill version -> skill。"""
    if not (_created_container_ids or _created_versions or _created_skill_ids):
        return

    print_header("Cleanup: 删除测试资源")
    client = _get_client()

    has_container_delete = hasattr(client.containers, "delete")
    if not has_container_delete:
        print_info("client.containers.delete() not present on this SDK version — skipping container cleanup")
    for container_id in _created_container_ids:
        if not has_container_delete:
            continue
        try:
            client.containers.delete(container_id)
            print_result(True, f"Deleted container: {container_id}")
        except Exception as e:
            print_result(False, f"Failed to delete container {container_id}: {e}")

    for skill_id, version in _created_versions:
        try:
            client.skills.versions.delete(version, skill_id=skill_id)
            print_result(True, f"Deleted skill version: {skill_id} v{version}")
        except Exception as e:
            print_result(
                False,
                f"Failed to delete skill version {skill_id} v{version} "
                f"(may be the default/last remaining version — informational, not necessarily a bug): {e}",
            )

    for skill_id in _created_skill_ids:
        try:
            client.skills.delete(skill_id)
            print_result(True, f"Deleted skill: {skill_id}")
        except Exception as e:
            print_result(
                False,
                f"Failed to delete skill {skill_id} "
                f"(may already be gone if its last version was deleted above — informational): {e}",
            )


# =============================================================================
# Main
# =============================================================================


def main():
    print("=" * 72)
    print("  Azure OpenAI Responses API Skills 路径 POC (openai/v1, plain openai SDK)")
    print("  Skill: mr-training-creator (skills.create, versions, responses shell tool, inline base64)")
    print("=" * 72)

    if ENDPOINT:
        print_info(f"Endpoint: {ENDPOINT}")
        print_info(f"Base URL: {BASE_URL}")
        print_info(f"Project: {PROJECT_NAME}")
        print_info(f"Model: {MODEL}")
    else:
        print_info("No Azure credentials — only running local tests (1-2)")

    print_info(f"Skill dir: {SKILL_DIR.relative_to(TESTS_DIR)}")

    results = {}

    try:
        results["Test 1: SDK Surface Discovery"] = test_1_sdk_surface_discovery()
        results["Test 2: Package Skill ZIP (single top-level folder)"] = test_2_package_skill_zip()
        results["Test 3: Upload Skill"] = test_3_upload_skill()
        results["Test 4: Version Management"] = test_4_version_management()
        results["Test 5: Responses Shell Tool Mount"] = test_5_responses_shell_tool_mount()
        results["Test 6: Inline Base64 ZIP Skill"] = test_6_inline_base64_skill()
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
