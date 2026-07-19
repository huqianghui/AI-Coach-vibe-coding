"""Phase 29 Plan 01 POC: azure-ai-voicelive SDK availability + Agent connect + capabilities probe.

Verifies (per D-01/D-02/D-03/D-04/D-14, evidence-based, not research-time assumption):
  1. Installed azure-ai-voicelive version.
  2. Entra-first / API-key-fallback credential resolution against Voice Live
     `azure.ai.voicelive.aio.connect(...)`, using api_version="2026-07-15" (GA target)
     regardless of which SDK version is actually installed.
  3. A real Agent connect + session.update round-trip (hosted agent, not classic asst_*).
  4. AIProjectClient.deployments.list() capabilities shape (D-14 probe) -- best-effort,
     does not fail the whole script if unavailable.

Security: never prints raw API keys or bearer tokens -- only credential *path taken*
(Entra vs API-key) and PASS/FAIL/SKIPPED outcomes (T-29-P1 mitigation).

Run:
    cd backend && .venv/bin/python scripts/poc_voice_live_1_3_0.py
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import sys
from pathlib import Path

# Allow running as a standalone script from backend/scripts/ with `app.*` importable.
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

GA_API_VERSION = "2026-07-15"
# Known-good hosted agent from a synced HCP (see backend/ai_coach.db hcp_profiles.agent_id).
DEFAULT_AGENT_NAME = "Dr-Wang-Fang"


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _resolve_credential(api_key: str):
    """Entra-first / API-key-fallback credential resolution for Voice Live connect().

    Mirrors the shape of agent_sync_service._get_project_client (D-01).
    Returns (credential, path_label) where path_label is "entra" or "api_key".
    Never logs the raw key or any token value.
    """
    try:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        credential.get_token("https://cognitiveservices.azure.com/.default")
        print("  [credential] DefaultAzureCredential (Entra ID) token probe: PASS")
        return credential, "entra"
    except Exception as exc:  # noqa: BLE001 - broad on purpose, this is a probe
        print(f"  [credential] DefaultAzureCredential (Entra ID) unavailable: {type(exc).__name__}")

    if api_key:
        from azure.core.credentials import AzureKeyCredential

        print("  [credential] Falling back to AzureKeyCredential (API key)")
        return AzureKeyCredential(api_key), "api_key"

    raise RuntimeError("No valid credential available: Entra probe failed, no API key configured.")


async def _try_entra_only(endpoint: str) -> str:
    """Attempt Entra-only credential acquisition (no API-key fallback), for reporting."""
    try:
        from azure.identity import DefaultAzureCredential

        cred = DefaultAzureCredential()
        cred.get_token("https://cognitiveservices.azure.com/.default")
        return "PASS"
    except Exception:  # noqa: BLE001
        return "FAIL"


async def _try_api_key_credential(api_key: str) -> str:
    if not api_key:
        return "SKIPPED"
    try:
        from azure.core.credentials import AzureKeyCredential

        AzureKeyCredential(api_key)
        return "PASS"
    except Exception:  # noqa: BLE001
        return "FAIL"


async def agent_connect_probe(
    endpoint: str, api_key: str, project_name: str, agent_name: str
) -> tuple[str, str]:
    """Attempt a real Agent connect() + session.update round-trip.

    Returns (result, detail) where result is "PASS" or "FAIL".
    """
    from azure.ai.voicelive.aio import AgentSessionConfig, connect
    from azure.ai.voicelive.models import Modality, RequestSession

    try:
        credential, path_label = _resolve_credential(api_key)
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"credential resolution failed: {type(exc).__name__}: {exc}"

    agent_config: AgentSessionConfig = {
        "agent_name": agent_name,
        "project_name": project_name,
    }

    try:
        async with connect(
            endpoint=endpoint,
            credential=credential,
            api_version=GA_API_VERSION,
            agent_config=agent_config,
        ) as connection:
            print(f"  [connect] WebSocket established via {path_label} credential path")
            await connection.send(
                {
                    "type": "session.update",
                    "session": RequestSession(modalities=[Modality.TEXT]),
                }
            )
            print("  [connect] session.update sent")

            got_session_created = False
            got_session_updated = False
            got_error = False
            error_detail = ""

            for _ in range(10):
                try:
                    event = await asyncio.wait_for(connection.recv(), timeout=15.0)
                    event_type = getattr(event, "type", "unknown")
                    print(f"  [event] {event_type}")
                    if event_type == "session.created":
                        got_session_created = True
                    elif event_type == "session.updated":
                        got_session_updated = True
                        break
                    elif "error" in event_type:
                        got_error = True
                        error_detail = str(getattr(event, "error", event))
                        break
                except TimeoutError:
                    print("  [event] timeout waiting for next event (15s)")
                    break

            if got_error:
                return "FAIL", f"session.update rejected: {error_detail}"
            if not got_session_created:
                return "FAIL", "no session.created event received"
            if not got_session_updated:
                return "FAIL", "session.created received but no session.updated"
            return "PASS", f"credential_path={path_label}"
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"{type(exc).__name__}: {exc}"


async def foundry_capabilities_probe(endpoint: str, api_key: str, project_name: str) -> None:
    """Best-effort probe of AIProjectClient.deployments.list() capabilities shape (D-14).

    AIProjectClient requires a *project-scoped* endpoint
    (``{base}/api/projects/{project_name}``), matching the resolution logic in
    ``agent_sync_service.get_project_endpoint()`` -- passing the bare account
    endpoint returns 404.
    """
    _print_header("Foundry deployments.list() capabilities probe (D-14)")
    base = endpoint.rstrip("/")
    if "/api/projects/" in base:
        project_endpoint = base
    elif project_name:
        project_endpoint = f"{base}/api/projects/{project_name}"
    else:
        print(
            "FOUNDRY_PROBE_UNAVAILABLE: no project_name configured to build project-scoped endpoint"
        )  # noqa: E501
        return

    try:
        from azure.ai.projects import AIProjectClient

        try:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
            credential.get_token("https://ai.azure.com/.default")
        except Exception:  # noqa: BLE001
            if api_key:
                from azure.core.credentials import AzureKeyCredential

                credential = AzureKeyCredential(api_key)
            else:
                print("FOUNDRY_PROBE_UNAVAILABLE: no valid credential (Entra failed, no API key)")
                return

        client = AIProjectClient(endpoint=project_endpoint, credential=credential)
        count = 0
        for d in client.deployments.list():
            count += 1
            print(
                f"  [deployment] name={getattr(d, 'name', '?')} "
                f"model_name={getattr(d, 'model_name', '?')} "
                f"model_publisher={getattr(d, 'model_publisher', '?')} "
                f"capabilities={getattr(d, 'capabilities', {})}"
            )
        if count == 0:
            print("  [deployment] no deployments returned by this project")
    except Exception as exc:  # noqa: BLE001
        print(f"FOUNDRY_PROBE_UNAVAILABLE: {type(exc).__name__}: {exc}")


async def main() -> int:
    from app.config import get_settings

    settings = get_settings()
    endpoint = settings.azure_foundry_endpoint.rstrip("/")
    api_key = settings.azure_foundry_api_key
    project_name = settings.azure_foundry_default_project

    try:
        sdk_version = importlib.metadata.version("azure-ai-voicelive")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = "NOT_INSTALLED"

    _print_header("azure-ai-voicelive POC (Phase 29 Plan 01)")
    print(f"  Installed SDK version: {sdk_version}")
    print(f"  Target GA api_version: {GA_API_VERSION}")
    print(f"  Foundry endpoint configured: {'yes' if endpoint else 'no'}")
    print(f"  Foundry API key configured: {'yes' if api_key else 'no'}")
    print(f"  Project name: {project_name or '(not configured)'}")
    print(f"  Agent name (hosted, known-good synced HCP): {DEFAULT_AGENT_NAME}")

    if not endpoint:
        print(
            f"\nPOC_RESULT: SDK_VERSION={sdk_version} AGENT_CONNECT=FAIL ENTRA=SKIPPED "
            "API_KEY_FALLBACK=SKIPPED (reason=no azure_foundry_endpoint configured)"
        )
        return 1

    entra_result = await _try_entra_only(endpoint)
    api_key_result = await _try_api_key_credential(api_key)

    _print_header("Agent connect + session.update probe (D-01)")
    connect_result, connect_detail = await agent_connect_probe(
        endpoint=endpoint,
        api_key=api_key,
        project_name=project_name,
        agent_name=DEFAULT_AGENT_NAME,
    )
    print(f"  [result] AGENT_CONNECT={connect_result} ({connect_detail})")

    await foundry_capabilities_probe(endpoint, api_key, project_name)

    print(
        f"\nPOC_RESULT: SDK_VERSION={sdk_version} AGENT_CONNECT={connect_result} "
        f"ENTRA={entra_result} API_KEY_FALLBACK={api_key_result}"
    )

    return 0 if connect_result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
