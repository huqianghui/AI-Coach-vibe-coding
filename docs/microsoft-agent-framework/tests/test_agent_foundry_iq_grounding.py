"""
Azure Voice Live SDK 1.3.0b1 Agent 模式 + Foundry IQ 知识库 grounding 实测

验证：一个已同步（agent_sync_status="synced"）且挂载了启用的 Foundry IQ 知识库
（HcpKnowledgeConfig, index_name="omada-product-parameters-kb"）的 Agent，在 Voice Live
Agent 模式会话中，是否会针对知识库相关问题真正触发 MCP 检索工具调用
（mcp_list_tools.*/response.mcp_call.* 事件），而对无关问题不触发。

使用当前实际安装的 SDK（1.3.0b1）的 connect() 扁平化 kwargs 形态
（agent_name=/project_name=），不导入已移除的 AgentSessionConfig。

运行方式：
  cd backend
  .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py
"""

import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

load_dotenv(backend_dir / ".env")

ENDPOINT = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").rstrip("/")
API_KEY = os.getenv("AZURE_FOUNDRY_API_KEY", "")
PROJECT_NAME = os.getenv("AZURE_FOUNDRY_DEFAULT_PROJECT", "avarda-demo-prj")
AGENT_NAME = "Dr-Wang-Fang"
API_VERSION = "2026-07-15"

# Turn 1: 只能从挂载的知识库 (omada-product-parameters-kb) 中检索到的具体问题
KB_QUESTION = (
    "请查阅你的知识库，告诉我泽布替尼(zanubrutinib)在 omada 产品参数知识库中记录的"
    "具体剂量、储存条件和已批准适应症分别是什么？请明确说明这个答案是否来自你的知识库检索。"
)

# Turn 2: 与知识库完全无关的对照问题
CONTROL_QUESTION = "跨部门沟通中最常见的挑战是什么？请从管理学的角度简单谈谈你的看法。"

MCP_EVENT_PREFIXES = ("mcp_list_tools.", "response.mcp_call")


def print_header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_result(success: bool, message: str) -> None:
    icon = "✅" if success else "❌"
    print(f"  {icon} {message}")


def print_info(message: str) -> None:
    print(f"  ℹ️  {message}")


def print_event(event_type: str, detail: str) -> None:
    icon = "🔎" if event_type.startswith(MCP_EVENT_PREFIXES) else "📨"
    print(f"  {icon} [{event_type}] {detail}")


def _is_mcp_event(event_type: str) -> bool:
    return event_type.startswith(MCP_EVENT_PREFIXES)


async def _run_turn(connection, question: str, turn_label: str) -> dict:
    """发送一条用户消息 + response.create，收集事件直到 response.done 或超时。"""
    print_header(f"Turn: {turn_label}")

    events_collected: list[str] = []
    text_response = ""
    got_response = False
    got_error = False
    error_detail = ""

    await connection.send(
        {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": question}],
            },
        }
    )
    print_info(f"用户消息已发送: {question[:40]}...")

    await connection.send(
        {
            "type": "response.create",
            "response": {"modalities": ["text"]},
        }
    )
    print_info("response.create 已发送，等待回复...")

    for _ in range(800):
        try:
            event = await asyncio.wait_for(connection.recv(), timeout=60.0)
            event_type = getattr(event, "type", "unknown")
            events_collected.append(event_type)

            if event_type == "response.text.delta":
                delta = getattr(event, "delta", "")
                text_response += delta
            elif event_type == "response.text.done":
                full_text = getattr(event, "text", "")
                if full_text:
                    text_response = full_text
                got_response = True
                print_event(event_type, f"文本回复完成 (长度={len(text_response)})")
            elif event_type == "response.done":
                response_obj = getattr(event, "response", None)
                status = str(getattr(response_obj, "status", "")) if response_obj else ""
                if "failed" in status.lower():
                    got_error = True
                    status_details = getattr(response_obj, "status_details", None)
                    error_detail = str(status_details) if status_details else status
                    print_event(event_type, f"response.status=FAILED: {error_detail[:300]}")
                else:
                    print_event(event_type, f"回复流结束 (status={status})")
                break
            elif "error" in event_type:
                got_error = True
                error_detail = str(getattr(event, "error", event))
                print_event(event_type, f"错误: {error_detail}")
                break
            elif _is_mcp_event(event_type):
                print_event(event_type, "*** MCP 检索工具事件 ***")
            else:
                print_event(event_type, "")
        except asyncio.TimeoutError:
            print_info("等待事件超时 (60秒)")
            break

    if got_error:
        print_result(False, f"对话出错: {error_detail}")
    elif got_response and text_response:
        print_result(True, "收到完整文本回复!")
        print()
        print(f"  ┌─ 回复 {'─' * 55}")
        for i in range(0, len(text_response), 60):
            print(f"  │ {text_response[i:i + 60]}")
        print(f"  └{'─' * 62}")
    elif text_response:
        print_result(True, f"收到部分回复 (长度={len(text_response)})")
    else:
        print_result(False, "未收到任何文本回复")

    mcp_events = [e for e in events_collected if _is_mcp_event(e)]
    event_counts = Counter(events_collected)
    print_info(f"事件统计: {dict(event_counts)}")
    print_info(f"MCP 检索事件是否出现: {'是' if mcp_events else '否'} ({mcp_events})")

    return {
        "turn": turn_label,
        "events": events_collected,
        "event_counts": dict(event_counts),
        "mcp_events": mcp_events,
        "response": text_response,
        "error": error_detail,
        "got_response": got_response,
    }


