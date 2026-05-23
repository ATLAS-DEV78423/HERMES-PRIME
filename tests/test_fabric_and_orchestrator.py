from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.hermes_agent.orchestrator import HermesPrimeOrchestrator
from infrastructure.policy_engine.engine import PolicyContext, PolicyEngine
from infrastructure.vault.capabilities import CapabilityVault
from miners.fabric_miners.miners import (
    FabricPatternCatalog,
    PatternClassificationMiner,
    PatternInjectionMiner,
    PatternMiner,
)


class FabricAndOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.fabric_root = self.root / "external" / "fabric"
        pattern_root = self.fabric_root / "data" / "patterns" / "security-review"
        pattern_root.mkdir(parents=True)
        (pattern_root / "system.md").write_text(
            "# security review\ncheck secrets and shell injection\n",
            encoding="utf-8",
        )
        (self.root / "sample.txt").write_text("read this content", encoding="utf-8")

    def test_fabric_pipeline_returns_heuristic_metadata(self) -> None:
        classifier = PatternClassificationMiner()
        catalog = FabricPatternCatalog(self.fabric_root)
        miner = PatternMiner(catalog)
        injector = PatternInjectionMiner()
        classification = classifier.classify("security review shell injection")
        matches = miner.match(classification)
        augmentation = injector.inject(matches)
        self.assertEqual(classification.domain, "security")
        self.assertTrue(matches)
        self.assertEqual(augmentation.authority, "heuristic_guidance_only")

    def test_orchestrator_runs_with_bounded_authority(self) -> None:
        policy = PolicyEngine(PolicyContext(workspace_root=str(self.root)))
        vault = CapabilityVault()
        orchestrator = HermesPrimeOrchestrator(
            workspace_root=self.root,
            fabric_root=self.fabric_root,
            policy=policy,
            vault=vault,
        )
        result = orchestrator.run("read sample")
        self.assertTrue(result.decision["permitted"])
        self.assertEqual(result.action["action_type"], "filesystem.read")
        self.assertTrue(result.retrieval)
        self.assertEqual(result.augmentation["authority"], "heuristic_guidance_only")

    def test_orchestrator_enforces_recursion_ceiling(self) -> None:
        policy = PolicyEngine(PolicyContext(workspace_root=str(self.root)))
        vault = CapabilityVault()
        orchestrator = HermesPrimeOrchestrator(
            workspace_root=self.root,
            fabric_root=self.fabric_root,
            policy=policy,
            vault=vault,
        )
        orchestrator._depth = 1
        with self.assertRaises(RuntimeError):
            orchestrator.run("read sample")


if __name__ == "__main__":
    unittest.main()
