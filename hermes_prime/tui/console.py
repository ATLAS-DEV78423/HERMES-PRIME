from __future__ import annotations

from typing import Any

from .banner import HERMES_PRIME_LOGO
from .components import OperatorConsole, TelemetryHeader, divider_heavy, divider_thin


class HermesConsole:
    def __init__(self, use_rich: bool = True) -> None:
        self._use_rich = use_rich
        self._rich_console = None
        if use_rich:
            try:
                from rich.console import Console

                self._rich_console = Console()
            except ImportError:
                self._rich_console = None
                self._use_rich = False

    def print(self, text: str = "", style: str | None = None) -> None:
        if self._rich_console and style:
            from rich.text import Text

            self._rich_console.print(Text(text, style=style))
        else:
            print(text)

    def print_logo(self) -> None:
        if self._rich_console:
            from rich.text import Text

            logo = Text(HERMES_PRIME_LOGO, style="bold cyan")
            self._rich_console.print(logo)
        else:
            print(HERMES_PRIME_LOGO)

    def print_header(self, text: str) -> None:
        self.print(divider_heavy(), style="grey62")
        self.print(text, style="bold white")
        self.print(divider_heavy(), style="grey62")

    def print_section(self, text: str) -> None:
        self.print(divider_thin(), style="grey62")
        self.print(text, style="bold cyan")
        self.print(divider_thin(), style="grey62")

    def print_operator_console(
        self,
        status: str = "ACTIVE",
        governance: str = "LOCKED",
        sentinel: str = "ONLINE",
        memory_fabric: str = "STABLE",
        agent_mesh: str = "SYNCHRONIZED",
    ) -> None:
        console = OperatorConsole(
            status=status,
            governance=governance,
            sentinel=sentinel,
            memory_fabric=memory_fabric,
            agent_mesh=agent_mesh,
        )
        if self._rich_console:
            from rich.text import Text

            for line in console.render().split("\n"):
                styled = Text(line, style="bold cyan" if "HERMES-PRIME" in line else "grey62")
                self._rich_console.print(styled)
        else:
            print(console.render())

    def print_telemetry(
        self,
        agents: int = 0,
        task_queue: int = 0,
        latency_ms: float = 0.0,
        memory_load: float = 0.0,
        governance: str = "STABLE",
        threat_score: float = 0.0,
    ) -> None:
        telemetry = TelemetryHeader(
            agents=agents,
            task_queue=task_queue,
            latency_ms=latency_ms,
            memory_load=memory_load,
            governance=governance,
            threat_score=threat_score,
        )
        if self._rich_console:
            from rich.text import Text

            for line in telemetry.render().split("\n"):
                styled = Text(line, style="bold cyan" if "HERMES-PRIME" in line else "grey62")
                self._rich_console.print(styled)
        else:
            print(telemetry.render())

    def print_status(self, label: str, status: str) -> None:
        color_map = {
            "ACTIVE": "bold cyan",
            "ONLINE": "bold green",
            "LOCKED": "bold white",
            "STABLE": "bold green",
            "WARNING": "bold yellow",
            "CRITICAL": "bold red",
        }
        style = color_map.get(status.upper(), "white")
        self.print(f"[ {label} :: {status} ]", style=style)

    def print_prompt(self) -> None:
        self.print("\n[HERMES|OPS]> ", style="bold cyan", end="")

    def print_error(self, message: str) -> None:
        self.print(f"[ ERROR ] {message}", style="bold red")

    def print_success(self, message: str) -> None:
        self.print(f"[ OK ] {message}", style="bold green")

    def print_warning(self, message: str) -> None:
        self.print(f"[ WARNING ] {message}", style="bold yellow")

    def print_table(self, title: str, data: list[dict[str, Any]], columns: list[str]) -> None:
        if self._rich_console:
            from rich.table import Table

            table = Table(title=title, border_style="grey62")
            for col in columns:
                table.add_column(col, style="cyan", header_style="bold white")
            for row in data:
                table.add_row(*[str(row.get(c, "")) for c in columns])
            self._rich_console.print(table)
        else:
            self.print_header(title)
            header = " | ".join(columns)
            self.print(header)
            self.print(divider_thin(), style="grey62")
            for row in data:
                self.print(" | ".join(str(row.get(c, "")) for c in columns))
