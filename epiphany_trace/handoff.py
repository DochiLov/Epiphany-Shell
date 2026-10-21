"""Offline, allowlisted observer-health handoffs. No host or broker connection.

Packets are assertions by a named producer, not authenticated telemetry. This
module never executes packet content, makes network calls, or opens an observer
journal. Optional persistence uses a separate Epiphany trace ledger.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from uuid import UUID

from .graph import Record, TraceStore

SCHEMA = "epiphany.observer-health.v1"
MAX_BYTES = 16_384
PRODUCERS = {"chatgpt", "codex-cloud", "codex-local", "openclaw", "drift-observer"}
FIELDS = {"schema", "report_id", "producer", "subject", "observed_at", "evidence"}
EVIDENCE_FIELDS = {
    "process_state", "task_state", "phase", "heartbeat_at",
    "last_collection_at", "last_collection_result", "consecutive_failures",
    "stop_requested",
}
TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)


def _instant(value: object) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValueError("A timestamp must include seconds and an explicit timezone")
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid timestamp") from exc


def _exact_fields(value: object, fields: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        # Do not echo unknown keys or values: they may contain private material.
        raise ValueError("Unexpected or missing fields; use the normalized health schema")


def _choice(value: object, choices: set[str]) -> None:
    if not isinstance(value, str) or value not in choices:
        raise ValueError("Invalid normalized health value")


def validate_report(report: dict) -> dict:
    """Validate an explicit allowlist; return a detached copy, never raw logs."""
    _exact_fields(report, FIELDS)
    if report["schema"] != SCHEMA or report["subject"] != "drift-signal-observer":
        raise ValueError("Unsupported schema or subject")
    ident = report["report_id"]
    if not isinstance(ident, str):
        raise ValueError("report_id must be a canonical UUID")
    try:
        if str(UUID(ident)) != ident:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError("report_id must be a canonical UUID") from exc
    _choice(report["producer"], PRODUCERS)
    observed = _instant(report["observed_at"])
    evidence = report["evidence"]
    _exact_fields(evidence, EVIDENCE_FIELDS)
    _choice(evidence["process_state"], {"running", "stopped", "unknown"})
    _choice(evidence["task_state"], {"running", "ready", "disabled", "unknown"})
    _choice(evidence["phase"], {
        "collecting", "waiting_for_clock_window", "bounded_collection_complete",
        "stopped", "error", "unknown",
    })
    _choice(evidence["last_collection_result"], {"success", "failure", "unknown"})
    failures = evidence["consecutive_failures"]
    if failures is not None and (type(failures) is not int or not 0 <= failures <= 1_000_000):
        raise ValueError("consecutive_failures must be a nonnegative integer or null")
    stop = evidence["stop_requested"]
    if stop is not None and type(stop) is not bool:
        raise ValueError("stop_requested must be a boolean or null")
    for key in ("heartbeat_at", "last_collection_at"):
        if evidence[key] is not None and _instant(evidence[key]) > observed:
            raise ValueError("Evidence cannot postdate its observation")
    if evidence["last_collection_result"] != "unknown" and evidence["last_collection_at"] is None:
        raise ValueError("A collection result requires its observation timestamp")
    return json.loads(canonical_report(report))


def canonical_report(report: dict) -> str:
    return json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not allowed")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON values are not allowed")


def load_report(path: str | Path) -> dict:
    """Read one bounded normalized packet, not a runtime directory or database."""
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Health packet exceeds the size limit")
    try:
        parsed = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid health JSON") from exc
    return validate_report(parsed)


def assess_report(report: dict, *, received_at: str | None = None, max_age_seconds: int = 300) -> dict:
    """Evaluate freshness and reported conditions, not truth or overall health.

    Collection age is reported but not thresholded: a market-hours observer can
    legitimately wait between windows. No exchange calendar is implemented.
    """
    report = validate_report(report)
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86_400:
        raise ValueError("max_age_seconds must be an integer between 1 and 86400")
    received_at = datetime.now(timezone.utc).isoformat() if received_at is None else received_at
    now = _instant(received_at)
    observed = _instant(report["observed_at"])
    if observed > now:
        raise ValueError("Report is in the receiver's future; resolve clock disagreement")
    evidence = report["evidence"]
    age = (now - observed).total_seconds()
    heartbeat_age = None if evidence["heartbeat_at"] is None else (
        now - _instant(evidence["heartbeat_at"])
    ).total_seconds()
    collection_age = None if evidence["last_collection_at"] is None else (
        now - _instant(evidence["last_collection_at"])
    ).total_seconds()
    flags = []
    if age > max_age_seconds:
        flags.append("report_stale")
    if heartbeat_age is None:
        flags.append("heartbeat_unknown")
    elif heartbeat_age > max_age_seconds:
        flags.append("heartbeat_stale")
    if evidence["process_state"] != "running":
        flags.append("process_" + evidence["process_state"])
    if evidence["task_state"] in {"disabled", "unknown"}:
        flags.append("task_" + evidence["task_state"])
    if evidence["phase"] in {"error", "stopped", "unknown"}:
        flags.append("phase_" + evidence["phase"])
    if evidence["last_collection_result"] != "success":
        flags.append("collection_" + evidence["last_collection_result"])
    if evidence["consecutive_failures"] is None:
        flags.append("failure_count_unknown")
    elif evidence["consecutive_failures"] > 0:
        flags.append("reported_failures")
    if evidence["stop_requested"] is None:
        flags.append("stop_state_unknown")
    elif evidence["stop_requested"]:
        flags.append("stop_requested")
    return {
        "report_id": report["report_id"], "producer_claim": report["producer"],
        "observed_at": report["observed_at"], "received_at": received_at,
        "max_age_seconds": max_age_seconds, "report_age_seconds": age,
        "heartbeat_age_seconds": heartbeat_age, "collection_age_seconds": collection_age,
        "flags": flags, "provenance": "producer-declared; not authenticated",
        "assessment_scope": "packet freshness and reported conditions; not a live host check",
    }


def import_report(store: TraceStore, report: dict, *, received_at: str | None = None,
                  parent_ids: tuple[str, ...] = ()) -> tuple[Record, bool]:
    """Append once; exact replay is harmless, changed content under an ID fails.

    The receipt time belongs to the returned assessment, not the source event.
    Preserve the original packet/ID when relaying it between environments.
    """
    report = validate_report(report)
    assess_report(report, received_at=received_at)
    body = canonical_report(report)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    record = Record(
        event_id="health:" + report["report_id"], occurred_at=report["observed_at"],
        kind="observation", actor="handoff/" + report["producer"], statement=body,
        parent_ids=tuple(parent_ids), source_ref="handoff:sha256:" + digest,
    )
    try:
        existing = store.get(record.event_id)
    except KeyError:
        store.add(record)
        return record, True
    if existing != record:
        raise ValueError("Conflicting content or ancestry for an existing report ID")
    return existing, False


def _local_store() -> TraceStore:
    """Use a separate checkout-local ledger, never the live observer journal."""
    directory = Path(".local")
    path = directory / "epiphany_handoff.sqlite3"
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("Refusing a symlink for the local handoff ledger")
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as database:
            tables = {row[0] for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        if tables != {"records", "parents"}:
            raise ValueError("Existing file is not the expected trace ledger")
    directory.mkdir(exist_ok=True)
    return TraceStore(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="Normalized, reviewed health JSON")
    parser.add_argument("--max-age-seconds", type=int, default=300)
    parser.add_argument("--save", action="store_true", help="Write a separate .local trace ledger")
    args = parser.parse_args(argv)
    try:
        report = load_report(args.packet)
        assessment = assess_report(report, max_age_seconds=args.max_age_seconds)
        if args.save:
            store = _local_store()
            try:
                record, inserted = import_report(store, report, received_at=assessment["received_at"])
                assessment["event_id"] = record.event_id
                assessment["receipt"] = "inserted" if inserted else "already_present"
            finally:
                store.close()
        print(json.dumps(assessment, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error):
        # Raw decoder/OS/database exceptions may contain paths or packet values.
        print("Handoff rejected: check schema, timestamps, input access, or local ledger.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
