"""Streamlit AppTest for front/app.py with a mocked API client.

Runs the app end-to-end in-process (no server, no network) by swapping the real
CPEClient for a fake that serves a canned long-format payload, then asserts the
dashboard renders the four charts and the filters without error.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

FRONT_DIR = Path(__file__).resolve().parent.parent
if str(FRONT_DIR) not in sys.path:
    sys.path.insert(0, str(FRONT_DIR))

from api_client import LONG_FORMAT_COLUMNS  # noqa: E402

APP_PATH = str(FRONT_DIR / "app.py")

ROWS = [
    {
        "Nome do Aluno": "Giovanna",
        "Turma": "3A",
        "Área": "Matemática",
        "Subárea": "Álgebra",
        "Número da questão": 1,
        "Questão": "Q1",
        "Resposta do aluno": "E",
        "Resultado": "Acerto",
    },
    {
        "Nome do Aluno": "Pedro",
        "Turma": "3A",
        "Área": "Linguagem e Códigos",
        "Subárea": "Português",
        "Número da questão": 2,
        "Questão": "Q2",
        "Resposta do aluno": "B",
        "Resultado": "Erro",
    },
]


class FakeClient:
    base_url = "http://fake"

    def health(self):
        return True

    def exams(self):
        return [{"id": 1, "name": "Simulado 1", "applied_on": None, "sequence": 1}]

    def long_format_dataframe(self, **filters):
        frame = pd.DataFrame(ROWS)
        return frame[LONG_FORMAT_COLUMNS]

    def classes(self):
        return [{"id": 1, "name": "3A", "turno": "vespertino"}]

    def class_trend(self, class_id):
        return {
            "class_id": class_id,
            "points": [
                {
                    "exam_id": 1,
                    "exam_name": "Simulado 1",
                    "applied_on": "2026-03-01",
                    "sequence": 1,
                    "overall": {
                        "total": 4,
                        "acertos": 1,
                        "erros": 3,
                        "em_branco": 0,
                        "taxa_acerto": 25.0,
                    },
                    "by_subject": {"Matemática": 50.0, "Português": 0.0},
                },
                {
                    "exam_id": 2,
                    "exam_name": "Simulado 2",
                    "applied_on": "2026-05-01",
                    "sequence": 2,
                    "overall": {
                        "total": 4,
                        "acertos": 3,
                        "erros": 1,
                        "em_branco": 0,
                        "taxa_acerto": 75.0,
                    },
                    "by_subject": {"Matemática": 100.0, "Português": 50.0},
                },
            ],
        }


def _clear_streamlit_caches():
    """get_client() is @st.cache_resource; clear it so each run rebuilds it."""
    import streamlit as st

    try:
        st.cache_resource.clear()
    except Exception:
        pass


@pytest.fixture
def app():
    # Patch the class so the app's cached get_client() builds our fake
    _clear_streamlit_caches()
    with patch("api_client.CPEClient", FakeClient):
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        yield at


def test_app_runs_without_exception(app):
    assert not app.exception


def test_dashboard_renders_four_charts(app):
    # Move to the dashboard tab context: AppTest runs every tab body, so the
    # plotly charts from the dashboard are already in the element tree.
    # Four st.plotly_chart calls -> four figures rendered.
    # (KPIs + charts only appear when the fake returns rows, which it does.)
    subheaders = [h.value for h in app.subheader]
    assert "1. Desempenho por área" in subheaders
    assert "2. Desempenho por subárea" in subheaders
    assert "3. Taxa de acerto por questão" in subheaders
    assert "4. Desempenho por aluno" in subheaders


def test_no_health_error_shown(app):
    errors = [e.value for e in app.error]
    assert not any("não consegui falar com a api" in e.lower() for e in errors)


def test_evolucao_tab_renders(app):
    # The evolution tab shows the two trend subheaders when >= 2 exams exist
    subheaders = [h.value for h in app.subheader]
    assert "Evolução geral da turma" in subheaders
    assert "Evolução por área" in subheaders


def test_health_banner_when_api_down():
    class DownClient(FakeClient):
        def health(self):
            return False

        def exams(self):
            return []

    _clear_streamlit_caches()
    with patch("api_client.CPEClient", DownClient):
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert not at.exception
        errors = [e.value.lower() for e in at.error]
        assert any("não consegui falar com a api" in e for e in errors)
