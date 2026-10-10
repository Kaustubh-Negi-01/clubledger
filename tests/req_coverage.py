"""Requirement status and test coverage tracker.

Validates requirement coverage against docs/REQUIREMENTS.md and tests/req_status.json.
Modes:
  --mode progress: used by early CI on every PR.
  --mode final: release gate before final evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Set, Tuple

DEFAULT_REQ_PATH = Path("docs/REQUIREMENTS.md")
DEFAULT_STATUS_PATH = Path("tests/req_status.json")
DEFAULT_RESULTS_PATH = Path(".pytest_results.json")
VALID_STATUSES = {"planned", "implemented", "deferred"}


def get_current_git_commit() -> str:
    """Get current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return res.stdout.strip()
    except Exception:
        return ""


def parse_requirements(md_path: Path = DEFAULT_REQ_PATH) -> List[str]:
    """Parse requirement IDs from docs/REQUIREMENTS.md table rows.

    Rejects duplicate requirement rows.
    """
    if not md_path.exists():
        raise FileNotFoundError(f"Requirements file not found: {md_path}")

    text = md_path.read_text(encoding="utf-8")
    table_rows = re.findall(r"^\|\s*([A-Za-z0-9_-]+)\s*\|", text, re.MULTILINE)
    raw_ids = [
        m for m in table_rows if m not in ("ID", "#") and not m.startswith("---")
    ]

    seen: Set[str] = set()
    duplicates: List[str] = []
    unique_ids: List[str] = []
    for rid in raw_ids:
        if rid in seen:
            duplicates.append(rid)
        else:
            seen.add(rid)
            unique_ids.append(rid)

    if duplicates:
        raise ValueError(
            f"Duplicate requirement row(s) found in {md_path}: {sorted(set(duplicates))}"
        )

    return unique_ids


