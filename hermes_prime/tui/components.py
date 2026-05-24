from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any



def divider_thin(length: int | None = None) -> str:
    width = length or shutil.get_terminal_size().columns
    return "\u2500" * width


def divider_heavy(length: int | None = None) -> str:
    width = length or shutil.get_terminal_size().columns
    return "\u2550" * width


def divider_tactical(length: int | None = None) -> str:
    width = (length or shutil.get_terminal_size().columns) // 2
    return "\u2593\u2591\u2592" * (width // 3)


@dataclass
class StatusPill:
    label: str
    status: str

    def render(self) -> str:
        return f"[ {self.label} :: {self.status} ]"

    def render_rich(self) -> str:
        color_map = {
            "ACTIVE": "bold cyan",
            "ONLINE": "bold green",
            "LOCKED": "bold white",
            "STABLE": "bold green",
            "WARNING": "bold yellow",
            "CRITICAL": "bold red",
            "FAILED": "bold red",
            "PENDING": "grey62",
            "RUNNING": "bold cyan",
            "COMPLETED": "bold green",
        }
        style = color_map.get(self.status.upper(), "white")
        return f"[{style}]{self.label} :: {self.status}[/]"


@dataclass
class OperatorConsole:
    status: str = "ACTIVE"
    governance: str = "LOCKED"
    sentinel: str = "ONLINE"
    memory_fabric: str = "STABLE"
    agent_mesh: str = "SYNCHRONIZED"

    def render(self) -> str:
        width = 47
        lines = [
            "\u250c" + "\u2500" * width + "\u2510",
            f"\u2502 HERMES-PRIME :: OPERATOR CONSOLE{' ' * (width - 35)}\u2502",
            "\u251c" + "\u2500" * width + "\u2524",
            f"\u2502 STATUS        :: {self.status:<29}\u2502",
            f"\u2502 GOVERNANCE    :: {self.governance:<29}\u2502",
            f"\u2502 SENTINEL      :: {self.sentinel:<29}\u2502",
            f"\u2502 MEMORY FABRIC :: {self.memory_fabric:<29}\u2502",
            f"\u2502 AGENT MESH    :: {self.agent_mesh:<29}\u2502",
            "\u2514" + "\u2500" * width + "\u2518",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "governance": self.governance,
            "sentinel": self.sentinel,
            "memory_fabric": self.memory_fabric,
            "agent_mesh": self.agent_mesh,
        }


@dataclass
class TelemetryHeader:
    agents: int = 0
    task_queue: int = 0
    latency_ms: float = 0.0
    memory_load: float = 0.0
    governance: str = "STABLE"
    threat_score: float = 0.0

    def render(self) -> str:
        width = 58
        lines = [
            "\u250c" + "\u2500" * width + "\u2510",
            f"\u2502 HERMES-PRIME :: LIVE TELEMETRY{' ' * (width - 33)}\u2502",
            "\u251c" + "\u2500" * width + "\u2524",
            f"\u2502 AGENTS        : {self.agents:<6}{' ' * (width - 22)}\u2502",
            f"\u2502 TASK QUEUE    : {self.task_queue:<6}{' ' * (width - 22)}\u2502",
            f"\u2502 LATENCY       : {self.latency_ms:.0f}ms{' ' * (width - 22)}\u2502",
            f"\u2502 MEMORY LOAD   : {self.memory_load:.0f}%{' ' * (width - 22)}\u2502",
            f"\u2502 GOVERNANCE    : {self.governance:<6}{' ' * (width - 22)}\u2502",
            f"\u2502 THREAT SCORE  : {self.threat_score:<6.3f}{' ' * (width - 22)}\u2502",
            "\u2514" + "\u2500" * width + "\u2518",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents": self.agents,
            "task_queue": self.task_queue,
            "latency_ms": self.latency_ms,
            "memory_load": self.memory_load,
            "governance": self.governance,
            "threat_score": self.threat_score,
        }


class AgentMeshVisualizer:
    def __init__(self, agents: list[dict] | None = None) -> None:
        self._agents = agents or []

    def render(self) -> str:
        if not self._agents:
            return self._render_empty()
        return self._render_mesh()

    def _render_empty(self) -> str:
        return (
            "  [ORCHESTRATOR]\n"
            "       |\n"
            "     (idle)\n\n"
            "  MESH STATUS :: STANDBY"
        )

    def _render_mesh(self) -> str:
        agent_ids = [a.get("agent_id", "?")[:8] for a in self._agents]
        root_depth = min(a.get("depth", 0) for a in self._agents) if self._agents else 0

        depth_groups: dict[int, list[str]] = {}
        for a, aid in zip(self._agents, agent_ids):
            d = a.get("depth", 0)
            depth_groups.setdefault(d, []).append(f"[{aid}]")

        lines = ["  [ORCHESTRATOR]"]
        for d in sorted(depth_groups.keys()):
            indent = "    " * (d + 1)
            group = depth_groups[d]
            line = f"{indent}{'--'.join(group)}"
            if d == 0 and root_depth > 0:
                line = f"  [ROOT] -> {line}"
            lines.append(f"  {'|' if d == 0 else ' ' * 2}")
            lines.append(line)

        statuses = [a.get("status", "unknown") for a in self._agents]
        mesh_status = "SYNCHRONIZED" if all(s in ("running", "completed") for s in statuses) else "ACTIVE"
        lines.append(f"\n  MESH STATUS :: {mesh_status}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {"agents": self._agents, "count": len(self._agents)}
