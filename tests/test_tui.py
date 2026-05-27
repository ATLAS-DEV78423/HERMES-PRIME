from __future__ import annotations

import unittest

from hermes_prime.tui.banner import (
    FILE_MINERS_LOGO,
    HEAVY_DIVIDER,
    HERMES_PRIME_LOGO,
    HERMES_PRIME_LOGO_SMALL,
    NEURAL_FABRIC,
    SENTINEL_SHIELD,
    TACTICAL_DIVIDER,
    THIN_DIVIDER,
)
from hermes_prime.tui.components import (
    AgentMeshVisualizer,
    OperatorConsole,
    StatusPill,
    TelemetryHeader,
    divider_heavy,
    divider_tactical,
    divider_thin,
)
from hermes_prime.tui.theme import HERMES_THEME, HermesColor, HermesStyle


class ThemeTests(unittest.TestCase):
    def test_hermes_color_constants(self) -> None:
        self.assertEqual(HermesColor.CYAN, "cyan")
        self.assertEqual(HermesColor.AMBER, "yellow")
        self.assertEqual(HermesColor.RED, "red")

    def test_hermes_style_defaults(self) -> None:
        style = HermesStyle()
        self.assertEqual(style.core_signal, "bold cyan")
        self.assertEqual(style.governance, "bold white")

    def test_hermes_theme_dict(self) -> None:
        self.assertIn("core_signal", HERMES_THEME)
        self.assertIn("governance", HERMES_THEME)
        self.assertEqual(HERMES_THEME["critical"], "bold red")


class BannerTests(unittest.TestCase):
    def test_logo_not_empty(self) -> None:
        self.assertTrue(len(HERMES_PRIME_LOGO.strip()) > 0)
        self.assertIn("\u2588", HERMES_PRIME_LOGO)

    def test_logo_small_not_empty(self) -> None:
        self.assertTrue(len(HERMES_PRIME_LOGO_SMALL.strip()) > 0)

    def test_sentinel_shield_contains_text(self) -> None:
        self.assertIn("SENTINEL", SENTINEL_SHIELD)
        self.assertIn("GOVERNANCE", SENTINEL_SHIELD)

    def test_file_miners_logo_not_empty(self) -> None:
        self.assertTrue(len(FILE_MINERS_LOGO.strip()) > 0)
        self.assertIn("\u2588", FILE_MINERS_LOGO)

    def test_neural_fabric_contains_hermes(self) -> None:
        self.assertIn("HERMES", NEURAL_FABRIC)
        self.assertIn("FABRIC", NEURAL_FABRIC)

    def test_dividers_not_empty(self) -> None:
        self.assertTrue(len(TACTICAL_DIVIDER) > 0)
        self.assertTrue(len(HEAVY_DIVIDER) > 0)
        self.assertTrue(len(THIN_DIVIDER) > 0)
        self.assertNotEqual(TACTICAL_DIVIDER, HEAVY_DIVIDER)


