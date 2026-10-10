"""Repository tests: persist graded sheets and read them back as long format.

The long-format shape asserted here is the contract the dashboard charts consume
(Nome do Aluno, Turma, Área, Subárea, Número da questão, Questão, Resposta do
aluno, Resultado with Acerto/Erro/Não Respondeu), so these tests pin the shape
that Task 5's charts depend on.
"""
from datetime import date

import pandas as pd

from data.models import VERDICT_CORRECT, VERDICT_INCORRECT, VERDICT_UNMARKED, Answer
from data.repositories import (
    ACERTO,
    ERRO,
    LONG_FORMAT_COLUMNS,
    NAO_RESPONDEU,
    AnswerInput,
    SheetInput,
    long_format_dataframe,
    long_format_rows,
    persist_graded_sheet,
)


def _sheet_input(student_name, marked_first, verdict_first):
    """One two-question sheet for a Matemática/Português simulado."""
    return SheetInput(
        student_name=student_name,
        exam_name="Simulado 1",
        class_name="3º Ano A",
        turno="vespertino",
        score=1.0,
        source_image=f"{student_name}.png",
        exam_applied_on=date(2026, 3, 1),
        exam_sequence=1,
        answers=[
            AnswerInput(
                number=1,
                marked_answer=marked_first,
                verdict=verdict_first,
                correct_answer="E",
                subject="Matemática",
                subtopic="Álgebra",
            ),
            AnswerInput(
                number=2,
                marked_answer="-",
                verdict=VERDICT_UNMARKED,
                correct_answer="B",
                subject="Linguagem e Códigos",
                subtopic="Português",
            ),
        ],
    )


def test_persist_creates_full_graph(session):
    persist_graded_sheet(session, _sheet_input("Aluno A", "E", VERDICT_CORRECT))
    session.commit()

    assert session.query(Answer).count() == 2
    rows = long_format_rows(session)
    assert len(rows) == 2


def test_long_format_matches_chart_contract(session):
    persist_graded_sheet(session, _sheet_input("Aluno A", "E", VERDICT_CORRECT))
    persist_graded_sheet(session, _sheet_input("Aluno B", "C", VERDICT_INCORRECT))
    session.commit()

    frame = long_format_dataframe(session)

    # Every canonical column is present and leads
    assert list(frame.columns)[: len(LONG_FORMAT_COLUMNS)] == LONG_FORMAT_COLUMNS

    # Two students x two questions
    assert len(frame) == 4

    aluno_a = frame[frame["Nome do Aluno"] == "Aluno A"].sort_values(
        "Número da questão"
    )
    # Q1 correct -> Acerto, Q2 unmarked -> Não Respondeu
    assert list(aluno_a["Resultado"]) == [ACERTO, NAO_RESPONDEU]
    assert list(aluno_a["Área"]) == ["Matemática", "Linguagem e Códigos"]
    assert list(aluno_a["Subárea"]) == ["Álgebra", "Português"]
    assert list(aluno_a["Turma"]) == ["3º Ano A", "3º Ano A"]
    assert list(aluno_a["Resposta do aluno"]) == ["E", "-"]

    aluno_b = frame[frame["Nome do Aluno"] == "Aluno B"].sort_values(
        "Número da questão"
    )
    # Q1 incorrect -> Erro
    assert aluno_b.iloc[0]["Resultado"] == ERRO


def test_regrade_is_idempotent(session):
    # Grade once, then re-grade the same student/exam with a different verdict
    persist_graded_sheet(session, _sheet_input("Aluno A", "E", VERDICT_CORRECT))
    session.commit()
    persist_graded_sheet(session, _sheet_input("Aluno A", "C", VERDICT_INCORRECT))
    session.commit()

    # Still one sheet, two answers - not duplicated
    assert session.query(Answer).count() == 2
    frame = long_format_dataframe(session)
    q1 = frame[
        (frame["Nome do Aluno"] == "Aluno A") & (frame["Número da questão"] == 1)
    ].iloc[0]
    assert q1["Resultado"] == ERRO
    assert q1["Resposta do aluno"] == "C"


def test_filters_narrow_results(session):
    persist_graded_sheet(session, _sheet_input("Aluno A", "E", VERDICT_CORRECT))
    session.commit()

    # Subject filter keeps only Matemática answers
    from data.models import Subject

    matematica = session.query(Subject).filter_by(name="Matemática").one()
    rows = long_format_rows(session, subject_id=matematica.id)
    assert len(rows) == 1
    assert rows[0]["Área"] == "Matemática"


def test_empty_dataframe_has_canonical_columns(session):
    frame = long_format_dataframe(session)
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == LONG_FORMAT_COLUMNS
    assert frame.empty
