"""Unit tests for the stateless POST /prompts/optimize endpoint.

Calls the router coroutine directly with a mocked optimize_prompt so coverage tracks
the return/branch lines that httpx ASGITransport does not. No live sidecar, no DB writes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.prompts import OptimizeRequest, optimize
from app.models.user import User
from app.services.prompt_optimizer_client import PromptOptimizerError
from app.utils.exceptions import AppException, ValidationException


def _admin() -> User:
    user = MagicMock(spec=User)
    user.id = "admin-user-id"
    user.role = "admin"
    return user


async def test_system_mode_returns_optimized_text():
    data = OptimizeRequest(prompt="You are helpful.", mode="system")
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="BETTER")) as mock_opt:
        result = await optimize(data, _user=_admin())
    assert result.optimized_prompt == "BETTER"
    mock_opt.assert_awaited_once()
    assert mock_opt.await_args.kwargs["mode"] == "system"


async def test_user_mode_forwards_mode():
    data = OptimizeRequest(prompt="hi", mode="user")
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="U")) as mock_opt:
        await optimize(data, _user=_admin())
    assert mock_opt.await_args.kwargs["mode"] == "user"


async def test_iterate_mode_forwards_requirements():
    data = OptimizeRequest(prompt="hi", mode="iterate", requirements="shorter")
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="I")) as mock_opt:
        await optimize(data, _user=_admin())
    assert mock_opt.await_args.kwargs["requirements"] == "shorter"


async def test_iterate_without_requirements_raises_422():
    data = OptimizeRequest(prompt="hi", mode="iterate")
    with pytest.raises(ValidationException):
        await optimize(data, _user=_admin())


async def test_invalid_mode_raises_422():
    data = OptimizeRequest(prompt="hi", mode="bogus")
    with pytest.raises(ValidationException):
        await optimize(data, _user=_admin())


async def test_upstream_error_surfaces_as_appexception():
    data = OptimizeRequest(prompt="hi", mode="system")
    with patch(
        "app.api.prompts.optimize_prompt",
        new=AsyncMock(side_effect=PromptOptimizerError("sidecar down")),
    ):
        with pytest.raises(AppException) as exc:
            await optimize(data, _user=_admin())
    assert exc.value.status_code == 502
    assert exc.value.code == "PROMPT_OPTIMIZER_ERROR"


async def test_does_not_persist(monkeypatch):
    """Endpoint takes no db dependency and must not write anything."""
    import inspect

    sig = inspect.signature(optimize)
    assert "db" not in sig.parameters
