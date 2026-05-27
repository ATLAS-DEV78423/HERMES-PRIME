from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from hermes_prime.contracts import (
    FabricAugmentation,
    FabricPatternMatch,
    PatternClassification,
)
from hermes_prime.utils import new_urn_uuid, read_text_safe, utc_now_iso


@dataclass
class FabricPatternCatalogEntry:
    name: str
    path: Path
    hash: str
    tags: list[str]
    content: str


class FabricPatternCatalog:
    def __init__(self, fabric_root: str | Path) -> None:
        self.fabric_root = Path(fabric_root).resolve()
        self.pattern_root = self.fabric_root / "data" / "patterns"

    def entries(self) -> list[FabricPatternCatalogEntry]:
        entries: list[FabricPatternCatalogEntry] = []
        if not self.pattern_root.exists():
            return entries
        for folder in sorted(self.pattern_root.iterdir(), key=lambda p: p.name):
            if not folder.is_dir():
                continue
            content = self._read_folder(folder)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            tags = self._derive_tags(folder.name, content)
            entries.append(
                FabricPatternCatalogEntry(
                    name=folder.name,
                    path=folder,
                    hash="sha256:" + digest,
                    tags=tags,
                    content=content,
                )
            )
        return entries

    def _read_folder(self, folder: Path) -> str:
        chunks = []
        for name in ("system.md", "user.md", "README.md", "readme.md"):
            candidate = folder / name
            if candidate.exists():
                chunks.append(read_text_safe(candidate))
        return "\n".join(chunks)

    def _derive_tags(self, name: str, content: str) -> list[str]:
        tokens = set(name.replace("-", "_").split("_"))
        low = content.lower()
        if any(k in low for k in ("security", "threat", "exploit", "credential", "secret")):
            tokens.update({"security", "audit", "defensive"})
        if any(k in low for k in ("summarize", "summary", "extract", "analysis")):
            tokens.update({"analysis", "summarization"})
        if any(k in low for k in ("review", "compare", "check", "falsifiability")):
            tokens.update({"review", "validation"})
        return sorted(tokens)


class PatternClassificationMiner:
    def classify(self, prompt: str) -> PatternClassification:
        text = prompt.lower()
        task_types = ["general"]
        recommended: list[str] = ["general"]
        domain = "general"
        confidence = 0.5
        if any(k in text for k in ("security", "threat", "vulnerability", "exploit", "secret")):
            task_types = ["security-audit", "code-review"]
            recommended = ["security", "audit", "defensive"]
            domain = "security"
            confidence = 0.9
        elif any(k in text for k in ("summarize", "summary", "explain", "analyze")):
            task_types = ["analysis", "summarization"]
            recommended = ["analysis", "summarization"]
            domain = "analysis"
            confidence = 0.82
        elif any(k in text for k in ("patch", "fix", "implement", "refactor")):
            task_types = ["implementation", "code-change"]
            recommended = ["code", "implementation", "refactor"]
            domain = "code"
            confidence = 0.8
        return PatternClassification(
            classification_id=new_urn_uuid(),
            task_types=task_types,
            domain=domain,
            recommended_pattern_tags=recommended,
            confidence=confidence,
            classified_at=utc_now_iso(),
        )


class PatternMiner:
    def __init__(self, catalog: FabricPatternCatalog) -> None:
        self.catalog = catalog

    def match(
        self, classification: PatternClassification, limit: int = 5
    ) -> list[FabricPatternMatch]:
        entries = self.catalog.entries()
        scored: list[tuple[float, FabricPatternCatalogEntry]] = []
        wanted = set(classification.recommended_pattern_tags + classification.task_types)
        for entry in entries:
            score = len(wanted.intersection(entry.tags))
            if score:
                scored.append((score + classification.confidence, entry))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        matches: list[FabricPatternMatch] = []
        for score, entry in scored[:limit]:
            matches.append(
                FabricPatternMatch(
                    match_id=new_urn_uuid(),
                    pattern_name=entry.name,
                    pattern_hash=entry.hash,
                    fabric_version="local-snapshot",
                    retrieval_time=utc_now_iso(),
                    confidence=min(0.99, score / 4.0),
                    reasoning_style=self._reasoning_style(entry),
                    required_checks=self._required_checks(entry),
                    output_structure=["findings", "severity", "remediation"],
                    tags=entry.tags,
                )
            )
        return matches

    def _reasoning_style(self, entry: FabricPatternCatalogEntry) -> list[str]:
        if "security" in entry.tags or "audit" in entry.tags:
            return ["adversarial", "defensive", "exploit-aware"]
        if "summarization" in entry.tags:
            return ["concise", "evidence-based"]
        return ["structured", "evidence-based"]

    def _required_checks(self, entry: FabricPatternCatalogEntry) -> list[str]:
        if "security" in entry.tags:
            return ["credential leakage", "shell injection", "path traversal"]
        if "review" in entry.tags:
            return ["consistency", "missing references"]
        return ["evidence", "scope"]


class PatternInjectionMiner:
    def inject(self, matches: list[FabricPatternMatch]) -> FabricAugmentation:
        pattern_hashes = {match.pattern_name: match.pattern_hash for match in matches}
        reasoning_style = []
        required_checks = []
        tags = []
        for match in matches:
            reasoning_style.extend(match.reasoning_style)
            required_checks.extend(match.required_checks)
            tags.extend(match.tags)
        reasoning_style = sorted(set(reasoning_style))
        required_checks = sorted(set(required_checks))
        augmentation = FabricAugmentation(
            augmentation_id=new_urn_uuid(),
            source_patterns=[match.pattern_name for match in matches],
            reasoning_style=reasoning_style,
            required_checks=required_checks,
            output_structure={
                "format": "structured",
                "required_sections": ["findings", "severity", "remediation"],
            },
            constraints=[
                "Do not recommend actions outside current capability scope.",
                "Treat Fabric guidance as heuristic only.",
            ],
            authority="heuristic_guidance_only",
            generated_at=utc_now_iso(),
            pattern_hashes=pattern_hashes,
        )
        return augmentation
