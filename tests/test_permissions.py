from app import database
from app.permissions import can_use_skill


def test_public_skill_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.sqlite")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.init_db()
    database.sync_skills(
        [
            {
                "key": "sample",
                "title": "Sample",
                "description": "",
                "command": "sample",
            }
        ]
    )
    database.ensure_user("123", "Test")

    allowed, reason = can_use_skill("123", "sample")

    assert allowed is True
    assert reason == ""

