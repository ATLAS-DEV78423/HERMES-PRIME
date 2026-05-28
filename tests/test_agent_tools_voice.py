import pytest


def test_tts_tool_registered():
    from hermes_prime.agent.tools.voice import text_to_speech, get_tts_schema
    assert callable(text_to_speech)
    schema = get_tts_schema()
    assert schema["name"] == "text_to_speech"
    assert "text" in schema["parameters"]["properties"]