async def _run_session(connect_fn, credential, auth_label: str) -> dict:
    """建立一次 Agent 模式连接，跑完 session.update + Turn1(KB) + Turn2(对照)。"""
    print_header(f"连接尝试: {auth_label} + Agent 模式 (agent_name=/project_name= 扁平化 kwargs)")

    turn_results: list[dict] = []

    try:
        async with connect_fn(
            endpoint=ENDPOINT,
            credential=credential,
            api_version=API_VERSION,
            agent_name=AGENT_NAME,
            project_name=PROJECT_NAME,
        ) as connection:
            print_result(True, "WebSocket 连接建立")

            await connection.send(
                {
                    "type": "session.update",
                    "session": {"modalities": ["text"]},
                }
            )
            print_info("session.update 已发送")

            got_session_created = False
            got_session_updated = False
            for _ in range(10):
                try:
                    event = await asyncio.wait_for(connection.recv(), timeout=15.0)
                    event_type = getattr(event, "type", "unknown")
                    if event_type == "session.created":
                        got_session_created = True
                        print_event(event_type, "会话已创建")
                    elif event_type == "session.updated":
                        got_session_updated = True
                        print_event(event_type, "会话已更新")
                        break
                    elif "error" in event_type:
                        error_detail = str(getattr(event, "error", event))
                        print_event(event_type, f"错误: {error_detail}")
                        print_result(False, f"会话配置被拒绝: {error_detail}")
                        return {"connected": True, "session_ok": False, "error": error_detail, "turns": []}
                    else:
                        print_event(event_type, "")
                except asyncio.TimeoutError:
                    print_info("等待事件超时 (15秒)")
                    break

            if not got_session_created:
                print_result(False, "未收到 session.created")
                return {"connected": True, "session_ok": False, "error": "no session.created", "turns": []}

            print_result(True, f"会话配置成功 (updated={got_session_updated})")

            # Turn 1: KB-grounded question
            try:
                turn1 = await _run_turn(connection, KB_QUESTION, "1 - 知识库检索问题")
                turn_results.append(turn1)
            except Exception as e:
                print_result(False, f"Turn 1 失败: {type(e).__name__}: {str(e)[:300]}")
                turn_results.append(
                    {
                        "turn": "1 - 知识库检索问题",
                        "events": [],
                        "event_counts": {},
                        "mcp_events": [],
                        "response": "",
                        "error": f"{type(e).__name__}: {str(e)[:300]}",
                        "got_response": False,
                    }
                )

            # Turn 2: control question, same connection
            try:
                turn2 = await _run_turn(connection, CONTROL_QUESTION, "2 - 对照问题（无关知识库）")
                turn_results.append(turn2)
            except Exception as e:
                print_result(False, f"Turn 2 失败: {type(e).__name__}: {str(e)[:300]}")
                turn_results.append(
                    {
                        "turn": "2 - 对照问题（无关知识库）",
                        "events": [],
                        "event_counts": {},
                        "mcp_events": [],
                        "response": "",
                        "error": f"{type(e).__name__}: {str(e)[:300]}",
                        "got_response": False,
                    }
                )

            return {"connected": True, "session_ok": True, "error": "", "turns": turn_results}

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:300]}"
        print_result(False, f"连接失败: {error_msg}")
        return {"connected": False, "session_ok": False, "error": error_msg, "turns": []}


