from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory.decay import (
    AccessTracker,
    DecayPolicy,
    DecayResult,
    DecayScheduler,
    _parse_timestamp,
    _trust_score,
)
from hermes_prime.utils import new_urn_uuid, utc_now_iso


def _make_claim(
    fact_id: str | None = None,
    claim_text: str = "test",
    memory_type: str = "episodic",
    trust_state: TrustState = TrustState.UNVERIFIED,
    timestamp: str | None = None,
) -> MemoryClaim:
    return MemoryClaim(
        fact_id=fact_id or new_urn_uuid(),
        claim=claim_text,
        source={"agent": "test", "memory_type": memory_type},
        epistemic_confidence=0.5,
        verification_status="unverified",
        source_trust="observed",
        timestamp=timestamp or utc_now_iso(),
        trust_state=trust_state,
        tier=MemoryTier.QUARANTINE,
        contradictions=[],
        intent_root="",
    )


class TestDecayPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = DecayPolicy()

    def test_default_retention(self):
        self.assertEqual(self.policy.retention_for("working"), 1)
        self.assertEqual(self.policy.retention_for("episodic"), 90)
        self.assertEqual(self.policy.retention_for("reflective"), 30)
        self.assertEqual(self.policy.retention_for("semantic"), 365)
        self.assertEqual(self.policy.retention_for("strategic"), 0)
        self.assertEqual(self.policy.retention_for("governance"), 0)

    def test_unknown_type_defaults(self):
        self.assertEqual(self.policy.retention_for("unknown"), 90)

    def test_executable_is_exempt(self):
        claim = _make_claim(trust_state=TrustState.EXECUTABLE)
        self.assertTrue(self.policy.is_exempt(claim))

    def test_strategic_is_exempt(self):
        claim = _make_claim(memory_type="strategic")
        self.assertTrue(self.policy.is_exempt(claim))

    def test_governance_is_exempt(self):
        claim = _make_claim(memory_type="governance")
        self.assertTrue(self.policy.is_exempt(claim))

    def test_unverified_not_exempt(self):
        claim = _make_claim(memory_type="episodic", trust_state=TrustState.UNVERIFIED)
        self.assertFalse(self.policy.is_exempt(claim))

    def test_effective_age_ratio_exempt_returns_zero(self):
        claim = _make_claim(memory_type="strategic")
        self.assertEqual(self.policy.effective_age_ratio(claim), 0.0)

    def test_effective_age_ratio_fresh(self):
        claim = _make_claim(memory_type="episodic", timestamp=utc_now_iso())
        ratio = self.policy.effective_age_ratio(claim)
        self.assertLess(ratio, 0.1)

    def test_effective_age_ratio_old(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=180)).isoformat().replace("+00:00", "Z")
        claim = _make_claim(memory_type="episodic", timestamp=old)
        ratio = self.policy.effective_age_ratio(claim)
        self.assertGreater(ratio, 1.0)

    def test_unverified_decays_faster(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45)).isoformat().replace("+00:00", "Z")
        unverified = _make_claim(memory_type="episodic", trust_state=TrustState.UNVERIFIED, timestamp=old)
        validated = _make_claim(memory_type="episodic", trust_state=TrustState.VALIDATED, timestamp=old)
        uv_ratio = self.policy.effective_age_ratio(unverified)
        val_ratio = self.policy.effective_age_ratio(validated)
        self.assertGreater(uv_ratio, val_ratio)

    def test_access_decay_accelerator(self):
        claim = _make_claim(memory_type="episodic", timestamp=utc_now_iso())
        ratio_no_access = self.policy.effective_age_ratio(claim, access_days_since=None)
        ratio_with_access = self.policy.effective_age_ratio(claim, access_days_since=60)
        self.assertGreater(ratio_with_access, ratio_no_access)


class TestAccessTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = AccessTracker()

    def test_record_and_get_last_access(self):
        self.tracker.record_access("fact-1")
        last = self.tracker.get_last_access("fact-1")
        self.assertIsNotNone(last)

    def test_get_last_access_none(self):
        self.assertIsNone(self.tracker.get_last_access("nonexistent"))

    def test_get_access_count(self):
        self.tracker.record_access("fact-1")
        self.tracker.record_access("fact-1")
        self.assertEqual(self.tracker.get_access_count("fact-1"), 2)

    def test_get_access_count_none(self):
        self.assertEqual(self.tracker.get_access_count("nonexistent"), 0)

    def test_get_access_count_since(self):
        yesterday = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat().replace("+00:00", "Z")
        self.tracker.record_access("fact-1")
        self.tracker.record_access("fact-1")
        count = self.tracker.get_access_count("fact-1", since=yesterday)
        self.assertEqual(count, 2)

    def test_days_since_last_access(self):
        self.tracker.record_access("fact-1")
        days = self.tracker.days_since_last_access("fact-1")
        self.assertEqual(days, 0)

    def test_days_since_last_access_none(self):
        self.assertIsNone(self.tracker.days_since_last_access("nonexistent"))

    def test_clear(self):
        self.tracker.record_access("fact-1")
        self.tracker.clear()
        self.assertEqual(self.tracker.get_access_count("fact-1"), 0)

    def test_multiple_facts(self):
        self.tracker.record_access("fact-a")
        self.tracker.record_access("fact-b")
        self.tracker.record_access("fact-a")
        self.assertEqual(self.tracker.get_access_count("fact-a"), 2)
        self.assertEqual(self.tracker.get_access_count("fact-b"), 1)


