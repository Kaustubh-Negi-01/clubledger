"""Unit tests for the requirements coverage checker (tests.req_coverage).

Harness tests covering:
- Unknown IDs in test markers
- Missing positive or negative passing evidence for implemented IDs
- Skipped/xfail/xpass tests not counting as passing evidence
- Failing tests blocking CI
- Stale / missing results file / commit mismatch
- Unjustified deferrals (missing reason)
- Duplicate requirement rows rejected
- Unknown status keys rejected
- Malformed markers rejected
- Tests for planned IDs executing without blocking progress mode
- Final mode validation
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from tests.req_coverage import check_coverage, parse_requirements, load_req_status


def test_parse_requirements():
    """Verify parsing docs/REQUIREMENTS.md yields the expected unique IDs."""
    ids = parse_requirements(Path("docs/REQUIREMENTS.md"))
    assert len(ids) == 110
    assert len(ids) == len(set(ids))
    assert "AUTH-01" in ids
    assert "E2E-01" in ids
    assert "EVD-01" in ids


def test_duplicate_requirement_rows_rejected(tmp_path: Path):
    """Checker must reject duplicate requirement rows in REQUIREMENTS.md."""
    req_file = tmp_path / "REQUIREMENTS.md"
    req_file.write_text(
        "| ID | Requirement |\n|---|---|\n| AUTH-01 | Test 1 |\n| AUTH-01 | Test 1 duplicate |\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate requirement row"):
        parse_requirements(req_file)


def test_unknown_status_key_rejected(tmp_path: Path):
    """Checker must reject unknown status keys in req_status.json."""
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps({"AUTH-01": "invalid_status"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown status key"):
        load_req_status(status_file)


def test_missing_results_file(tmp_path: Path):
    """Checker must fail if .pytest_results.json is missing."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps({"AUTH-01": "planned"}), encoding="utf-8")
    missing_results = tmp_path / "non_existent.json"

    with pytest.raises(FileNotFoundError, match="Pytest test results file not found"):
        check_coverage(
            mode="progress",
            req_path=req_file,
            status_path=status_file,
            results_path=missing_results,
            check_commit=False,
        )


def test_stale_mismatched_results_rejected(tmp_path: Path):
    """Checker must reject test results from a different git commit."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = tmp_path / "req_status.json"
    status_file.write_text(
        json.dumps({rid: "planned" for rid in parse_requirements(req_file)}),
        encoding="utf-8",
    )

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "old_deadbeef_commit",
                "exitstatus": 0,
                "tests": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Stale test results detected"):
        check_coverage(
            mode="progress",
            req_path=req_file,
            status_path=status_file,
            results_path=results_file,
            check_commit=True,  # compares against current HEAD
        )


def test_nonzero_pytest_exitstatus_rejected(tmp_path: Path):
    """Checker must fail if pytest reported a non-zero exit status (e.g. collection error)."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = Path("tests/req_status.json")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 2,  # e.g. collection error
                "tests": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="non-zero exit status"):
        check_coverage(
            mode="progress",
            req_path=req_file,
            status_path=status_file,
            results_path=results_file,
            check_commit=False,
        )


