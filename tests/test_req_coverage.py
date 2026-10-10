"""Unit tests for the requirements coverage checker (tests.req_coverage).

Harness tests covering:
- Unknown IDs in test markers
- Missing positive or negative passing evidence for implemented IDs
- Skipped tests not counting as passing evidence
- Failing tests blocking CI
- Stale / missing results file
- Unjustified deferrals (missing reason)
- Final mode validation
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from tests.req_coverage import check_coverage, parse_requirements


def test_parse_requirements():
    """Verify parsing docs/REQUIREMENTS.md yields the expected unique IDs."""
    ids = parse_requirements(Path("docs/REQUIREMENTS.md"))
    assert len(ids) == 110
    assert len(ids) == len(set(ids))
    assert "AUTH-01" in ids
    assert "EVD-01" in ids


def test_missing_results_file(tmp_path: Path):
    """Checker must fail if .pytest_results.json is missing."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps({"AUTH-01": "planned"}), encoding="utf-8")
    missing_results = tmp_path / "non_existent.json"

    with pytest.raises(FileNotFoundError, match="Pytest test results file not found"):
        check_coverage(mode="progress", req_path=req_file, status_path=status_file, results_path=missing_results)


def test_unknown_id_in_marker(tmp_path: Path):
    """Checker must fail if test markers contain an unknown requirement ID."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = Path("tests/req_status.json")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({
            "exitstatus": 0,
            "tests": [
                {
                    "nodeid": "tests/unit/test_fake.py::test_fake",
                    "outcome": "passed",
                    "markers": [{"id": "UNKNOWN-99", "kind": "pos"}],
                }
            ],
            "failures": [],
        }),
        encoding="utf-8",
    )

    code = check_coverage(mode="progress", req_path=req_file, status_path=status_file, results_path=results_file)
    assert code != 0


def test_failing_test_blocks_ci(tmp_path: Path):
    """Checker must fail if any test in pytest run failed."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = Path("tests/req_status.json")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({
            "exitstatus": 1,
            "tests": [
                {
                    "nodeid": "tests/unit/test_err.py::test_err",
                    "outcome": "failed",
                    "markers": [],
                }
            ],
            "failures": [{"nodeid": "tests/unit/test_err.py::test_err", "message": "AssertionError"}],
        }),
        encoding="utf-8",
    )

    code = check_coverage(mode="progress", req_path=req_file, status_path=status_file, results_path=results_file)
    assert code != 0


def test_missing_pos_or_neg_evidence_for_implemented(tmp_path: Path):
    """Marking an ID implemented without both positive and negative passing tests must fail."""
    req_file = Path("docs/REQUIREMENTS.md")

    # Set AUTH-01 as implemented, all others planned
    base_status = json.loads(Path("tests/req_status.json").read_text(encoding="utf-8"))
    base_status["AUTH-01"] = "implemented"
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    # Provide only 'pos' passing test
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({
            "exitstatus": 0,
            "tests": [
                {
                    "nodeid": "tests/unit/test_auth.py::test_auth_pos",
                    "outcome": "passed",
                    "markers": [{"id": "AUTH-01", "kind": "pos"}],
                }
            ],
            "failures": [],
        }),
        encoding="utf-8",
    )

    code = check_coverage(mode="progress", req_path=req_file, status_path=status_file, results_path=results_file)
    assert code != 0  # Missing neg evidence!


def test_skipped_test_never_counts_as_passing_evidence(tmp_path: Path):
    """A skipped test must not count as passing requirement evidence."""
    req_file = Path("docs/REQUIREMENTS.md")

    base_status = json.loads(Path("tests/req_status.json").read_text(encoding="utf-8"))
    base_status["AUTH-01"] = "implemented"
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    # 'pos' passed, but 'neg' was skipped
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({
            "exitstatus": 0,
            "tests": [
                {
                    "nodeid": "tests/unit/test_auth.py::test_auth_pos",
                    "outcome": "passed",
                    "markers": [{"id": "AUTH-01", "kind": "pos"}],
                },
                {
                    "nodeid": "tests/unit/test_auth.py::test_auth_neg",
                    "outcome": "skipped",
                    "markers": [{"id": "AUTH-01", "kind": "neg"}],
                },
            ],
            "failures": [],
        }),
        encoding="utf-8",
    )

    code = check_coverage(mode="progress", req_path=req_file, status_path=status_file, results_path=results_file)
    assert code != 0  # Skipped does not count!


def test_unjustified_deferral_fails(tmp_path: Path):
    """A deferred status without a reason must fail."""
    req_file = Path("docs/REQUIREMENTS.md")

    base_status = json.loads(Path("tests/req_status.json").read_text(encoding="utf-8"))
    base_status["AUTH-01"] = "deferred"  # No reason string
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({"exitstatus": 0, "tests": [], "failures": []}),
        encoding="utf-8",
    )

    code = check_coverage(mode="progress", req_path=req_file, status_path=status_file, results_path=results_file)
    assert code != 0


def test_justified_deferral_succeeds(tmp_path: Path):
    """A deferred status with a valid reason succeeds in progress mode."""
    req_file = Path("docs/REQUIREMENTS.md")

    base_status = json.loads(Path("tests/req_status.json").read_text(encoding="utf-8"))
    base_status["AUTH-01"] = {"status": "deferred", "reason": "Cut line per BUILD_ORDER.md §5"}
    status_file = tmp_path / "req_status.json"
    status_file.write_text(json.dumps(base_status), encoding="utf-8")

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({"exitstatus": 0, "tests": [], "failures": []}),
        encoding="utf-8",
    )

    code = check_coverage(mode="progress", req_path=req_file, status_path=status_file, results_path=results_file)
    assert code == 0


def test_final_mode_fails_on_unimplemented(tmp_path: Path):
    """Final release gate mode must fail if planned IDs remain unimplemented."""
    req_file = Path("docs/REQUIREMENTS.md")
    status_file = Path("tests/req_status.json")  # All planned

    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({"exitstatus": 0, "tests": [], "failures": []}),
        encoding="utf-8",
    )

    code = check_coverage(mode="final", req_path=req_file, status_path=status_file, results_path=results_file)
    assert code != 0