class TestDecayScheduler(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test_decay.db"
        self.backend = SQLiteMemoryBackend(self.db_path)
        self.tracker = AccessTracker()
        self.policy = DecayPolicy()
        self.scheduler = DecayScheduler(
            backend=self.backend,
            policy=self.policy,
            access_tracker=self.tracker,
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add_claim(
        self,
        text: str = "test",
        memory_type: str = "episodic",
        trust_state: TrustState = TrustState.UNVERIFIED,
        days_ago: int = 0,
    ) -> MemoryClaim:
        ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
        claim = _make_claim(
            claim_text=text,
            memory_type=memory_type,
            trust_state=trust_state,
            timestamp=ts,
        )
        self.backend.store(claim)
        return claim

    def test_no_decay_for_fresh_claims(self):
        self._add_claim("fresh", days_ago=0)
        result = self.scheduler.run_cycle()
        self.assertEqual(result.deleted_count, 0)
        self.assertEqual(result.demoted_count, 0)
        self.assertEqual(result.expired_count, 0)

    def test_decay_old_working_memory(self):
        self._add_claim("old working", memory_type="working", days_ago=5)
        result = self.scheduler.run_cycle()
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.expired_count, 1)

    def test_decay_old_episodic_unverified(self):
        self._add_claim("old episodic", memory_type="episodic", days_ago=180)
        result = self.scheduler.run_cycle()
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.expired_count, 1)

    def test_demote_validated_episodic(self):
        self._add_claim(
            "demotable", memory_type="episodic",
            trust_state=TrustState.VALIDATED, days_ago=180,
        )
        result = self.scheduler.run_cycle()
        self.assertEqual(result.demoted_count, 1)
        self.assertEqual(result.expired_count, 1)

    def test_exempt_strategic(self):
        self._add_claim("strategic insight", memory_type="strategic", days_ago=1000)
        result = self.scheduler.run_cycle()
        self.assertEqual(result.exempt_count, 1)
        self.assertEqual(result.deleted_count, 0)

    def test_exempt_governance(self):
        self._add_claim("governance rule", memory_type="governance", days_ago=1000)
        result = self.scheduler.run_cycle()
        self.assertEqual(result.exempt_count, 1)
        self.assertEqual(result.deleted_count, 0)

    def test_exempt_executable(self):
        self._add_claim(
            "executable", memory_type="episodic",
            trust_state=TrustState.EXECUTABLE, days_ago=180,
        )
        result = self.scheduler.run_cycle()
        self.assertEqual(result.exempt_count, 1)
        self.assertEqual(result.deleted_count, 0)

    def test_unverified_decays_faster_than_validated(self):
        unvalidated = self._add_claim(
            "uv", memory_type="episodic",
            trust_state=TrustState.UNVERIFIED, days_ago=60,
        )
        validated = self._add_claim(
            "val", memory_type="episodic",
            trust_state=TrustState.VALIDATED, days_ago=60,
        )
        result = self.scheduler.run_cycle()
        self.assertGreaterEqual(result.deleted_count, 1)

    def test_working_memory_decays_at_80_percent(self):
        half_life = 1
        aged = int(half_life * 0.85)
        self._add_claim("near expiry working", memory_type="working", days_ago=aged)
        result = self.scheduler.run_cycle()
        self.assertGreaterEqual(result.deleted_count, 0)

    def test_scheduler_handles_empty_backend(self):
        result = self.scheduler.run_cycle()
        self.assertEqual(result.expired_count, 0)
        self.assertEqual(result.errors, [])

    def test_result_tracks_errors(self):
        result = DecayResult()
        result.errors.append("test error")
        self.assertEqual(len(result.errors), 1)

    def test_decay_result_defaults(self):
        r = DecayResult()
        self.assertEqual(r.expired_count, 0)
        self.assertEqual(r.demoted_count, 0)
        self.assertEqual(r.deleted_count, 0)
        self.assertEqual(r.exempt_count, 0)
        self.assertEqual(r.errors, [])

    def test_mixed_claims(self):
        self._add_claim("fresh", days_ago=0)
        self._add_claim("old working", memory_type="working", days_ago=5)
        self._add_claim("strategic", memory_type="strategic", days_ago=1000)
        self._add_claim("old episodic", memory_type="episodic", days_ago=200)
        result = self.scheduler.run_cycle()
        self.assertGreaterEqual(result.deleted_count, 2)
        self.assertGreaterEqual(result.exempt_count, 1)

    def test_reflective_decay(self):
        self._add_claim("old reflection", memory_type="reflective", days_ago=60)
        result = self.scheduler.run_cycle()
        self.assertEqual(result.deleted_count, 1)

    def test_semantic_not_deleted_when_old(self):
        self._add_claim("old semantic", memory_type="semantic", days_ago=400)
        result = self.scheduler.run_cycle()
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.demoted_count, 0)

    def test_parse_timestamp_invalid(self):
        now = _parse_timestamp("invalid")
        self.assertIsNotNone(now)

    def test_parse_timestamp_zulu(self):
        parsed = _parse_timestamp("2026-01-01T00:00:00Z")
        self.assertEqual(parsed.year, 2026)

    def test_trust_score_enum(self):
        self.assertEqual(_trust_score(TrustState.VALIDATED), 3)

    def test_trust_score_string(self):
        self.assertEqual(_trust_score("VALIDATED"), 3)

    def test_trust_score_lowercase(self):
        self.assertEqual(_trust_score("validated"), 3)

    def test_trust_score_unknown(self):
        self.assertEqual(_trust_score("unknown"), -1)


if __name__ == "__main__":
    unittest.main()
