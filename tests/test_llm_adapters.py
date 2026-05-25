from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from hermes_prime.llm.client import LLMRequest, LLMResponse
from hermes_prime.llm.ollama_adapter import OllamaClient
from hermes_prime.llm.prompt_builder import PromptBuilder
from hermes_prime.llm.vllm_adapter import VLLMClient


GOVERNANCE_MARKERS = [
    "Hermes Prime",
    "governed autonomous agent",
    "JSON proposal",
    "Sentinel policy engine",
    "action_type",
    "risk_tier",
    "capability",
]


class TestLLMRequest(unittest.TestCase):
    def test_default_values(self):
        req = LLMRequest(model="test-model", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(req.model, "test-model")
        self.assertEqual(req.temperature, 0.7)
        self.assertIsNone(req.max_tokens)
        self.assertEqual(req.top_p, 0.95)

    def test_custom_values(self):
        req = LLMRequest(
            model="gpt-4",
            messages=[{"role": "system", "content": "you are"}],
            temperature=0.1,
            max_tokens=100,
            top_p=0.5,
        )
        self.assertEqual(req.model, "gpt-4")
        self.assertEqual(req.temperature, 0.1)
        self.assertEqual(req.max_tokens, 100)
        self.assertEqual(req.top_p, 0.5)


class TestLLMResponse(unittest.TestCase):
    def test_all_fields(self):
        resp = LLMResponse(
            model="test-model",
            message_content="Hello",
            finish_reason="stop",
            tokens_used=42,
            latency_ms=123.4,
        )
        self.assertEqual(resp.model, "test-model")
        self.assertEqual(resp.message_content, "Hello")
        self.assertEqual(resp.finish_reason, "stop")
        self.assertEqual(resp.tokens_used, 42)
        self.assertEqual(resp.latency_ms, 123.4)

    def test_error_response_fields(self):
        resp = LLMResponse(
            model="error-model",
            message_content="",
            finish_reason="error",
            tokens_used=0,
            latency_ms=0.0,
        )
        self.assertEqual(resp.finish_reason, "error")
        self.assertEqual(resp.tokens_used, 0)


class TestPromptBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = PromptBuilder(workspace_root="/test/workspace")

    def test_build_system_prompt_includes_governance_instructions(self):
        prompt = self.builder.build_system_prompt()
        for marker in GOVERNANCE_MARKERS:
            self.assertIn(marker, prompt)

    def test_build_system_prompt_mentions_json_proposal(self):
        prompt = self.builder.build_system_prompt()
        self.assertIn("```json", prompt)
        self.assertIn("action_type", prompt)

    def test_build_user_prompt_with_task_only(self):
        prompt = self.builder.build_user_prompt(task="do something")
        self.assertIn("Task: do something", prompt)
        self.assertIn("Propose your next action as a JSON block.", prompt)

    def test_build_user_prompt_with_file_context(self):
        files = ["src/main.py", "src/utils.py", "src/config.py"]
        prompt = self.builder.build_user_prompt(
            task="refactor code",
            file_context=files,
        )
        self.assertIn("Relevant files:", prompt)
        self.assertIn("  - src/main.py", prompt)
        self.assertIn("  - src/utils.py", prompt)

    def test_build_user_prompt_file_context_limited_to_5(self):
        files = [f"file{i}.py" for i in range(10)]
        prompt = self.builder.build_user_prompt(
            task="task",
            file_context=files,
        )
        self.assertEqual(prompt.count("  - "), 5)

    def test_build_user_prompt_with_recent_actions(self):
        actions = [
            {"action_type": "filesystem.read", "scope": "/tmp/a"},
            {"action_type": "filesystem.write", "scope": "/tmp/b"},
        ]
        prompt = self.builder.build_user_prompt(
            task="task",
            recent_actions=actions,
        )
        self.assertIn("Recent approved actions:", prompt)
        self.assertIn("filesystem.read: /tmp/a", prompt)
        self.assertIn("filesystem.write: /tmp/b", prompt)

    def test_build_user_prompt_recent_actions_limited_to_3(self):
        actions = [{"action_type": f"type{i}", "scope": f"/s{i}"} for i in range(10)]
        prompt = self.builder.build_user_prompt(
            task="task",
            recent_actions=actions,
        )
        self.assertEqual(prompt.count("  - "), 3)

    def test_build_user_prompt_with_learned_guidance(self):
        prompt = self.builder.build_user_prompt(
            task="task",
            learned_guidance="Previous attempts suggest using T2 risk tier.",
        )
        self.assertIn("Previous attempts suggest using T2 risk tier.", prompt)

    def test_build_user_prompt_with_all_context(self):
        files = ["src/main.py"]
        actions = [{"action_type": "read", "scope": "/tmp"}]
        prompt = self.builder.build_user_prompt(
            task="deploy",
            file_context=files,
            recent_actions=actions,
            learned_guidance="Be cautious.",
        )
        self.assertIn("Task: deploy", prompt)
        self.assertIn("Relevant files:", prompt)
        self.assertIn("Recent approved actions:", prompt)
        self.assertIn("Be cautious.", prompt)
        self.assertIn("Propose your next action as a JSON block.", prompt)

    def test_build_messages_returns_system_and_user(self):
        messages = self.builder.build_messages(task="hello")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("Hermes Prime", messages[0]["content"])
        self.assertIn("Task: hello", messages[1]["content"])

    def test_build_messages_passes_context_through(self):
        messages = self.builder.build_messages(
            task="analyze",
            file_context=["src/lib.rs"],
        )
        self.assertIn("src/lib.rs", messages[1]["content"])


class TestOllamaClient(unittest.TestCase):
    def test_default_base_url(self):
        client = OllamaClient()
        self.assertEqual(client.base_url, "http://localhost:11434")

    def test_custom_base_url_trailing_slash_stripped(self):
        client = OllamaClient(base_url="http://myhost:8080/")
        self.assertEqual(client.base_url, "http://myhost:8080")

    def test_health_check_returns_true_on_200(self):
        client = OllamaClient()
        client.session = MagicMock()
        client.session.get.return_value.status_code = 200
        self.assertTrue(client.health_check())
        client.session.get.assert_called_once_with(
            "http://localhost:11434/api/tags", timeout=5
        )

    def test_health_check_returns_false_on_non_200(self):
        client = OllamaClient()
        client.session = MagicMock()
        client.session.get.return_value.status_code = 500
        self.assertFalse(client.health_check())

    def test_health_check_returns_false_on_exception(self):
        client = OllamaClient()
        client.session = MagicMock()
        client.session.get.side_effect = Exception("connection failed")
        self.assertFalse(client.health_check())

    def test_list_models_returns_names(self):
        client = OllamaClient()
        client.session = MagicMock()
        client.session.get.return_value.status_code = 200
        client.session.get.return_value.json.return_value = {
            "models": [{"name": "llama3"}, {"name": "mistral"}]
        }
        models = client.list_models()
        self.assertEqual(models, ["llama3", "mistral"])

    def test_list_models_returns_empty_on_error(self):
        client = OllamaClient()
        client.session = MagicMock()
        client.session.get.side_effect = Exception("fail")
        self.assertEqual(client.list_models(), [])

    def test_infer_returns_response(self):
        client = OllamaClient()
        client.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hello!"},
            "eval_count": 5,
        }
        client.session.post.return_value = mock_resp

        req = LLMRequest(model="llama3", messages=[{"role": "user", "content": "say hi"}])
        resp = client.infer(req)
        self.assertEqual(resp.model, "llama3")
        self.assertEqual(resp.message_content, "Hello!")
        self.assertEqual(resp.finish_reason, "stop")
        self.assertEqual(resp.tokens_used, 5)

    def test_infer_returns_error_on_non_200(self):
        client = OllamaClient()
        client.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        client.session.post.return_value = mock_resp

        resp = client.infer(LLMRequest(model="m", messages=[{"role": "user", "content": "x"}]))
        self.assertEqual(resp.finish_reason, "error")

    def test_infer_includes_num_predict_when_max_tokens_set(self):
        client = OllamaClient()
        client.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "ok"}, "eval_count": 1}
        client.session.post.return_value = mock_resp

        req = LLMRequest(model="m", messages=[], max_tokens=50)
        client.infer(req)
        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["num_predict"], 50)

    def test_infer_handles_exception_gracefully(self):
        client = OllamaClient()
        client.session = MagicMock()
        client.session.post.side_effect = Exception("timeout")

        resp = client.infer(LLMRequest(model="m", messages=[]))
        self.assertEqual(resp.finish_reason, "error")
        self.assertEqual(resp.message_content, "")

    def test_session_is_requests_session(self):
        import requests
        client = OllamaClient()
        self.assertIsInstance(client.session, requests.Session)


