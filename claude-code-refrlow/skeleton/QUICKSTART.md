# Quickstart — Refrlow Reference Implementation

## Install

```bash
cd claude-code-refrlow/skeleton
pip install -e .   # if a setup.py / pyproject.toml is provided
# or simply:
export PYTHONPATH=$(pwd)
```

Optional (recommended): install `ripgrep` for faster grep-miner.

```bash
# macOS
brew install ripgrep
# Debian/Ubuntu
sudo apt install ripgrep
```

## Run the tests

```bash
cd claude-code-refrlow/skeleton
pip install pytest
pytest tests/
```

## Minimal usage

```python
from refrlow import Dispatcher, DispatchPolicy
from refrlow.protocol import DispatchRequest, Scope, Budget
from refrlow.miners.file_miner import FileMiner
from refrlow.miners.grep_miner import GrepMiner
from refrlow.miners.ast_miner import AstMiner

WORKSPACE = "/path/to/your/project"

# Set up the dispatcher.
disp = Dispatcher(policy=DispatchPolicy(), workspace_root=WORKSPACE)
disp.register(FileMiner())
disp.register(GrepMiner())
disp.register(AstMiner())

# Begin a main-agent turn.
disp.begin_turn()

# Dispatch a request.
req = DispatchRequest(
    subagent="grep_miner",
    task="find_imports_of",
    params={"module": "@/lib/auth"},
    scope=Scope(root=WORKSPACE),
    budget=Budget(max_tokens=2000, ttl_seconds=10),
    justification="finding all import sites for the auth refactor",
)

report = disp.dispatch(req)

print(report.status)
print(report.result)
print(report.to_ingestion_text())  # what the main agent would receive
```

## Wiring into Claude Code

The dispatcher should be exposed to Claude Code as a single tool named
`refrlow.dispatch`. The tool's JSON schema mirrors `DispatchRequest`. Its
return shape mirrors `DispatchReport.to_dict()`.

```python
# Pseudocode — adapt to your Claude Code tool-registration mechanism.

def refrlow_dispatch_tool(payload: dict) -> dict:
    req = DispatchRequest(
        subagent=payload["subagent"],
        task=payload["task"],
        params=payload.get("params", {}),
        scope=Scope(**payload["scope"]),
        budget=Budget(**payload.get("budget", {})),
        justification=payload["justification"],
        expected_schema=payload.get("expected_schema", "default"),
        parent_request_id=payload.get("parent_request_id"),
    )
    report = dispatcher.dispatch(req)
    return report.to_dict()
```

Then drop `prompts/CLAUDE.md` into your project root (or `.claude/`) and
Claude Code will pick up the operating instructions automatically.

## Wiring in a real LLM-backed Summarizer

In `refrlow/miners/summarizer.py`, replace the `_call_llm()` stub with a
call to your provider. Critical: use `prompts/miner-system-prompt.md` as
the system prompt. Example sketch:

```python
import anthropic

_SYSTEM_PROMPT = open("claude-code-refrlow/prompts/miner-system-prompt.md").read()
_client = anthropic.Anthropic()

def _call_llm(file_content: str, max_words: int) -> str:
    resp = _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=max_words * 2,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Summarize the purpose of this file in at most "
                    f"{max_words} words. Output a JSON object with one "
                    f"key 'summary'.\n\n<file>\n{file_content}\n</file>"
                ),
            }
        ],
    )
    import json
    parsed = json.loads(resp.content[0].text)
    return parsed["summary"]
```

## Adding a new subagent class

1. Create a new file under `refrlow/miners/`.
2. Subclass `Miner`.
3. Set `class_name` and `tasks`.
4. Implement `execute()`.
5. Update `claude-code-refrlow/SUBAGENT_TAXONOMY.md` with the new class.
6. Register a class budget cap in `DispatchPolicy.max_budget_per_class`.
7. Add tests.
8. Justify the addition: does it have a single responsibility? Is it
   distinct from existing classes? Is it implementable deterministically
   when possible?

If you cannot answer those questions cleanly, the class should not be
added.

## What to monitor

In production, watch:

- `denied` rate per session — spikes indicate misuse or policy mismatch
- `truncated` rate — high values mean budgets are too tight
- `escalate` rate — investigate every one
- Per-turn token totals — confirm refrlow is actually saving tokens vs
  baseline direct-read behavior
- Per-class concurrency — confirm parallelism is being used

The audit sink in `Dispatcher.__init__` is your hook for these metrics.
Plug it into whatever observability you use.
