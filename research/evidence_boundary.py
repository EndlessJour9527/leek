"""Offline, fail-closed boundary for hash-bound research material, never orders.

`as_of` is the evidence cutoff, NOT a report's creation/decision time. Declared
publication/availability must precede the cutoff; forward-shadow capture must
also do so. Analysis can finish later, with monotone declared creation times.
Hashes and producer IDs check consistency, not truth, provenance authenticity,
actual independent authorship, or unseen/holdout status. No model is invoked.

CLI: python3 -m research.evidence_boundary INPUT.json (or - for stdin).
Exit 0 = structurally accepted research packet; 2 = abstain/review; 1 = invalid.
Canonical hashes use UTF-8 JSON, sorted keys, compact separators, ensure_ascii
False and allow_nan False. Array order and string spelling remain significant.
A packet/candidate hash omits only that object's own hash field. Evidence content
hashes cover the exact UTF-8 content string. Hashes are NOT signatures.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit


_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z")


class BoundaryError(ValueError):
    """A stable, non-content-echoing input validation failure."""

    def __init__(self, code: str, path: str, detail: str):
        super().__init__(detail)
        self.code, self.path, self.detail = code, path, detail


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_uri: str
    content: str
    published_at: datetime
    available_at: datetime
    captured_at: datetime
    content_sha256: str


@dataclass(frozen=True)
class EvidencePacket:
    packet_id: str
    run_id: str
    as_of: datetime
    created_at: datetime
    mode: str
    data_classification: str
    evidence: tuple[Evidence, ...]
    snapshot_sha256: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    producer_id: str
    created_at: datetime
    stance: str
    used_evidence_ids: frozenset[str]
    candidate_sha256: str


@dataclass(frozen=True)
class Challenge:
    challenge_id: str
    producer_id: str
    created_at: datetime
    disposition: str
    contradiction_count: int
    challenge_sha256: str


def _fail(code: str, path: str, detail: str) -> None:
    raise BoundaryError(code, path, detail)


def _json_value(value: Any, path: str = "$") -> None:
    """Reject Python-only values as well as JSON's nonstandard NaN extensions."""
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            _fail("NONFINITE_NUMBER", path, "numbers must be finite")
        return
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError:
            _fail("INVALID_UNICODE", path, "strings must encode as UTF-8")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _json_value(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail("INVALID_JSON_TYPE", path, "object keys must be strings")
            _json_value(key, path)
            _json_value(item, f"{path}.{key}")
        return
    _fail("INVALID_JSON_TYPE", path, "only JSON values are permitted")


def load_document(text: str) -> dict:
    """Parse strict JSON; never extract a stance or JSON fragment from free text."""
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                _fail("DUPLICATE_JSON_KEY", "$", "duplicate object key")
            out[key] = value
        return out

    def constant(_):
        _fail("NONFINITE_NUMBER", "$", "nonfinite JSON constants are forbidden")

    try:
        document = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (json.JSONDecodeError, UnicodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, BoundaryError):
            raise
        _fail("INVALID_JSON", "$", "expected one strict JSON document")
    _json_value(document)
    if type(document) is not dict:
        _fail("INVALID_JSON_TYPE", "$", "top-level input must be an object")
    return document


def canonical_sha256(value: Any) -> str:
    """Hash JSON data without altering strings, times or array order."""
    _json_value(value)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_sha256(content: str) -> str:
    _string(content, "content")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _object(value, keys, path):
    if type(value) is not dict:
        _fail("INVALID_TYPE", path, "expected an object")
    missing, unknown = set(keys) - value.keys(), value.keys() - set(keys)
    if missing:
        _fail("MISSING_FIELDS", path, "missing fields: " + ", ".join(sorted(missing)))
    if unknown:
        _fail("UNKNOWN_FIELDS", path, "unknown fields: " + ", ".join(sorted(unknown)))
    return value


def _string(value, path):
    if type(value) is not str or not value.strip():
        _fail("INVALID_STRING", path, "expected a nonblank string")
    return value


def _identifier(value, path):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail("INVALID_ID", path, "expected a lowercase ASCII identifier without whitespace")
    return value


def _source_uri(value, classification, path):
    """Check a provenance locator's syntax only; never fetch or authenticate it."""
    _string(value, path)
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        _fail("INVALID_SOURCE_URI", path, "source URI cannot contain whitespace or controls")
    allowed = ("http", "https") if classification == "OBSERVED" else ("http", "https", "synthetic")
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        # Reading .port triggers urllib's numeric/range validation.
        _ = parts.port
        if parts.scheme not in allowed or not hostname or parts.username is not None or parts.password is not None:
            raise ValueError("invalid scheme, host or credentials")
        if "%" in hostname:
            raise ValueError("encoded hosts and scoped addresses are not permitted")
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            host = (hostname[:-1] if hostname.endswith(".") else hostname).encode("idna").decode("ascii")
            if not host or len(host) > 253 or any(
                not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in host.split(".")
            ):
                raise ValueError("invalid hostname")
    except (ValueError, UnicodeError):
        _fail("INVALID_SOURCE_URI", path, "expected an allowed URI with a valid hostname and no credentials")
    return value


def _enum(value, choices, path):
    if type(value) is not str or value not in choices:
        _fail("INVALID_ENUM", path, "value is not an allowed enum member")
    return value


def _timestamp(value, path):
    if type(value) is not str or not _TIME.fullmatch(value):
        _fail("INVALID_TIMESTAMP", path, "expected an aware ISO-8601 timestamp with seconds")
    # -00:00 denotes an unknown local offset in RFC3339, not authenticated UTC.
    if value.endswith("-00:00"):
        _fail("INVALID_TIMESTAMP", path, "unknown timezone offsets are forbidden")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        _fail("INVALID_TIMESTAMP", path, "invalid calendar time or timezone offset")


def _hash(value, path):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail("INVALID_HASH", path, "expected lowercase SHA-256 hex")
    return value


def _bound_hash(obj, field, path):
    supplied = _hash(obj[field], f"{path}.{field}")
    actual = canonical_sha256({key: value for key, value in obj.items() if key != field})
    if supplied != actual:
        _fail("HASH_MISMATCH", f"{path}.{field}", "declared hash does not bind this content")
    return actual


def _references(value, known, path, nonempty=False):
    if type(value) is not list or (nonempty and not value):
        _fail("INVALID_REFERENCES", path, "expected an evidence ID array" + (" with entries" if nonempty else ""))
    refs = [_identifier(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if len(set(refs)) != len(refs):
        _fail("DUPLICATE_ID", path, "duplicate evidence reference")
    if not set(refs) <= known:
        _fail("UNKNOWN_REFERENCE", path, "reference is outside this packet")
    return frozenset(refs)


def _packet(raw):
    path = "$.packet"
    _object(raw, ("packet_id", "run_id", "as_of", "created_at", "mode", "data_classification",
                  "evidence", "snapshot_sha256"), path)
    packet_id = _identifier(raw["packet_id"], path + ".packet_id")
    run_id = _identifier(raw["run_id"], path + ".run_id")
    as_of = _timestamp(raw["as_of"], path + ".as_of")
    created = _timestamp(raw["created_at"], path + ".created_at")
    mode = _enum(raw["mode"], ("historical_development", "forward_shadow"), path + ".mode")
    classification = _enum(raw["data_classification"], ("SYNTHETIC", "OBSERVED"), path + ".data_classification")
    if type(raw["evidence"]) is not list or not raw["evidence"]:
        _fail("MISSING_EVIDENCE", path + ".evidence", "packet needs at least one evidence entry")
    evidence, ids = [], set()
    for index, item in enumerate(raw["evidence"]):
        loc = f"{path}.evidence[{index}]"
        _object(item, ("evidence_id", "source_uri", "content", "published_at", "available_at",
                       "captured_at", "content_sha256"), loc)
        eid = _identifier(item["evidence_id"], loc + ".evidence_id")
        if eid in ids:
            _fail("DUPLICATE_ID", loc, "duplicate evidence ID")
        ids.add(eid)
        source = _source_uri(item["source_uri"], classification, loc + ".source_uri")
        content = _string(item["content"], loc + ".content")
        published = _timestamp(item["published_at"], loc + ".published_at")
        available = _timestamp(item["available_at"], loc + ".available_at")
        captured = _timestamp(item["captured_at"], loc + ".captured_at")
        if published > available or available > captured:
            _fail("TIMESTAMP_ORDER", loc, "require published_at <= available_at <= captured_at")
        if published > as_of or available > as_of:
            _fail("FUTURE_EVIDENCE", loc, "publication and availability must not exceed as_of")
        if mode == "forward_shadow" and captured > as_of:
            _fail("FUTURE_CAPTURE", loc + ".captured_at", "forward-shadow capture must not exceed as_of")
        if captured > created:
            _fail("TIMESTAMP_ORDER", path + ".created_at", "packet cannot precede its evidence capture")
        digest = _hash(item["content_sha256"], loc + ".content_sha256")
        if digest != content_sha256(content):
            _fail("HASH_MISMATCH", loc + ".content_sha256", "evidence content changed")
        evidence.append(Evidence(eid, source, content, published, available, captured, digest))
    digest = _bound_hash(raw, "snapshot_sha256", path)
    return EvidencePacket(packet_id, run_id, as_of, created, mode, classification, tuple(evidence), digest)


def _context(raw, packet, path, earliest):
    if _identifier(raw["run_id"], path + ".run_id") != packet.run_id:
        _fail("RUN_MISMATCH", path + ".run_id", "object belongs to another run")
    if _hash(raw["packet_sha256"], path + ".packet_sha256") != packet.snapshot_sha256:
        _fail("PACKET_MISMATCH", path + ".packet_sha256", "object binds a different packet")
    if _timestamp(raw["as_of"], path + ".as_of") != packet.as_of:
        _fail("CUTOFF_MISMATCH", path + ".as_of", "object has a different evidence cutoff")
    created = _timestamp(raw["created_at"], path + ".created_at")
    if created < earliest:
        _fail("TIMESTAMP_ORDER", path + ".created_at", "object precedes its required input")
    return created


def _candidate(raw, packet):
    path = "$.candidate"
    _object(raw, ("candidate_id", "run_id", "packet_sha256", "as_of", "created_at", "producer_id",
                  "stance", "thesis", "supporting_evidence_ids", "counter_evidence_ids", "counter_search",
                  "invalidation_condition", "candidate_sha256"), path)
    cid = _identifier(raw["candidate_id"], path + ".candidate_id")
    producer = _identifier(raw["producer_id"], path + ".producer_id")
    created = _context(raw, packet, path, packet.created_at)
    stance = _enum(raw["stance"], ("BULLISH", "BEARISH", "NEUTRAL", "ABSTAIN"), path + ".stance")
    _string(raw["thesis"], path + ".thesis")
    _string(raw["invalidation_condition"], path + ".invalidation_condition")
    known = {item.evidence_id for item in packet.evidence}
    support = _references(raw["supporting_evidence_ids"], known, path + ".supporting_evidence_ids", True)
    counter = _references(raw["counter_evidence_ids"], known, path + ".counter_evidence_ids")
    searched = frozenset()
    search = raw["counter_search"]
    if search is not None:
        loc = path + ".counter_search"
        _object(search, ("scope", "query", "searched_at", "as_of", "searched_evidence_ids", "limitations", "conclusion"), loc)
        _enum(search["scope"], ("PACKET_ONLY",), loc + ".scope")
        _string(search["query"], loc + ".query")
        _string(search["limitations"], loc + ".limitations")
        _enum(search["conclusion"], ("NONE_FOUND_IN_BOUNDED_SCOPE",), loc + ".conclusion")
        if _timestamp(search["as_of"], loc + ".as_of") != packet.as_of:
            _fail("CUTOFF_MISMATCH", loc + ".as_of", "search has a different evidence cutoff")
        searched = _references(search["searched_evidence_ids"], known, loc + ".searched_evidence_ids", True)
        searched_at = _timestamp(search["searched_at"], loc + ".searched_at")
        latest_capture = max(item.captured_at for item in packet.evidence if item.evidence_id in searched)
        if not max(latest_capture, packet.created_at) <= searched_at <= created:
            _fail("TIMESTAMP_ORDER", loc + ".searched_at", "search must follow packet creation and captures, and precede the candidate")
        if counter:
            _fail("CONTRADICTORY_SEARCH", loc, "use explicit counter-evidence OR a bounded negative search, not both")
    if not counter and search is None:
        _fail("MISSING_COUNTEREVIDENCE", path, "require counter-evidence or a documented bounded negative search")
    digest = _bound_hash(raw, "candidate_sha256", path)
    return Candidate(cid, producer, created, stance, support | counter | searched, digest)


def _challenge(raw, packet, candidate):
    path = "$.challenge"
    _object(raw, ("challenge_id", "run_id", "packet_sha256", "candidate_sha256", "as_of", "created_at",
                  "producer_id", "disposition", "reviewed_evidence_ids", "contradictions", "search_summary", "rationale"), path)
    cid = _identifier(raw["challenge_id"], path + ".challenge_id")
    producer = _identifier(raw["producer_id"], path + ".producer_id")
    if producer == candidate.producer_id:
        _fail("SELF_REVIEW", path + ".producer_id", "candidate and challenge require distinct declared producer IDs")
    created = _context(raw, packet, path, candidate.created_at)
    if _hash(raw["candidate_sha256"], path + ".candidate_sha256") != candidate.candidate_sha256:
        _fail("CANDIDATE_MISMATCH", path + ".candidate_sha256", "challenge binds a different candidate")
    disposition = _enum(raw["disposition"], ("NO_MATERIAL_CONTRADICTION_FOUND", "MATERIAL_CONTRADICTIONS", "ABSTAIN"), path + ".disposition")
    _string(raw["rationale"], path + ".rationale")
    known = {item.evidence_id for item in packet.evidence}
    reviewed = _references(raw["reviewed_evidence_ids"], known, path + ".reviewed_evidence_ids", True)
    if reviewed != known:
        _fail("INCOMPLETE_REVIEW", path + ".reviewed_evidence_ids", "review must cover every evidence entry in the packet")
    summary = raw["search_summary"]
    _object(summary, ("scope", "limitations"), path + ".search_summary")
    _enum(summary["scope"], ("PACKET_ONLY",), path + ".search_summary.scope")
    _string(summary["limitations"], path + ".search_summary.limitations")
    contradictions = raw["contradictions"]
    if type(contradictions) is not list:
        _fail("INVALID_TYPE", path + ".contradictions", "expected an array")
    for index, item in enumerate(contradictions):
        loc = f"{path}.contradictions[{index}]"
        _object(item, ("description", "evidence_ids"), loc)
        _string(item["description"], loc + ".description")
        _references(item["evidence_ids"], reviewed, loc + ".evidence_ids", True)
    if bool(contradictions) != (disposition == "MATERIAL_CONTRADICTIONS"):
        _fail("CONTRADICTORY_DISPOSITION", path, "material-contradiction disposition must agree with a nonempty contradiction list")
    return Challenge(cid, producer, created, disposition, len(contradictions), canonical_sha256(raw))


def _report(status, **fields):
    return dict(schema_version=1, report_type="RESEARCH_EVIDENCE_BOUNDARY", status=status,
                research_stance="ABSTAIN", execution_authorized=False, profit_evidence=False,
                clean_holdout=False, truth_verified=False, provenance_authenticated=False,
                independent_authorship_verified=False, statistical_independence_verified=False,
                acceptance_scope="STRUCTURE_DECLARED_PIT_REFERENCE_AND_HASH_CONSISTENCY_ONLY",
                **fields)


def invalid_report(error):
    return _report("INVALID", errors=[dict(code=error.code, path=error.path, detail=error.detail)])


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def evaluate(document: Any) -> dict:
    """Validate explicit immutable snapshots and return a deterministic safe report.

    Input dictionaries are read, never mutated. Parsed domain objects are frozen;
    nested evidence is a tuple of frozen values. No persistent memory, model,
    external source lookup, signal, simulation, portfolio or execution call exists.
    """
    try:
        _json_value(document)
        _object(document, ("schema_version", "packet", "candidate", "challenge"), "$")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            _fail("INVALID_VERSION", "$.schema_version", "expected integer version 1")
        packet = _packet(document["packet"])
        candidate = _candidate(document["candidate"], packet)
        challenge = _challenge(document["challenge"], packet, candidate)
        ids = [packet.packet_id, candidate.candidate_id, challenge.challenge_id]
        ids.extend(item.evidence_id for item in packet.evidence)
        if len(ids) != len(set(ids)):
            _fail("DUPLICATE_ID", "$", "packet, candidate, challenge and evidence IDs must be distinct")
    except BoundaryError as exc:
        return invalid_report(exc)
    except RecursionError:
        return invalid_report(BoundaryError("INVALID_JSON", "$", "input nesting is too deep"))
    if challenge.disposition == "MATERIAL_CONTRADICTIONS":
        status, reasons = "REVIEW_REQUIRED", ["UNRESOLVED_MATERIAL_CONTRADICTIONS"]
    elif candidate.stance == "ABSTAIN" or challenge.disposition == "ABSTAIN":
        status, reasons = "ABSTAIN", ["EXPLICIT_ABSTENTION"]
    else:
        status, reasons = "RESEARCH_PACKET_ACCEPTED", ["STRUCTURAL_CHECKS_PASSED"]
    report = _report(status, run_id=packet.run_id, packet_sha256=packet.snapshot_sha256,
                     candidate_sha256=candidate.candidate_sha256, challenge_sha256=challenge.challenge_sha256,
                     evidence_cutoff=_iso(packet.as_of), packet_created_at=_iso(packet.created_at),
                     candidate_created_at=_iso(candidate.created_at), challenge_created_at=_iso(challenge.created_at),
                     decision_available_at=_iso(challenge.created_at),
                     mode=packet.mode, data_classification=packet.data_classification,
                     data_label=("ALL_SEEN_OR_RECONSTRUCTED" if packet.mode == "historical_development"
                                 else "FORWARD_SHADOW_UNVERIFIED"),
                     material_contradiction_count=challenge.contradiction_count, reason_codes=reasons,
                     limitations=["Declared timestamps and hashes are not source or time authentication.",
                                  "Distinct producer IDs do not establish independent authorship or statistical independence.",
                                  "Text truth, relevance, search completeness and semantic contradiction resolution are not validated.",
                                  "No model, trading signal, backtest, profitability assessment or order was run."], errors=[])
    if status == "RESEARCH_PACKET_ACCEPTED":
        report["research_stance"] = candidate.stance
    return report


def evaluate_json(text: str) -> dict:
    try:
        return evaluate(load_document(text))
    except BoundaryError as exc:
        return invalid_report(exc)
    except RecursionError:
        return invalid_report(BoundaryError("INVALID_JSON", "$", "input nesting is too deep"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="explicit research JSON file, or - for stdin")
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        report = evaluate_json(text)
    except (OSError, UnicodeError):
        report = invalid_report(BoundaryError("INPUT_READ_ERROR", "$", "could not read UTF-8 input"))
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if report["status"] == "RESEARCH_PACKET_ACCEPTED" else (1 if report["status"] == "INVALID" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