def _print_turn_summary(turn_results: list[dict]) -> None:
    for r in turn_results:
        print()
        print(f"  Turn: {r['turn']}")
        print(f"    事件统计: {r['event_counts']}")
        print(f"    MCP 检索事件: {'触发 -> ' + str(r['mcp_events']) if r['mcp_events'] else '未触发'}")
        print(f"    回复长度: {len(r['response'])}")
        if r["error"]:
            print(f"    错误: {r['error']}")

    if len(turn_results) >= 1:
        t1_mcp = bool(turn_results[0].get("mcp_events"))
        print(f"\n  🔎 Turn 1 (知识库问题) MCP 检索事件触发: {'✅ 是' if t1_mcp else '❌ 否'}")
    if len(turn_results) >= 2:
        t2_mcp = bool(turn_results[1].get("mcp_events"))
        print(f"  🔎 Turn 2 (对照问题) MCP 检索事件触发: {'⚠️ 是（意外）' if t2_mcp else '✅ 否（符合预期）'}")


async def main() -> None:
    if not ENDPOINT or not API_KEY:
        print(
            "\n  ❌ 缺少配置：请确认 backend/.env 中设置了 "
            "AZURE_FOUNDRY_ENDPOINT 和 AZURE_FOUNDRY_API_KEY"
        )
        sys.exit(1)

    import azure.ai.voicelive as vl_pkg
    from azure.ai.voicelive.aio import connect
    from azure.core.credentials import AzureKeyCredential
    from azure.identity.aio import DefaultAzureCredential

    print("\n" + "=" * 70)
    print("  Agent 模式 + Foundry IQ 知识库 grounding 实测 (SDK 1.3.0b1)")
    print("=" * 70)
    print(f"\n  SDK Version:  {getattr(vl_pkg, '__version__', vl_pkg._version.VERSION)}")
    print(f"  Endpoint:     {ENDPOINT}")
    print(f"  Project:      {PROJECT_NAME}")
    print(f"  Agent:        {AGENT_NAME}")
    print(f"  API Version:  {API_VERSION}")

    # ─── Attempt 1: API Key（与历史 2026-04-08 POC 相同认证方式） ───
    key_credential = AzureKeyCredential(API_KEY)
    api_key_result = await _run_session(connect, key_credential, "API Key")

    # ─── Attempt 2: Entra ID（若 API Key 未成功建立会话，用 Entra ID 完成实际
    #     grounding 测试；这也是生产代码 _resolve_voice_live_credential 的
    #     Entra-first 逻辑在 Entra 探测成功时会走的同一条路径） ───
    entra_credential = None
    entra_result: dict | None = None
    if not api_key_result.get("session_ok"):
        print_info("API Key 未能建立可用会话，切换 Entra ID (DefaultAzureCredential) 继续实测")
        entra_credential = DefaultAzureCredential()
        entra_result = await _run_session(connect, entra_credential, "Entra ID")
        await entra_credential.close()

    # ─── 汇总 ───
    print_header("测试结果汇总")

    print("\n  认证方式对比：")
    print(f"    API Key  : connected={api_key_result['connected']}, session_ok={api_key_result['session_ok']}"
          + (f", error={api_key_result['error'][:120]}" if api_key_result["error"] else ""))
    if entra_result is not None:
        print(f"    Entra ID : connected={entra_result['connected']}, session_ok={entra_result['session_ok']}"
              + (f", error={entra_result['error'][:120]}" if entra_result["error"] else ""))

    active_result = entra_result if (entra_result and entra_result.get("session_ok")) else api_key_result
    if active_result.get("session_ok"):
        active_label = "Entra ID" if active_result is entra_result else "API Key"
        print(f"\n  实际用于 grounding 实测的认证方式: {active_label}")
        _print_turn_summary(active_result["turns"])
    else:
        print_result(False, "两种认证方式均未能建立可用会话，无法完成 grounding 实测")

    print()


if __name__ == "__main__":
    asyncio.run(main())
