from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_prime.agent.tool_registry import ToolRegistry
from hermes_prime.agent.types import AgentContext, AgentResult, ToolCall
from hermes_prime.llm.client import LLMClient, LLMRequest
from hermes_prime.utils import new_urn_uuid


_SYSTEM_PROMPT = """You are Hermes Prime, an intelligent AI assistant with access to tools.
You can use tools to search the web, execute commands, and manage tasks.

When you need to use a tool, respond with a JSON block:
```json
{{"tool": "tool_name", "arguments": {{"key": "value"}}}}
```

Available tools:
{tool_schemas}

Respond conversationally. When you need information or to perform an action,
use the appropriate tool by name."""


class AgentLoop:
    def __init__(
        self,
        workspace_root: str | Path = ".",
        sentinel: Any = None,
        vault: Any = None,
        trust_store: Any = None,
        forge: Any = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        self.sentinel = sentinel
        self.vault = vault
        self.trust_store = trust_store
        self.forge = forge
        self.llm_client = llm_client
        self.tool_registry = ToolRegistry()

    def register_tool(self, name: str, fn: Any, description: str) -> None:
        self.tool_registry.register(name, fn, description)

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return self.tool_registry.execute(name, **arguments)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return self.tool_registry.tool_schemas()

    def _tool_schemas_text(self) -> str:
        schemas = self.get_tool_schemas()
        if not schemas:
            return "No tools available."
        lines = []
        for s in schemas:
            params = s.get("parameters", {})
            props = params.get("properties", {})
            args_str = ", ".join(
                f"{pname}: {pinfo.get('type', 'string')}"
                for pname, pinfo in props.items()
            )
            lines.append(f"- {s['name']}({args_str}): {s['description']}")
        return "\n".join(lines)

    def build_messages(self, prompt: str, context: AgentContext | None = None) -> list[dict[str, Any]]:
        system_prompt = _SYSTEM_PROMPT.format(tool_schemas=self._tool_schemas_text())
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if context and context.messages:
            messages.extend(context.messages)
        messages.append({"role": "user", "content": prompt})
        return messages

    def run(self, prompt: str, context: AgentContext | None = None) -> AgentResult:
        ctx = context or AgentContext(workspace_root=self.workspace_root)
        session_id = ctx.session_id or new_urn_uuid()
        messages = self.build_messages(prompt, context)

        if self.llm_client is None:
            return AgentResult(
                session_id=session_id,
                messages=messages,
                tool_calls=[],
                summary=f"Processed: {prompt[:60]}",
                success=True,
            )

        if not self.llm_client.health_check():
            return AgentResult(
                session_id=session_id,
                messages=messages,
                tool_calls=[],
                summary="LLM service is not available. Check that your LLM provider is running.",
                success=False,
            )

        tool_calls_made: list[ToolCall] = []
        all_messages = list(messages)
        model = ctx.model

        for iteration in range(ctx.max_iterations):
            request = LLMRequest(
                model=model,
                messages=all_messages,
                temperature=0.7,
                max_tokens=2048,
            )
            try:
                response = self.llm_client.infer(request)
            except Exception as e:
                return AgentResult(
                    session_id=session_id,
                    messages=all_messages,
                    tool_calls=tool_calls_made,
                    summary=f"LLM inference failed: {e}",
                    success=False,
                )

            content = response.message_content.strip()

            # Check if response contains a tool call JSON block
            import re
            tool_match = re.search(
                r'```json\s*(\{.*?"tool"\s*:\s*"[^"]+".*?\})\s*```',
                content,
                re.DOTALL,
            )
            if tool_match:
                try:
                    import json
                    call_data = json.loads(tool_match.group(1))
                    tool_name = call_data["tool"]
                    tool_args = call_data.get("arguments", {})

                    tc = ToolCall(name=tool_name, arguments=tool_args, tool_call_id=new_urn_uuid())
                    tool_calls_made.append(tc)

                    tool_result_text = self.tool_registry.execute(tool_name, **tool_args)

                    all_messages.append({"role": "assistant", "content": content})
                    all_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "content": tool_result_text,
                    })
                    continue  # Let LLM respond to tool result
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    all_messages.append({"role": "assistant", "content": content})
                    all_messages.append({
                        "role": "user",
                        "content": f"Tool call parsing failed: {e}. Please respond directly.",
                    })
                    continue
            else:
                # No tool call — this is the final response
                return AgentResult(
                    session_id=session_id,
                    messages=all_messages + [{"role": "assistant", "content": content}],
                    tool_calls=tool_calls_made,
                    summary=content,
                    success=True,
                )

        return AgentResult(
            session_id=session_id,
            messages=all_messages,
            tool_calls=tool_calls_made,
            summary="Reached maximum iterations without final response.",
            success=False,
        )
