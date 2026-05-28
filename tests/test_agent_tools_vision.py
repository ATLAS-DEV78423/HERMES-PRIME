import pytest


def test_vision_tool_registered():
    from hermes_prime.agent.tools.vision import vision_analyze, get_vision_schema
    assert callable(vision_analyze)
    schema = get_vision_schema()
    assert schema["name"] == "vision_analyze"
    assert "image_url" in schema["parameters"]["properties"]
