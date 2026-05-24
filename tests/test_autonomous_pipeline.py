import unittest
from unittest.mock import MagicMock, patch

from hermes_prime.autonomous.inference_logger import InferenceLogger
from hermes_prime.autonomous.proposal_parser import ProposalParser, ProposalParsingError
from hermes_prime.contracts import ActionType
from hermes_prime.llm.client import LLMRequest, LLMResponse
from hermes_prime.llm.ollama_adapter import OllamaClient
from hermes_prime.llm.prompt_builder import PromptBuilder
from hermes_prime.llm.vllm_adapter import VLLMClient


class TestPromptBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = PromptBuilder("/workspace")

    def test_system_prompt_contains_constraints(self):
        system = self.builder.build_system_prompt()
        self.assertIn("Hermes Prime", system)
        self.assertIn("Sentinel", system)
        self.assertIn("JSON", system)

    def test_build_messages_has_system_and_user(self):
        messages = self.builder.build_messages("test task")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")

    def test_build_user_prompt_includes_task(self):
        prompt = self.builder.build_user_prompt("analyze code")
        self.assertIn("analyze code", prompt)


class TestProposalParser(unittest.TestCase):
    def test_parse_valid_json_block(self):
        llm_output = """Here is my proposal:
```json
{
  "action_type": "filesystem.read",
  "scope": "/workspace/src",
  "capability": "cap:file-read:scoped",
  "parameters": {"reason": "analyze code"}
}
```"""
        intent_root = "urn:uuid:12345678-1234-1234-1234-123456789012"
        proposal = ProposalParser.parse(llm_output, intent_root, "/workspace")

        self.assertEqual(proposal.action_type, ActionType.FILESYSTEM_READ)
        self.assertEqual(proposal.scope, "/workspace/src")
        self.assertEqual(proposal.capability, "cap:file-read:scoped")

    def test_parse_invalid_json(self):
        llm_output = "```json { invalid json }```"
        intent_root = "urn:uuid:12345678-1234-1234-1234-123456789012"

        with self.assertRaises(ProposalParsingError):
            ProposalParser.parse(llm_output, intent_root, "/workspace")

    def test_parse_missing_required_fields(self):
        llm_output = """```json
{
  "action_type": "filesystem.read"
}
```"""
        intent_root = "urn:uuid:12345678-1234-1234-1234-123456789012"

        with self.assertRaises(ProposalParsingError):
            ProposalParser.parse(llm_output, intent_root, "/workspace")

    def test_parse_raw_json_without_fence(self):
        llm_output = '{"action_type": "filesystem.read", "scope": "/workspace", "capability": "cap:file-read:scoped"}'
        intent_root = "urn:uuid:12345678-1234-1234-1234-123456789012"
        proposal = ProposalParser.parse(llm_output, intent_root, "/workspace")
        self.assertEqual(proposal.action_type, ActionType.FILESYSTEM_READ)


class TestInferenceLogger(unittest.TestCase):
    def test_create_attestation(self):
        request = LLMRequest(
            model="mistral",
            messages=[{"role": "user", "content": "test"}],
        )
        response = LLMResponse(
            model="mistral",
            message_content="response",
            finish_reason="stop",
            tokens_used=42,
            latency_ms=1234.5,
        )

        attestation = InferenceLogger.create_attestation(request, response, signature="sig:test")

        self.assertEqual(attestation.model, "mistral")
        self.assertEqual(attestation.tokens_used, 42)
        self.assertGreater(attestation.latency_ms, 0)
        self.assertEqual(attestation.finish_reason, "stop")

    def test_attestation_to_dict(self):
        request = LLMRequest(
            model="mistral",
            messages=[{"role": "user", "content": "test"}],
        )
        response = LLMResponse(
            model="mistral",
            message_content="response",
            finish_reason="stop",
            tokens_used=42,
            latency_ms=1234.5,
        )

        attestation = InferenceLogger.create_attestation(request, response, signature="sig:test")
        d = attestation.to_dict()

        self.assertIn("attestation_id", d)
        self.assertEqual(d["model"], "mistral")
        self.assertEqual(d["tokens_used"], 42)


class TestLLMClients(unittest.TestCase):
    @patch("requests.Session.get")
    def test_ollama_health_check_success(self, mock_get):
        mock_get.return_value.status_code = 200
        client = OllamaClient()
        self.assertTrue(client.health_check())

    @patch("requests.Session.get")
    def test_ollama_health_check_failure(self, mock_get):
        mock_get.return_value.status_code = 500
        client = OllamaClient()
        self.assertFalse(client.health_check())

    @patch("requests.Session.get")
    def test_ollama_list_models(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "mistral:latest"},
                {"name": "llama2:latest"},
            ]
        }
        mock_get.return_value = mock_response

        client = OllamaClient()
        models = client.list_models()
        self.assertEqual(len(models), 2)
        self.assertIn("mistral:latest", models)

    @patch("requests.Session.post")
    def test_ollama_infer(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": '{"action_type": "filesystem.read"}'},
            "eval_count": 100,
        }
        mock_post.return_value = mock_response

        client = OllamaClient()
        request = LLMRequest(
            model="mistral",
            messages=[{"role": "user", "content": "test"}],
        )
        response = client.infer(request)

        self.assertEqual(response.tokens_used, 100)
        self.assertIn("action_type", response.message_content)

    @patch("requests.Session.post")
    def test_ollama_infer_error(self, mock_post):
        mock_post.return_value.status_code = 500

        client = OllamaClient()
        request = LLMRequest(
            model="mistral",
            messages=[{"role": "user", "content": "test"}],
        )
        response = client.infer(request)

        self.assertEqual(response.finish_reason, "error")
        self.assertEqual(response.message_content, "")

    @patch("requests.Session.get")
    def test_vllm_health_check(self, mock_get):
        mock_get.return_value.status_code = 200
        client = VLLMClient()
        self.assertTrue(client.health_check())

    @patch("requests.Session.post")
    def test_vllm_infer(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test response"}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 50},
        }
        mock_post.return_value = mock_response

        client = VLLMClient()
        request = LLMRequest(
            model="mistral",
            messages=[{"role": "user", "content": "test"}],
        )
        response = client.infer(request)

        self.assertEqual(response.tokens_used, 50)
        self.assertEqual(response.message_content, "test response")


if __name__ == "__main__":
    unittest.main()