def test_unknown_id_in_marker(tmp_path: Path):
    """Checker must fail if test markers contain an unknown requirement ID."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = Path("tests/req_status.json")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [
                    {
                        "nodeid": "tests/unit/test_fake.py::test_fake",
                        "outcome": "passed",
                        "markers": [{"id": "UNKNOWN-99", "kind": "pos"}],
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code != 0


def test_malformed_marker_rejected(tmp_path: Path):
    """Checker must fail if a marker is malformed (invalid kind or missing id)."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = Path("tests/req_status.json")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [
                    {
                        "nodeid": "tests/unit/test_fake.py::test_fake",
                        "outcome": "passed",
                        "markers": [{"id": "AUTH-01", "kind": "invalid_kind"}],
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code != 0


def test_failing_test_blocks_ci(tmp_path: Path):
    """Checker must fail if any test in pytest run failed."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = Path("tests/req_status.json")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [
                    {
                        "nodeid": "tests/unit/test_err.py::test_err",
                        "outcome": "failed",
                        "markers": [],
                    }
                ],
                "failures": [
                    {
                        "nodeid": "tests/unit/test_err.py::test_err",
                        "message": "AssertionError",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code != 0


def test_missing_pos_or_neg_evidence_for_implemented(tmp_path: Path):
    """Marking an ID implemented without both positive and negative passing tests must fail."""
    req_file = Path("docs/REQUIREMENTS.md")

    base_status = json.loads(Path("tests/req_status.json").read_text(encoding="utf-8"))
    base_status["AUTH-01"] = "implemented"
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    # Provide only 'pos' passing test
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [
                    {
                        "nodeid": "tests/unit/test_auth.py::test_auth_pos",
                        "outcome": "passed",
                        "markers": [{"id": "AUTH-01", "kind": "pos"}],
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code != 0  # Missing neg evidence!


def test_skipped_or_xfail_never_counts_as_passing_evidence(tmp_path: Path):
    """Skipped, xfail, or xpass tests must never count as passing requirement evidence."""
    req_file = Path("docs/REQUIREMENTS.md")

    base_status = json.loads(Path("tests/req_status.json").read_text(encoding="utf-8"))
    base_status["AUTH-01"] = "implemented"
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    # 'pos' passed, but 'neg' was xfail
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [
                    {
                        "nodeid": "tests/unit/test_auth.py::test_auth_pos",
                        "outcome": "passed",
                        "markers": [{"id": "AUTH-01", "kind": "pos"}],
                    },
                    {
                        "nodeid": "tests/unit/test_auth.py::test_auth_neg",
                        "outcome": "xfail",
                        "markers": [{"id": "AUTH-01", "kind": "neg"}],
                    },
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code != 0


def test_planned_id_tests_may_execute_in_progress_mode(tmp_path: Path):
    """Under lead workflow correction, tests for planned IDs may execute without failing progress mode."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = tmp_path / "req_status.json"
    status_file.write_text(
        json.dumps({rid: "planned" for rid in parse_requirements(req_file)}),
        encoding="utf-8",
    )

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [
                    {
                        "nodeid": "tests/unit/test_auth.py::test_partial_plan",
                        "outcome": "passed",
                        "markers": [{"id": "AUTH-01", "kind": "pos"}],
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code == 0


def test_unjustified_deferral_fails(tmp_path: Path):
    """A deferred status without a reason must fail."""
    req_file = Path("docs/REQUIREMENTS.md")

    base_status = {rid: "planned" for rid in parse_requirements(req_file)}
    base_status["AUTH-01"] = "deferred"  # No reason string
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code != 0


def test_justified_deferral_succeeds(tmp_path: Path):
    """A deferred status with a valid reason succeeds in progress mode."""
    req_file = Path("docs/REQUIREMENTS.md")

    base_status = {rid: "planned" for rid in parse_requirements(req_file)}
    base_status["AUTH-01"] = {
        "status": "deferred",
        "reason": "Cut line per BUILD_ORDER.md §5",
    }
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="progress",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code == 0


def test_final_mode_fails_on_unimplemented(tmp_path: Path):
    """Final release gate mode must fail if planned IDs remain unimplemented."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = tmp_path / "req_status.json"
    status_file.write_text(
        json.dumps({rid: "planned" for rid in parse_requirements(req_file)}),
        encoding="utf-8",
    )

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T12:00:00Z",
                "commit": "unknown",
                "exitstatus": 0,
                "tests": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    code = check_coverage(
        mode="final",
        req_path=req_file,
        status_path=status_file,
        results_path=results_file,
        check_commit=False,
    )
    assert code != 0
