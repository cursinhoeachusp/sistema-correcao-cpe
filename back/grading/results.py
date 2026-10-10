"""Parsing of the ResultsByQuestion.csv the OMR pipeline produces.

This is the logic previously embedded in webapp/pipeline.py, lifted out so it can
be reused without importing any Streamlit or web concern. The pipeline writes a
transposed sheet: a `question` column, an optional leading `score` row, some
answer-key meta columns carried over (Área, Subárea, Gabarito, ...), then one
column per graded sheet holding a verdict like 'correct-E' / 'incorrect-B' /
'unmarked'.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

QUESTION_COLUMN = "question"
SCORE_ROW = "score"

# Dashboard-facing Resultado labels, kept identical to data.repositories
ACERTO, ERRO, NAO_RESPONDEU = "Acerto", "Erro", "Não Respondeu"
RESULT_ORDER = [ACERTO, ERRO, NAO_RESPONDEU]


def load_results_by_question(path_or_buffer):
    """Read a ResultsByQuestion csv into a DataFrame of strings."""
    results = pd.read_csv(path_or_buffer, dtype=str, keep_default_na=False)
    results.columns = [str(column).strip() for column in results.columns]
    if QUESTION_COLUMN not in results.columns:
        # Written with the question labels as the first (index) column
        results = results.rename(columns={results.columns[0]: QUESTION_COLUMN})
    return results


def split_scores(results_by_question):
    """Pull the leading 'score' row out into a {column: score} mapping."""
    is_score_row = results_by_question[QUESTION_COLUMN].str.strip() == SCORE_ROW
    scores = {}
    if is_score_row.any():
        score_row = results_by_question[is_score_row].iloc[0]
        for column, value in score_row.items():
            if column == QUESTION_COLUMN:
                continue
            try:
                scores[column] = float(value)
            except (TypeError, ValueError):
                continue
    return scores, results_by_question[~is_score_row].reset_index(drop=True)


def student_columns(results_by_question, meta_columns):
    """Columns that hold a student's verdicts (everything but question + meta)."""
    known = {QUESTION_COLUMN, *meta_columns}
    return [column for column in results_by_question.columns if column not in known]


def guess_meta_columns(results_by_question, scores):
    """Answer-key columns carried over sit between 'question' and the sheets.

    They are the only non-question columns without a numeric score, since the
    score row is blank for them.
    """
    return [
        column
        for column in results_by_question.columns
        if column != QUESTION_COLUMN and column not in scores
    ]


def student_name_from_file(file_name):
    """Turn a sheet file name into a readable student name."""
    stem = Path(str(file_name)).stem
    return re.sub(r"[_\-]+", " ", stem).strip().title()


def parse_verdict(verdict):
    """Turn 'correct-E' / 'incorrect-B' / 'unmarked' into (resultado, resposta)."""
    value = str(verdict).strip()
    if value in ("", "nan"):
        return NAO_RESPONDEU, "-"
    head, _, marked = value.partition("-")
    head = head.lower()
    if head == "correct":
        return ACERTO, marked or "-"
    if head == "incorrect":
        return ERRO, marked or "-"
    if head == "unmarked":
        return NAO_RESPONDEU, "-"
    # No evaluation config was used - the cell holds the raw marked answer
    return NAO_RESPONDEU if value == "-" else ERRO, value


def question_number(question_label):
    """Extract the trailing integer from a question label like 'q12' -> 12."""
    digits = re.findall(r"\d+", str(question_label))
    return int(digits[-1]) if digits else None
