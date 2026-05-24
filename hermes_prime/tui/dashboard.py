from __future__ import annotations

from typing import ClassVar

from .banner import HERMES_PRIME_LOGO_SMALL, SENTINEL_SHIELD


class HermesDashboard:
    def __init__(self, use_textual: bool = True) -> None:
        self._use_textual = use_textual

    def run(self) -> int:
        if self._use_textual:
            try:
                return self._run_textual()
            except ImportError:
                self._use_textual = False
        return self._run_static()

    def _run_textual(self) -> int:
        from textual.app import App, ComposeResult
        from textual.containers import Container
        from textual.widgets import Header, Footer, Static

        class HermesApp(App):
            CSS: ClassVar[str] = """
            Screen {
                background: black;
            }
            Header {
                background: black;
                color: cyan;
            }
            Footer {
                background: black;
                color: grey62;
            }
            #logo {
                color: cyan;
                text-align: center;
                margin: 1;
            }
            #operator-console {
                color: grey62;
                margin: 1 2;
            }
            #telemetry {
                color: grey62;
                margin: 1 2;
            }
            #status-line {
                color: green;
                text-align: center;
                margin: 1;
            }
            #sentinel-shield {
                color: yellow;
                text-align: center;
                margin: 1;
            }
            .label {
                color: grey62;
            }
            .value {
                color: white;
            }
            .divider {
                color: grey35;
            }
            """

            def compose(self) -> ComposeResult:
                yield Header(show_clock=True)
                yield Container(
                    Static(HERMES_PRIME_LOGO_SMALL, id="logo"),
                    Static("Sovereign Cognitive Infrastructure", id="status-line"),
                    Static("", classes="divider"),
                    Static(self._build_operator_console(), id="operator-console"),
                    Static("", classes="divider"),
                    Static(self._build_telemetry(), id="telemetry"),
                    Static("", classes="divider"),
                    Static(SENTINEL_SHIELD, id="sentinel-shield"),
                    Static("", classes="divider"),
                    Static("[ GOVERNANCE :: OPERATIONAL ]", id="status-line"),
                )
                yield Footer()

            def _build_operator_console(self) -> str:
                return (
                    "\u250c" + "\u2500" * 45 + "\u2510\n"
                    "\u2502 HERMES-PRIME :: OPERATOR CONSOLE           \u2502\n"
                    "\u251c" + "\u2500" * 45 + "\u2524\n"
                    "\u2502 STATUS        :: ACTIVE                    \u2502\n"
                    "\u2502 GOVERNANCE    :: LOCKED                    \u2502\n"
                    "\u2502 SENTINEL      :: ONLINE                    \u2502\n"
                    "\u2502 MEMORY FABRIC :: STABLE                    \u2502\n"
                    "\u2502 AGENT MESH    :: SYNCHRONIZED              \u2502\n"
                    "\u2514" + "\u2500" * 45 + "\u2518"
                )

            def _build_telemetry(self) -> str:
                return (
                    "\u250c" + "\u2500" * 45 + "\u2510\n"
                    "\u2502 HERMES-PRIME :: LIVE TELEMETRY            \u2502\n"
                    "\u251c" + "\u2500" * 45 + "\u2524\n"
                    "\u2502 AGENTS        : 0                         \u2502\n"
                    "\u2502 TASK QUEUE    : 0                         \u2502\n"
                    "\u2502 LATENCY       : 0ms                       \u2502\n"
                    "\u2502 MEMORY LOAD   : 0%                        \u2502\n"
                    "\u2502 GOVERNANCE    : STABLE                    \u2502\n"
                    "\u2502 THREAT SCORE  : 0.000                     \u2502\n"
                    "\u2514" + "\u2500" * 45 + "\u2518"
                )

            def on_mount(self) -> None:
                self.set_interval(2, self._refresh_telemetry)

            def _refresh_telemetry(self) -> None:
                import random
                telemetry = self.query_one("#telemetry", Static)
                agents = random.randint(0, 20)
                queue = random.randint(0, 200)
                latency = random.uniform(5, 50)
                mem = random.uniform(20, 80)
                threat = random.uniform(0.0, 0.01)
                telemetry.update(self._build_telemetry_dynamic(agents, queue, latency, mem, threat))

            def _build_telemetry_dynamic(self, agents: int, queue: int, latency: float, mem: float, threat: float) -> str:
                return (
                    "\u250c" + "\u2500" * 45 + "\u2510\n"
                    "\u2502 HERMES-PRIME :: LIVE TELEMETRY            \u2502\n"
                    "\u251c" + "\u2500" * 45 + "\u2524\n"
                    f"\u2502 AGENTS        : {agents:<30}\u2502\n"
                    f"\u2502 TASK QUEUE    : {queue:<30}\u2502\n"
                    f"\u2502 LATENCY       : {latency:.0f}ms{' ' * 27}\u2502\n"
                    f"\u2502 MEMORY LOAD   : {mem:.0f}%{' ' * 28}\u2502\n"
                    "\u2502 GOVERNANCE    : STABLE                    \u2502\n"
                    f"\u2502 THREAT SCORE  : {threat:<6.3f}{' ' * 24}\u2502\n"
                    "\u2514" + "\u2500" * 45 + "\u2518"
                )

        app = HermesApp()
        return app.run()

    def _run_static(self) -> int:
        print(HERMES_PRIME_LOGO_SMALL)
        print("Sovereign Cognitive Infrastructure")
        print()
        print(self._build_static_console())
        print()
        print(self._build_static_telemetry())
        print()
        print("[ GOVERNANCE :: OPERATIONAL ]")
        return 0

    def _build_static_console(self) -> str:
        return (
            "\u250c" + "\u2500" * 45 + "\u2510\n"
            "\u2502 HERMES-PRIME :: OPERATOR CONSOLE           \u2502\n"
            "\u251c" + "\u2500" * 45 + "\u2524\n"
            "\u2502 STATUS        :: ACTIVE                    \u2502\n"
            "\u2502 GOVERNANCE    :: LOCKED                    \u2502\n"
            "\u2502 SENTINEL      :: ONLINE                    \u2502\n"
            "\u2502 MEMORY FABRIC :: STABLE                    \u2502\n"
            "\u2502 AGENT MESH    :: SYNCHRONIZED              \u2502\n"
            "\u2514" + "\u2500" * 45 + "\u2518"
        )

    def _build_static_telemetry(self) -> str:
        return (
            "\u250c" + "\u2500" * 45 + "\u2510\n"
            "\u2502 HERMES-PRIME :: LIVE TELEMETRY            \u2502\n"
            "\u251c" + "\u2500" * 45 + "\u2524\n"
            "\u2502 AGENTS        : 0                         \u2502\n"
            "\u2502 TASK QUEUE    : 0                         \u2502\n"
            "\u2502 LATENCY       : 0ms                       \u2502\n"
            "\u2502 MEMORY LOAD   : 0%                        \u2502\n"
            "\u2502 GOVERNANCE    : STABLE                    \u2502\n"
            "\u2502 THREAT SCORE  : 0.000                     \u2502\n"
            "\u2514" + "\u2500" * 45 + "\u2518"
        )
