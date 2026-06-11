import pytest


def test_web_search_tool_registered():
    from hermes_prime.agent.tools.web_search import web_search
    assert callable(web_search)


def test_web_fetch_tool_registered():
    from hermes_prime.agent.tools.web_search import web_fetch
    assert callable(web_fetch)


def test_web_search_schema():
    from hermes_prime.agent.tools.web_search import get_search_schema
    schema = get_search_schema()
    assert schema["name"] == "web_search"
    assert "query" in schema["parameters"]["properties"]


def test_web_search_schema_has_required_params():
    from hermes_prime.agent.tools.web_search import get_search_schema
    schema = get_search_schema()
    assert "query" in schema["parameters"]["required"]


def test_web_search_imports():
    from hermes_prime.agent.tools.web_search import web_search
    assert callable(web_search)


def test_web_search_schema_has_num_results():
    from hermes_prime.agent.tools.web_search import get_search_schema
    props = get_search_schema()["parameters"]["properties"]
    assert "num_results" in props
