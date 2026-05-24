from __future__ import annotations

import importlib.util
import shutil
import tempfile

import pytest

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.utils import new_urn_uuid, utc_now_iso

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mempalace") is None,
    reason="mempalace not installed",
)


class TestMemPalaceBackend:
    def _make_backend(self):
        from hermes_prime.memory.backends.mempalace_backend import MemPalaceBackend
        db_dir = tempfile.mkdtemp(prefix="mempalace_test_")
        backend = MemPalaceBackend(palace_path=db_dir)
        return backend, db_dir

    def _make_claim(self, text: str = "Test memory content") -> MemoryClaim:
        return MemoryClaim(
            fact_id=new_urn_uuid(),
            claim=text,
            source={"agent": "test-agent", "type": "test"},
            epistemic_confidence=0.8,
            verification_status="unverified",
            source_trust="observed",
            timestamp=utc_now_iso(),
            trust_state=TrustState.UNVERIFIED,
            tier=MemoryTier.QUARANTINE,
            contradictions=[],
            intent_root="urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        )

    def test_store_and_get(self):
        backend, tmp_dir = self._make_backend()
        try:
            claim = self._make_claim()
            backend.store(claim)
            retrieved = backend.get(claim.fact_id)
            assert retrieved is not None
            assert retrieved.fact_id == claim.fact_id
            assert retrieved.claim == claim.claim
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_store_and_search(self):
        backend, tmp_dir = self._make_backend()
        try:
            claim = self._make_claim("Unique search term xyzzy")
            backend.store(claim)
            results = backend.search("xyzzy", limit=5)
            assert len(results) >= 1
            assert any(r.fact_id == claim.fact_id for r in results)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_nonexistent(self):
        backend, tmp_dir = self._make_backend()
        try:
            retrieved = backend.get("urn:uuid:nonexistent-0000-0000-0000-000000000000")
            assert retrieved is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_delete(self):
        backend, tmp_dir = self._make_backend()
        try:
            claim = self._make_claim()
            backend.store(claim)
            deleted = backend.delete(claim.fact_id)
            assert deleted is True
            assert backend.get(claim.fact_id) is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_delete_nonexistent(self):
        backend, tmp_dir = self._make_backend()
        try:
            deleted = backend.delete("urn:uuid:nonexistent-0000-0000-0000-000000000000")
            assert deleted is False
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_count(self):
        backend, tmp_dir = self._make_backend()
        try:
            assert backend.count() == 0
            backend.store(self._make_claim())
            assert backend.count() == 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_list_all(self):
        backend, tmp_dir = self._make_backend()
        try:
            claim = self._make_claim()
            backend.store(claim)
            all_claims = backend.list_all()
            assert len(all_claims) == 1
            assert all_claims[0].fact_id == claim.fact_id
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_gc(self):
        from datetime import datetime, timedelta, timezone
        backend, tmp_dir = self._make_backend()
        try:
            claim = self._make_claim()
            backend.store(claim)
            future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
            deleted = backend.gc(future)
            assert deleted == 1
            assert backend.count() == 0
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
