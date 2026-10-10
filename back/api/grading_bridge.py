"""Bridge between the OMR pipeline and the ingest layer.

Kept in its own module (imported lazily by the /gradings endpoint) so importing
the API never pulls in OpenCV. It runs the same pipeline main.py uses and hands
back the ResultsByQuestion frame the ingest layer consumes.
"""
from __future__ import annotations

import io
from typing import List, Tuple

import pandas as pd

from grading.results import load_results_by_question


def grade_and_frame(
    images: List[Tuple[str, bytes]],
    answer_key: pd.DataFrame,
    question_column: str = None,
    answer_column: str = None,
) -> Tuple[pd.DataFrame, str]:
    """Grade `images` against `answer_key`, returning (results_frame, log).

    Imports grading.pipeline lazily; that module needs the template.json in
    inputs/ and the OpenCV stack. Column detection mirrors the old Streamlit app:
    first column that looks like a question / answer header.
    """
    from grading.pipeline import DEFAULT_MARKING, run_correction

    question_column = question_column or _pick(
        answer_key.columns, ("questão", "questao", "question", "nº", "numero", "número")
    )
    answer_column = answer_column or _pick(
        answer_key.columns,
        ("gabarito", "answer", "resposta", "correta"),
        exclude={question_column},
    )
    if question_column is None or answer_column is None:
        raise ValueError(
            "Não encontrei as colunas de questão e gabarito no arquivo enviado."
        )

    extra_columns = [c for c in answer_key.columns if c != question_column]

    from pathlib import Path

    template_path = Path(__file__).resolve().parent.parent / "inputs" / "template.json"
    if not template_path.exists():
        raise ValueError(
            "template.json não encontrado em inputs/. Coloque a folha de resposta lá."
        )
    config_path = template_path.with_name("config.json")

    correction = run_correction(
        images=images,
        template_bytes=template_path.read_bytes(),
        answer_key=answer_key,
        question_column=question_column,
        answer_column=answer_column,
        extra_columns=extra_columns,
        marking=DEFAULT_MARKING,
        config_bytes=config_path.read_bytes() if config_path.exists() else None,
    )

    # run_correction already parsed the sheet; re-load from its raw csv so the
    # ingest layer sees the exact on-disk ResultsByQuestion shape (score row +
    # meta columns intact).
    results = load_results_by_question(io.StringIO(correction.raw_csv))
    return results, correction.log


def _pick(columns, hints, exclude=()):
    for hint in hints:
        for column in columns:
            if column in exclude:
                continue
            if hint in str(column).strip().lower():
                return column
    return None
