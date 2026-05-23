"""Learning run orchestrator: scan → parse → classify → redact → delta-detect."""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from totalrecall.catalogue.models import CatalogueSource
from totalrecall.learning.classifier import classify
from totalrecall.learning.models import (
    LearningDelta,
    LearningDeltaState,
    LearningDiscovery,
    LearningReport,
    LearningRun,
    LearningRunStatus,
    LearningScope,
    LearningTriggerType,
)
from totalrecall.learning.parser import extract_patterns
from totalrecall.learning.redactor import redact
from totalrecall.learning.scanner import scan_path


def run_learning(
    tenant_id: str,
    application_id: str,
    scope: LearningScope,
    previous_hashes: dict[str, str],
    trigger_type: LearningTriggerType = LearningTriggerType.MANUAL,
) -> LearningReport:
    """Execute a single learning run synchronously.

    previous_hashes: mapping of stable_key → content_hash from the prior run,
    used for delta detection. A stable_key is "{file_path}::{pattern_name}".
    """
    run_id = str(uuid.uuid4())
    root = Path(scope.path)

    if not root.exists():
        run = LearningRun(
            run_id=run_id,
            tenant_id=tenant_id,
            application_id=application_id,
            scope=scope,
            trigger_type=trigger_type,
            status=LearningRunStatus.FAILED,
            completed_at=datetime.now(UTC),
        )
        return LearningReport(
            run=run,
            discovered_count=0,
            changed_count=0,
            removed_count=0,
            unchanged_count=0,
            rejected_count=0,
            warnings=[f"Scope path does not exist: {scope.path}"],
        )

    scanned_files = scan_path(root)
    discoveries: list[LearningDiscovery] = []
    all_warnings: list[str] = []

    for file in scanned_files:
        patterns = extract_patterns(file.content, file.path, file.language)
        for pattern in patterns:
            redacted_excerpt, redaction_warnings = redact(pattern.source_excerpt)
            if redaction_warnings:
                all_warnings.extend(redaction_warnings)

            stable_key = f"{pattern.file_path}::{pattern.name}"
            content_hash = hashlib.md5(
                f"{pattern.pattern_type}::{redacted_excerpt}".encode(),
                usedforsecurity=False,
            ).hexdigest()

            prev_hash = previous_hashes.get(stable_key)
            if prev_hash is None:
                delta_state = LearningDeltaState.NEW
            elif prev_hash == content_hash:
                delta_state = LearningDeltaState.UNCHANGED
            else:
                delta_state = LearningDeltaState.CHANGED

            source = CatalogueSource(
                type="file_scan",
                reference=pattern.file_path,
                file_path=pattern.file_path,
                symbol_name=pattern.name,
            )

            discoveries.append(
                LearningDiscovery(
                    discovery_id=str(uuid.uuid4()),
                    discovery_type=classify(pattern),
                    delta=LearningDelta(
                        state=delta_state,
                        previous_hash=prev_hash,
                        current_hash=content_hash,
                    ),
                    summary=f"{pattern.pattern_type}: {pattern.name} ({file.language})",
                    source=source,
                    proposed_tags={
                        "pattern_type": pattern.pattern_type,
                        "language": pattern.language,
                        "file": pattern.file_path,
                    },
                    warnings=redaction_warnings,
                )
            )

    def _count(state: LearningDeltaState) -> int:
        return sum(1 for d in discoveries if d.delta.state == state)

    run = LearningRun(
        run_id=run_id,
        tenant_id=tenant_id,
        application_id=application_id,
        scope=scope,
        trigger_type=trigger_type,
        status=LearningRunStatus.COMPLETED,
        discoveries=discoveries,
        completed_at=datetime.now(UTC),
    )

    return LearningReport(
        run=run,
        discovered_count=_count(LearningDeltaState.NEW),
        changed_count=_count(LearningDeltaState.CHANGED),
        removed_count=0,
        unchanged_count=_count(LearningDeltaState.UNCHANGED),
        rejected_count=0,
        warnings=all_warnings,
    )
