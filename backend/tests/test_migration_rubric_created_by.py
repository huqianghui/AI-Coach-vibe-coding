"""Tests for rubric migration created_by fallback behavior."""

from importlib import util
from pathlib import Path
from types import ModuleType

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


class _Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


def _load_migration(filename: str, module_name: str) -> ModuleType:
    spec = util.spec_from_file_location(module_name, MIGRATIONS_DIR / filename)
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v28b_skips_default_rubric_restore_when_admin_missing(monkeypatch):
    """Fresh DB migrations should not insert scoring rubrics with created_by='system'."""
    module = _load_migration(
        "v28b_restore_default_scoring_rubric.py",
        "v28b_restore_default_scoring_rubric_test",
    )

    class Connection:
        insert_count = 0

        def execute(self, statement, params=None):
            sql = str(statement)
            if "INSERT INTO scoring_rubrics" in sql:
                self.insert_count += 1
            return _Result(None)

    conn = Connection()
    monkeypatch.setattr(module.op, "get_bind", lambda: conn)

    module.upgrade()

    assert conn.insert_count == 0


def test_h21a_uses_existing_scenario_user_when_admin_missing():
    """Legacy scenario migration should use a real user instead of a synthetic system id."""
    module = _load_migration(
        "h21a_add_rubric_id_remove_weight_columns.py",
        "h21a_add_rubric_id_remove_weight_columns_test",
    )

    class Connection:
        def execute(self, statement, params=None):
            sql = str(statement)
            if "SELECT id FROM users WHERE role = 'admin'" in sql:
                return _Result(None)
            if "SELECT s.created_by FROM scenarios s" in sql:
                return _Result(("user-1",))
            return _Result(None)

    assert module._get_rubric_created_by_user_id(Connection()) == "user-1"
