from __future__ import annotations

from pathlib import Path

import pytest


def test_init_creates_db(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    db = tmp_path / "sessions.db"
    mgr = SessionManager(db)
    try:
        assert mgr.path == db
        assert db.exists()
    finally:
        mgr.close()


def test_create_session_returns_dict(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("test title", model="gpt4", source="web")
        assert s["title"] == "test title"
        assert s["model"] == "gpt4"
        assert s["source"] == "web"
        assert s["id"]
        assert s["message_count"] == 0
    finally:
        mgr.close()


def test_create_session_defaults(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("defaults")
        assert s["model"] == "mistral"
        assert s["source"] == "cli"
    finally:
        mgr.close()


def test_append_message_and_get_messages(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("msg test")
        mgr.append_message(s["id"], {"role": "user", "content": "hello"})
        mgr.append_message(s["id"], {"role": "assistant", "content": "world"})
        msgs = mgr.get_messages(s["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "world"
    finally:
        mgr.close()


def test_get_messages_limits(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("limit test")
        for i in range(10):
            mgr.append_message(s["id"], {"role": "user", "content": f"msg {i}"})
        msgs = mgr.get_messages(s["id"], limit=3)
        assert len(msgs) == 3
    finally:
        mgr.close()


def test_get_messages_empty_session(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("empty")
        msgs = mgr.get_messages(s["id"])
        assert msgs == []
    finally:
        mgr.close()


def test_list_sessions_all(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        mgr.create_session("s1")
        mgr.create_session("s2")
        mgr.create_session("s3")
        sessions = mgr.list_sessions()
        assert len(sessions) == 3
    finally:
        mgr.close()


def test_list_sessions_filter_by_source(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        mgr.create_session("cli session", source="cli")
        mgr.create_session("web session", source="web")
        mgr.create_session("api session", source="api")
        cli_sessions = mgr.list_sessions(source="cli")
        assert len(cli_sessions) == 1
        assert cli_sessions[0]["source"] == "cli"
        web_sessions = mgr.list_sessions(source="web")
        assert len(web_sessions) == 1
    finally:
        mgr.close()


def test_list_sessions_empty(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        assert mgr.list_sessions() == []
    finally:
        mgr.close()


def test_list_sessions_limit(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        for i in range(10):
            mgr.create_session(f"s{i}")
        sessions = mgr.list_sessions(limit=3)
        assert len(sessions) == 3
    finally:
        mgr.close()


def test_get_session_found(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        created = mgr.create_session("find me")
        found = mgr.get_session(created["id"])
        assert found is not None
        assert found["title"] == "find me"
        assert found["id"] == created["id"]
    finally:
        mgr.close()


def test_get_session_not_found(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        assert mgr.get_session("nonexistent-id") is None
    finally:
        mgr.close()


def test_rename_session_success(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("old name")
        result = mgr.rename_session(s["id"], "new name")
        assert result is True
        updated = mgr.get_session(s["id"])
        assert updated is not None
        assert updated["title"] == "new name"
    finally:
        mgr.close()


def test_rename_session_not_found(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        result = mgr.rename_session("bad-id", "anything")
        assert result is False
    finally:
        mgr.close()


def test_delete_session_success(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("delete me")
        mgr.append_message(s["id"], {"role": "user", "content": "msg"})
        result = mgr.delete_session(s["id"])
        assert result is True
        assert mgr.get_session(s["id"]) is None
        assert mgr.get_messages(s["id"]) == []
    finally:
        mgr.close()


def test_delete_session_not_found(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        result = mgr.delete_session("bad-id")
        assert result is False
    finally:
        mgr.close()


def test_prune_sessions_removes_old(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager
    from datetime import datetime, timezone, timedelta

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("old")
        mgr.append_message(s["id"], {"role": "user", "content": "x"})
        mgr._conn.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(days=60)).isoformat(), s["id"]),
        )
        mgr._conn.commit()
        mgr.create_session("new")
        count = mgr.prune_sessions(older_than_days=30)
        assert count == 1
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["title"] == "new"
    finally:
        mgr.close()


def test_prune_sessions_none_old(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        mgr.create_session("fresh")
        count = mgr.prune_sessions(older_than_days=30)
        assert count == 0
    finally:
        mgr.close()


def test_stats_empty(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        st = mgr.stats()
        assert st["sessions"] == 0
        assert st["messages"] == 0
        assert st["total_tokens"] == 0
        assert st["sources"] == []
    finally:
        mgr.close()


def test_stats_with_data(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s1 = mgr.create_session("a", source="cli")
        mgr.append_message(s1["id"], {"role": "user", "content": "hi"})
        s2 = mgr.create_session("b", source="web")
        mgr.append_message(s2["id"], {"role": "user", "content": "hello"})
        mgr.append_message(s2["id"], {"role": "assistant", "content": "world"})
        st = mgr.stats()
        assert st["sessions"] == 2
        assert st["messages"] == 3
        assert len(st["sources"]) == 2
    finally:
        mgr.close()


def test_export_jsonl_all(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("export all")
        mgr.append_message(s["id"], {"role": "user", "content": "line1"})
        output = mgr.export_jsonl()
        lines = output.strip().split("\n")
        assert len(lines) == 1
        import json
        record = json.loads(lines[0])
        assert record["title"] == "export all"
        assert len(record["messages"]) == 1
    finally:
        mgr.close()


def test_export_jsonl_single_session(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s1 = mgr.create_session("s1")
        s2 = mgr.create_session("s2")
        mgr.append_message(s1["id"], {"role": "user", "content": "from s1"})
        mgr.append_message(s2["id"], {"role": "user", "content": "from s2"})
        output = mgr.export_jsonl(session_id=s1["id"])
        lines = output.strip().split("\n")
        assert len(lines) == 1
        import json
        record = json.loads(lines[0])
        assert record["title"] == "s1"
    finally:
        mgr.close()


def test_export_jsonl_writes_file(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("file export")
        mgr.append_message(s["id"], {"role": "user", "content": "data"})
        out = tmp_path / "export.jsonl"
        mgr.export_jsonl(out_path=str(out))
        assert out.exists()
        content = out.read_text()
        assert "file export" in content
    finally:
        mgr.close()


def test_search_finds_matching(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("web dev")
        mgr.append_message(s["id"], {"role": "user", "content": "How do I build a web app?"})
        mgr.create_session("data science")
        results = mgr.search("web app")
        assert len(results) >= 1
        assert results[0]["title"] == "web dev"
    finally:
        mgr.close()


def test_search_no_match(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("python")
        mgr.append_message(s["id"], {"role": "user", "content": "learning python"})
        results = mgr.search("quantum physics")
        assert results == []
    finally:
        mgr.close()


def test_search_limit(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        for i in range(5):
            s = mgr.create_session(f"session {i}")
            mgr.append_message(s["id"], {"role": "user", "content": f"test data {i}"})
        results = mgr.search("test", limit=2)
        assert len(results) <= 2
    finally:
        mgr.close()


def test_close(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager
    import sqlite3

    mgr = SessionManager(tmp_path / "sessions.db")
    mgr.create_session("close test")
    mgr.close()
    with pytest.raises(sqlite3.ProgrammingError):
        mgr.create_session("after close")


def test_context_manager(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager
    import sqlite3

    with SessionManager(tmp_path / "sessions.db") as mgr:
        s = mgr.create_session("ctx test")
        assert s["title"] == "ctx test"
    with pytest.raises(sqlite3.ProgrammingError):
        mgr.create_session("outside ctx")


def test_append_message_updates_message_count(tmp_path: Path) -> None:
    from hermes_prime.sessions import SessionManager

    mgr = SessionManager(tmp_path / "sessions.db")
    try:
        s = mgr.create_session("count test")
        assert s["message_count"] == 0
        for i in range(5):
            mgr.append_message(s["id"], {"role": "user", "content": f"msg {i}"})
        updated = mgr.get_session(s["id"])
        assert updated is not None
        assert updated["message_count"] == 5
    finally:
        mgr.close()