def load_req_status(status_path: Path = DEFAULT_STATUS_PATH) -> Dict[str, Any]:
    """Load tests/req_status.json mapping IDs to status.

    Rejects unknown status keys.
    """
    if not status_path.exists():
        raise FileNotFoundError(f"Status file not found: {status_path}")
    with open(status_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate status values
    for rid, val in data.items():
        if isinstance(val, dict):
            status = val.get("status")
        elif isinstance(val, str):
            status = val
        else:
            raise ValueError(f"Invalid status specification for {rid}: {val}")

        if status not in VALID_STATUSES:
            raise ValueError(
                f"Unknown status key '{status}' for {rid}. Must be one of {sorted(VALID_STATUSES)}."
            )

    return data


def load_test_results(
    results_path: Path = DEFAULT_RESULTS_PATH,
    expected_commit: str | None = None,
) -> Dict[str, Any]:
    """Load recorded test run outcomes produced by pytest plugin in tests/conftest.py.

    Validates presence, exit status, and tested git revision matching.
    """
    if not results_path.exists():
        raise FileNotFoundError(
            f"Pytest test results file not found: {results_path}. "
            "Please run pytest before running tests.req_coverage."
        )

    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    exitstatus = data.get("exitstatus")
    if exitstatus is None:
        raise ValueError(f"Malformed results file {results_path}: missing exitstatus.")

    if exitstatus != 0:
        raise RuntimeError(
            f"Pytest run finished with non-zero exit status ({exitstatus})."
        )

    if expected_commit:
        recorded_commit = data.get("commit", "")
        if (
            recorded_commit
            and recorded_commit != "unknown"
            and recorded_commit != expected_commit
        ):
            raise ValueError(
                f"Stale test results detected! Results file tested commit '{recorded_commit}', "
                f"but current HEAD is '{expected_commit}'."
            )

    return data


def check_coverage(
    mode: str,
    req_path: Path = DEFAULT_REQ_PATH,
    status_path: Path = DEFAULT_STATUS_PATH,
    results_path: Path = DEFAULT_RESULTS_PATH,
    check_commit: bool = True,
) -> int:
    """Run coverage check according to accepted contract rules.

    Returns exit code (0 on success, non-zero on failure).
    """
    valid_ids = parse_requirements(req_path)
    total_scope = len(valid_ids)
    valid_id_set = set(valid_ids)

    status_data = load_req_status(status_path)

    current_commit = get_current_git_commit() if check_commit else None
    test_results = load_test_results(results_path, expected_commit=current_commit)

    # Check for test failures in pytest run
    failing_tests = test_results.get("failures", [])
    if failing_tests:
        print(f"FAILED: Pytest reported {len(failing_tests)} test failure(s):")
        for fail in failing_tests:
            print(f"  - {fail.get('nodeid')}: {fail.get('message', 'Failed')}")
        return 1

    recorded_tests = test_results.get("tests", [])

    # Check for unknown requirement IDs and malformed markers
    unknown_ids_found: Set[str] = set()
    malformed_markers: List[str] = []
    test_evidence: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        rid: {"pos": [], "neg": []} for rid in valid_ids
    }

    for test in recorded_tests:
        nodeid = test.get("nodeid", "")
        outcome = test.get("outcome", "")
        markers = test.get("markers", [])

        for marker in markers:
            if marker.get("malformed") or not marker.get("id"):
                malformed_markers.append(nodeid)
                continue

            m_id = marker.get("id")
            m_kind = marker.get("kind")

            if m_id not in valid_id_set:
                unknown_ids_found.add(f"{m_id} (in {nodeid})")
                continue

            if m_kind not in ("pos", "neg"):
                malformed_markers.append(
                    f"{nodeid} (invalid kind '{m_kind}' for {m_id})"
                )
                continue

            # Genuine positive/negative passing evidence:
            # outcome == 'passed' ONLY. (xfail, xpass, skipped never count)
            if outcome == "passed":
                test_evidence[m_id][m_kind].append(test)

    if malformed_markers:
        print("FAILED: Found malformed requirement marker(s):")
        for m in malformed_markers:
            print(f"  - {m}")
        return 1

    if unknown_ids_found:
        print("FAILED: Found markers naming unknown requirement ID(s):")
        for u in sorted(unknown_ids_found):
            print(f"  - {u}")
        return 1

    implemented_count = 0
    deferred_count = 0
    planned_count = 0
    errors: List[str] = []

    for rid in valid_ids:
        raw_val = status_data.get(rid)
        if raw_val is None:
            errors.append(f"Requirement {rid} is missing from {status_path}")
            continue

        if isinstance(raw_val, dict):
            status = raw_val.get("status", "")
            reason = raw_val.get("reason", "")
        elif isinstance(raw_val, str):
            status = raw_val
            reason = ""
        else:
            errors.append(
                f"Invalid status format for {rid} in {status_path}: {raw_val}"
            )
            continue

        if status == "implemented":
            implemented_count += 1
            pos_passes = len(test_evidence[rid]["pos"])
            neg_passes = len(test_evidence[rid]["neg"])
            if pos_passes == 0 or neg_passes == 0:
                errors.append(
                    f"Requirement {rid} is marked 'implemented' but lacks passing evidence: "
                    f"pos={pos_passes}, neg={neg_passes}."
                )

        elif status == "deferred":
            deferred_count += 1
            if not reason:
                errors.append(
                    f"Requirement {rid} is marked 'deferred' but lacks a recorded reason."
                )

        elif status == "planned":
            planned_count += 1
            # Note: Planned ID tests may execute during progress mode.
            # Passing partial tests do not force requirement to implemented or block progress mode.

        else:
            errors.append(
                f"Unknown status '{status}' for requirement {rid} in {status_path}"
            )

    # Mode-specific evaluations
    if mode == "progress":
        print(
            f"Requirements coverage: implemented {implemented_count} / {total_scope} (deferred: {deferred_count}, planned: {planned_count})"
        )
        if errors:
            print(f"FAILED (mode=progress) with {len(errors)} error(s):")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(
            "OK: Progress check passed. Unimplemented requirements do not block early CI."
        )
        return 0

    elif mode == "final":
        print(
            f"Final requirement coverage check: implemented {implemented_count} / {total_scope} (deferred: {deferred_count})"
        )
        for rid in valid_ids:
            raw_val = status_data.get(rid, "")
            st = raw_val.get("status") if isinstance(raw_val, dict) else raw_val
            if st not in ("implemented", "deferred"):
                errors.append(
                    f"Requirement {rid} is '{st}'; must be 'implemented' or 'deferred' for release gate."
                )

        if errors:
            print(f"FAILED (mode=final) with {len(errors)} error(s):")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(
            "OK: Final check passed. All accepted requirements are implemented or justified deferred."
        )
        return 0

    else:
        print(f"Invalid mode: {mode}. Must be 'progress' or 'final'.")
        return 2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ClubLedger requirements coverage checker."
    )
    parser.add_argument(
        "--mode",
        choices=["progress", "final"],
        required=True,
        help="Coverage mode: 'progress' (early CI) or 'final' (release gate).",
    )
    parser.add_argument(
        "--req-file",
        type=Path,
        default=DEFAULT_REQ_PATH,
        help="Path to REQUIREMENTS.md",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_PATH,
        help="Path to req_status.json",
    )
    parser.add_argument(
        "--results-file",
        type=Path,
        default=DEFAULT_RESULTS_PATH,
        help="Path to pytest results json file",
    )
    parser.add_argument(
        "--no-check-commit",
        action="store_true",
        help="Skip checking git commit matching (e.g. in test harness).",
    )

    args = parser.parse_args()
    try:
        code = check_coverage(
            mode=args.mode,
            req_path=args.req_file,
            status_path=args.status_file,
            results_path=args.results_file,
            check_commit=not args.no_check_commit,
        )
        sys.exit(code)
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
