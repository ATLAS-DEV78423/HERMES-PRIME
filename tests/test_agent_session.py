from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_session_store_create():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        try:
            session = store.create_session("test session", model="mistral")
            assert session["id"] is not None
            assert session["title"] == "test session"
            assert session["model"] == "mistral"
        finally:
            store.close()


def test_session_store_append():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        try:
            session = store.create_session("test")
            store.append_message(session["id"], {"role": "user", "content": "hello"})
            store.append_message(session["id"], {"role": "assistant", "content": "hi"})
            msgs = store.get_messages(session["id"])
            assert len(msgs) == 2
        finally:
            store.close()


def test_session_search():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        try:
            s1 = store.create_session("web development")
            store.append_message(s1["id"], {"role": "user", "content": "How do I build a web app?"})
            s2 = store.create_session("data science")
            store.append_message(s2["id"], {"role": "user", "content": "How do I analyze data?"})
            results = store.search("web app")
            assert len(results) >= 1
        finally:
            store.close()


def test_session_list():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        try:
            store.create_session("session 1")
            store.create_session("session 2")
            sessions = store.list_sessions()
            assert len(sessions) == 2
        finally:
            store.close()
