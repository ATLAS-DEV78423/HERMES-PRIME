import pytest


def test_vision_tool_registered():
    from hermes_prime.agent.tools.vision import vision_analyze, get_vision_schema
    assert callable(vision_analyze)
    schema = get_vision_schema()
    assert schema["name"] == "vision_analyze"
    assert "image_url" in schema["parameters"]["properties"]


def test_vision_schema_has_image_param():
    from hermes_prime.agent.tools.vision import get_vision_schema
    schema = get_vision_schema()
    assert "image_url" in schema["parameters"]["required"]


def test_vision_imports():
    from hermes_prime.agent.tools.vision import vision_analyze
    assert callable(vision_analyze)


def test_vision_rejects_missing_image():
    from hermes_prime.agent.tools.vision import vision_analyze
    result = vision_analyze("", "")
    assert "Error" in result or "error" in result or "not available" in result
