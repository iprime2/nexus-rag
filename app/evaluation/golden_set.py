"""Golden-set format and checker (eval/golden_set.jsonl).

One JSON object per line. The checker reports *every* problem with its line number instead of
stopping at the first, so a whole file can be fixed in one pass. Rules that span fields
(e.g. "unanswerable questions have no evidence") live in the model; rules that need the
whole file or the dataset manifest (duplicate ids, unknown documents) live in
``validate_golden_set``.
"""

import json
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

QuestionType = Literal["factual", "superseded", "unanswerable", "exact_term"]


class Evidence(BaseModel):
    """Where the expected answer is written: the owner checks it against this exact page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str = Field(min_length=1)  # as in datasets/faa/manifest.csv
    page: int = Field(ge=1)  # 1-based, like the page numbers our extractor stores
    quote: str = Field(min_length=1)  # the supporting sentence, copied from the page


class GoldenQuestion(BaseModel):
    # extra="forbid": a typo such as "questoin" is an error, not a silently ignored field.
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^q\d{3}$")
    type: QuestionType
    question: str = Field(min_length=1)
    answerable: bool
    expected_answer: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    written_by: Literal["owner", "claude"]  # honest attribution; see docs/evaluation-plan.md
    verified_on: date | None = None  # None = draft: not yet checked against the source page
    notes: str = ""

    @property
    def is_verified(self) -> bool:
        return self.verified_on is not None

    @model_validator(mode="after")
    def _fields_agree(self) -> Self:
        if (self.type == "unanswerable") == self.answerable:
            raise ValueError("type 'unanswerable' and answerable=false must go together")
        if self.answerable and (not self.evidence or not self.expected_answer):
            raise ValueError("an answerable question needs evidence and an expected_answer")
        if not self.answerable and self.evidence:
            raise ValueError("an unanswerable question must not have evidence")
        return self


def validate_golden_set(
    lines: Iterable[str], doc_status: Mapping[str, str]
) -> tuple[list[GoldenQuestion], list[str]]:
    """Parse golden-set lines. ``doc_status`` maps manifest doc_id -> "active" | "cancelled".

    Returns the valid questions and a list of "line N: ..." errors (empty when the file is valid).
    """
    questions: list[GoldenQuestion] = []
    errors: list[str] = []
    first_line_of: dict[str, int] = {}

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            q = GoldenQuestion.model_validate(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: invalid JSON: {exc.msg}")
            continue
        except ValidationError as exc:
            for err in exc.errors():
                where = ".".join(str(part) for part in err["loc"])
                errors.append(f"line {number}: {where or 'question'}: {err['msg']}")
            continue

        line_errors = []
        if q.id in first_line_of:
            line_errors.append(f"duplicate id '{q.id}' (first used on line {first_line_of[q.id]})")
        for ev in q.evidence:
            status = doc_status.get(ev.doc_id)
            if status is None:
                line_errors.append(f"unknown doc_id '{ev.doc_id}' (not in the dataset manifest)")
            elif q.type == "superseded" and status != "active":
                # The trap's expected answer must come from the current revision.
                line_errors.append(f"superseded question cites cancelled document '{ev.doc_id}'")

        first_line_of.setdefault(q.id, number)
        if line_errors:
            errors.extend(f"line {number}: {e}" for e in line_errors)
        else:
            questions.append(q)

    return questions, errors
