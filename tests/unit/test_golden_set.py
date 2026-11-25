"""Tests for the golden-set format checker (app/evaluation/golden_set.py)."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.cli import main as cli_main
from app.evaluation.golden_set import validate_golden_set

DOCS = {"AC 43-9D": "active", "AC 43-9C": "cancelled"}


def question(**overrides: Any) -> dict[str, Any]:
    q: dict[str, Any] = {
        "id": "q001",
        "type": "factual",
        "question": "What must a maintenance record entry contain?",
        "answerable": True,
        "expected_answer": "A description of the work, the date, and the signature.",
        "evidence": [{"doc_id": "AC 43-9D", "page": 5, "quote": "exact sentence"}],
        "written_by": "owner",
        "verified_on": "2026-12-15",
    }
    q.update(overrides)
    return q


def check(*rows: dict[str, Any] | str) -> tuple[int, list[str]]:
    lines = [r if isinstance(r, str) else json.dumps(r) for r in rows]
    questions, errors = validate_golden_set(lines, DOCS)
    return len(questions), errors


def test_a_valid_verified_question_passes() -> None:
    questions, errors = validate_golden_set([json.dumps(question())], DOCS)

    assert errors == []
    assert questions[0].is_verified


def test_a_question_without_verified_on_is_a_draft() -> None:
    questions, errors = validate_golden_set([json.dumps(question(verified_on=None))], DOCS)

    assert errors == []
    assert not questions[0].is_verified  # eval runs will skip drafts


def test_blank_lines_are_ignored() -> None:
    assert check("", question(), "   ") == (1, [])


def test_an_answerable_question_needs_evidence_and_an_expected_answer() -> None:
    _, errors = check(question(evidence=[], expected_answer=None))

    assert len(errors) == 1
    assert "line 1" in errors[0]
    assert "evidence" in errors[0]


@pytest.mark.parametrize(
    "overrides",
    [
        # unanswerable, but evidence given
        {"type": "unanswerable", "answerable": False, "expected_answer": None},
        # type says unanswerable, flag says answerable
        {"type": "unanswerable"},
        # flag says unanswerable, type says factual
        {"answerable": False, "evidence": [], "expected_answer": None},
    ],
)
def test_unanswerable_type_flag_and_evidence_must_agree(overrides: dict[str, Any]) -> None:
    count, errors = check(question(**overrides))

    assert count == 0
    assert len(errors) == 1


def test_a_valid_unanswerable_question_passes() -> None:
    assert check(
        question(type="unanswerable", answerable=False, expected_answer=None, evidence=[])
    ) == (1, [])


def test_a_typo_in_a_field_name_is_an_error() -> None:
    row = question()
    row["questoin"] = row.pop("question")

    _, errors = check(row)

    assert any("questoin" in e for e in errors)


def test_invalid_json_reports_the_line_number() -> None:
    _, errors = check(question(), "{not json")

    assert len(errors) == 1
    assert errors[0].startswith("line 2: invalid JSON")


def test_duplicate_ids_are_reported_with_both_lines() -> None:
    _, errors = check(question(), question())

    assert errors == ["line 2: duplicate id 'q001' (first used on line 1)"]


def test_evidence_must_cite_a_document_in_the_dataset_manifest() -> None:
    bad = question(evidence=[{"doc_id": "AC 99-1", "page": 1, "quote": "x"}])

    _, errors = check(bad)

    assert errors == ["line 1: unknown doc_id 'AC 99-1' (not in the dataset manifest)"]


def test_a_superseded_trap_must_be_answered_from_an_active_document() -> None:
    # The whole point of the trap: the expected answer comes from the current revision.
    bad = question(type="superseded", evidence=[{"doc_id": "AC 43-9C", "page": 3, "quote": "x"}])

    _, errors = check(bad)

    assert errors == ["line 1: superseded question cites cancelled document 'AC 43-9C'"]


def test_the_committed_golden_set_is_valid() -> None:
    assert cli_main(["check-golden-set"]) == 0


def test_cli_prints_a_summary_and_fails_on_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "golden.jsonl"
    path.write_text(
        json.dumps(question())
        + "\n"
        + json.dumps(question(id="q002", written_by="claude", verified_on=None))
        + "\n"
    )

    assert cli_main(["check-golden-set", str(path)]) == 0
    out = capsys.readouterr().out
    assert "2 questions: 1 verified, 1 draft" in out
    assert "written by owner: 1, claude: 1" in out

    path.write_text("{oops\n")
    assert cli_main(["check-golden-set", str(path)]) == 1