class ComponentsTests(unittest.TestCase):
    def test_divider_thin_uses_unicode(self) -> None:
        d = divider_thin(length=20)
        self.assertEqual(len(d), 20)
        self.assertEqual(d[0], "\u2500")

    def test_divider_heavy_uses_unicode(self) -> None:
        d = divider_heavy(length=30)
        self.assertEqual(len(d), 30)
        self.assertEqual(d[0], "\u2550")

    def test_divider_tactical(self) -> None:
        d = divider_tactical(length=30)
        self.assertTrue(len(d) > 0)

    def test_status_pill_render(self) -> None:
        pill = StatusPill(label="SENTINEL", status="ONLINE")
        rendered = pill.render()
        self.assertIn("SENTINEL", rendered)
        self.assertIn("ONLINE", rendered)

    def test_operator_console_render(self) -> None:
        console = OperatorConsole()
        rendered = console.render()
        self.assertIn("HERMES-PRIME", rendered)
        self.assertIn("OPERATOR CONSOLE", rendered)
        self.assertIn("STATUS", rendered)
        self.assertIn("ACTIVE", rendered)
        self.assertIn("GOVERNANCE", rendered)
        self.assertIn("SENTINEL", rendered)
        self.assertIn("MEMORY FABRIC", rendered)
        self.assertIn("AGENT MESH", rendered)

    def test_operator_console_custom_values(self) -> None:
        console = OperatorConsole(
            status="WARNING",
            governance="UNLOCKED",
            sentinel="DEGRADED",
            memory_fabric="REBUILDING",
            agent_mesh="DESYNC",
        )
        r = console.render()
        self.assertIn("WARNING", r)
        self.assertIn("UNLOCKED", r)
        self.assertIn("DEGRADED", r)

    def test_operator_console_to_dict(self) -> None:
        console = OperatorConsole()
        d = console.to_dict()
        self.assertEqual(d["status"], "ACTIVE")
        self.assertEqual(d["governance"], "LOCKED")

    def test_telemetry_header_render(self) -> None:
        telemetry = TelemetryHeader()
        rendered = telemetry.render()
        self.assertIn("LIVE TELEMETRY", rendered)
        self.assertIn("AGENTS", rendered)
        self.assertIn("GOVERNANCE", rendered)
        self.assertIn("THREAT SCORE", rendered)

    def test_telemetry_custom_values(self) -> None:
        telemetry = TelemetryHeader(
            agents=12,
            task_queue=148,
            latency_ms=11.0,
            memory_load=41.0,
            governance="STABLE",
            threat_score=0.002,
        )
        rendered = telemetry.render()
        self.assertIn("12", rendered)
        self.assertIn("148", rendered)
        self.assertIn("11ms", rendered)
        self.assertIn("41%", rendered)
        self.assertIn("STABLE", rendered)

    def test_telemetry_to_dict(self) -> None:
        telemetry = TelemetryHeader(agents=5, latency_ms=22.5)
        d = telemetry.to_dict()
        self.assertEqual(d["agents"], 5)
        self.assertEqual(d["latency_ms"], 22.5)

    def test_agent_mesh_viz_empty(self) -> None:
        viz = AgentMeshVisualizer()
        rendered = viz.render()
        self.assertIn("STANDBY", rendered)
        self.assertIn("ORCHESTRATOR", rendered)

    def test_agent_mesh_viz_with_agents(self) -> None:
        agents = [
            {"agent_id": "urn:uuid:a1", "depth": 0, "status": "running"},
            {"agent_id": "urn:uuid:b1", "depth": 1, "status": "running"},
        ]
        viz = AgentMeshVisualizer(agents=agents)
        rendered = viz.render()
        self.assertIn("ORCHESTRATOR", rendered)
        self.assertIn("MESH STATUS", rendered)

    def test_agent_mesh_viz_to_dict(self) -> None:
        viz = AgentMeshVisualizer(agents=[{"agent_id": "a"}])
        d = viz.to_dict()
        self.assertEqual(d["count"], 1)


class HermesConsoleTests(unittest.TestCase):
    def setUp(self) -> None:
        from hermes_prime.tui.console import HermesConsole

        self.console = HermesConsole(use_rich=False)

    def test_print_logo(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            self.console.print_logo()
            output = captured.getvalue()
            self.assertTrue(len(output.strip()) > 0)
        finally:
            sys.stdout = old_stdout

    def test_print_status(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            self.console.print_status("SENTINEL", "ONLINE")
            output = captured.getvalue()
            self.assertIn("SENTINEL", output)
            self.assertIn("ONLINE", output)
        finally:
            sys.stdout = old_stdout

    def test_print_error(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            self.console.print_error("test error")
            output = captured.getvalue()
            self.assertIn("ERROR", output)
            self.assertIn("test error", output)
        finally:
            sys.stdout = old_stdout

    def test_print_success(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            self.console.print_success("done")
            output = captured.getvalue()
            self.assertIn("OK", output)
        finally:
            sys.stdout = old_stdout


class AnimationsTests(unittest.TestCase):
    def test_pulse_loader_output(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            from hermes_prime.tui.animations import pulse_loader

            pulse_loader(label="TEST", steps=2, delay=0.01)
            output = captured.getvalue()
            self.assertTrue(len(output) > 0)
        finally:
            sys.stdout = old_stdout

    def test_typewriter_output(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            from hermes_prime.tui.animations import typewriter

            typewriter("hello", delay=0.001)
            output = captured.getvalue()
            self.assertIn("hello", output)
        finally:
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
