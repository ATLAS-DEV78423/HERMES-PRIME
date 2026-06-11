import pytest


def test_tts_tool_registered():
    from hermes_prime.agent.tools.voice import text_to_speech, get_tts_schema
    assert callable(text_to_speech)
    schema = get_tts_schema()
    assert schema["name"] == "text_to_speech"
    assert "text" in schema["parameters"]["properties"]


def test_voice_schema_has_required_text():
    from hermes_prime.agent.tools.voice import get_tts_schema
    schema = get_tts_schema()
    assert "text" in schema["parameters"]["required"]


def test_voice_imports():
    from hermes_prime.agent.tools.voice import text_to_speech
    assert callable(text_to_speech)