class TestVLLMClient(unittest.TestCase):
    def test_default_base_url(self):
        client = VLLMClient()
        self.assertEqual(client.base_url, "http://localhost:8000")

    def test_custom_base_url_trailing_slash_stripped(self):
        client = VLLMClient(base_url="http://myhost:7000/")
        self.assertEqual(client.base_url, "http://myhost:7000")

    def test_health_check_returns_true_on_200(self):
        client = VLLMClient()
        client.session = MagicMock()
        client.session.get.return_value.status_code = 200
        self.assertTrue(client.health_check())
        client.session.get.assert_called_once_with(
            "http://localhost:8000/health", timeout=5
        )

    def test_health_check_returns_false_on_non_200(self):
        client = VLLMClient()
        client.session = MagicMock()
        client.session.get.return_value.status_code = 503
        self.assertFalse(client.health_check())

    def test_health_check_returns_false_on_exception(self):
        client = VLLMClient()
        client.session = MagicMock()
        client.session.get.side_effect = Exception("fail")
        self.assertFalse(client.health_check())

    def test_list_models_returns_ids(self):
        client = VLLMClient()
        client.session = MagicMock()
        client.session.get.return_value.status_code = 200
        client.session.get.return_value.json.return_value = {
            "data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]
        }
        models = client.list_models()
        self.assertEqual(models, ["gpt-4", "gpt-3.5-turbo"])

    def test_list_models_returns_empty_on_error(self):
        client = VLLMClient()
        client.session = MagicMock()
        client.session.get.side_effect = Exception("fail")
        self.assertEqual(client.list_models(), [])

    def test_infer_returns_response(self):
        client = VLLMClient()
        client.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hi!"}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 3},
        }
        client.session.post.return_value = mock_resp

        req = LLMRequest(model="gpt-4", messages=[{"role": "user", "content": "say hi"}])
        resp = client.infer(req)
        self.assertEqual(resp.model, "gpt-4")
        self.assertEqual(resp.message_content, "Hi!")
        self.assertEqual(resp.finish_reason, "stop")
        self.assertEqual(resp.tokens_used, 3)

    def test_infer_returns_error_on_non_200(self):
        client = VLLMClient()
        client.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client.session.post.return_value = mock_resp

        resp = client.infer(LLMRequest(model="m", messages=[]))
        self.assertEqual(resp.finish_reason, "error")

    def test_infer_includes_max_tokens_when_set(self):
        client = VLLMClient()
        client.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 1},
        }
        client.session.post.return_value = mock_resp

        req = LLMRequest(model="m", messages=[], max_tokens=100)
        client.infer(req)
        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["max_tokens"], 100)

    def test_infer_includes_top_p(self):
        client = VLLMClient()
        client.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 1},
        }
        client.session.post.return_value = mock_resp

        req = LLMRequest(model="m", messages=[], top_p=0.5)
        client.infer(req)
        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["top_p"], 0.5)

    def test_infer_handles_exception_gracefully(self):
        client = VLLMClient()
        client.session = MagicMock()
        client.session.post.side_effect = Exception("timeout")

        resp = client.infer(LLMRequest(model="m", messages=[]))
        self.assertEqual(resp.finish_reason, "error")
        self.assertEqual(resp.message_content, "")

    def test_session_is_requests_session(self):
        import requests
        client = VLLMClient()
        self.assertIsInstance(client.session, requests.Session)


class TestLLMClientInheritance(unittest.TestCase):
    def test_ollama_is_llm_client(self):
        from hermes_prime.llm.client import LLMClient
        self.assertTrue(issubclass(OllamaClient, LLMClient))

    def test_vllm_is_llm_client(self):
        from hermes_prime.llm.client import LLMClient
        self.assertTrue(issubclass(VLLMClient, LLMClient))


if __name__ == "__main__":
    unittest.main()
