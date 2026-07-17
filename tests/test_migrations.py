from pathlib import Path

from catalyst_grit import MigrationManager, SQLiteWorkspaceRepository


def test_packaged_migrations_are_ordered_and_complete():
    migrations = MigrationManager.available()
    assert [item.version for item in migrations] == [1, 2, 3]
    assert [item.name for item in migrations] == ["core_workspace", "checkpoints_reviews_audit", "recovery_plans_actions_reassessment"]
    assert all(item.up_sql.strip() and item.down_sql.strip() for item in migrations)


def test_clean_install_rollback_and_remigration(tmp_path: Path):
    database = tmp_path / "workspace.sqlite3"
    with SQLiteWorkspaceRepository(database, auto_migrate=False) as repo:
        assert repo.migrations.status() == {"current": 0, "latest": 3, "applied": [], "pending": [1, 2, 3]}
        assert repo.migrations.migrate() == [1, 2, 3]
        assert repo.migrations.status()["current"] == 3
        assert repo.migrations.rollback(1) == [3]
        assert repo.migrations.status()["current"] == 2
        assert repo.migrations.migrate() == [3]
        assert repo.health()["integrity"] == "ok"


def test_migrate_to_explicit_target(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "target.sqlite3", auto_migrate=False) as repo:
        assert repo.migrations.migrate(1) == [1]
        tables = {row[0] for row in repo.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "projects" in tables
        assert "checkpoints" not in tables
        assert repo.migrations.migrate(2) == [2]
        tables = {row[0] for row in repo.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "checkpoints" in tables and "audit_events" in tables
        assert repo.migrations.migrate(3) == [3]
        tables = {row[0] for row in repo.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"action_events", "blockers", "reassessments"} <= tables
