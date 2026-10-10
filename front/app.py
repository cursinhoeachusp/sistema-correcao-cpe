"""Corretor de Provas OMR - interface web (Streamlit).

Frontend fino: toda a correção e persistência acontecem no backend (FastAPI +
banco). Este app apenas envia provas para correção, lê os resultados em formato
longo pela API e desenha os gráficos - os mesmos quatro de sempre (desempenho por
área, por subárea, taxa de acerto por questão e ranking por aluno).

Uso: streamlit run app.py
A URL da API vem de CPE_API_URL (padrão http://localhost:8001).
"""
import datetime as dt

import pandas as pd
import streamlit as st

import charts
from api_client import APIError, CPEClient

st.set_page_config(
    page_title="Corretor de Provas OMR",
    page_icon="🖊️",
    layout="wide",
)

ORANGE = "#ef7b17"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=League+Spartan:wght@600;700&family=Open+Sans:wght@400;600&display=swap');
    .cpe-header {
        display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
        border-left: 6px solid """ + ORANGE + """;
        padding: 0.35rem 0 0.35rem 1rem; margin-bottom: 0.5rem;
    }
    .cpe-header h1 {
        font-family: 'League Spartan', sans-serif; font-weight: 700;
        font-size: 2.1rem; line-height: 1.1; letter-spacing: -0.01em; margin: 0;
    }
    .cpe-header p {
        font-family: 'Open Sans', sans-serif; font-size: 0.95rem;
        opacity: 0.75; margin: 0.2rem 0 0 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="cpe-header">
      <div>
        <h1>Corretor de Provas OMR</h1>
        <p>Envie o gabarito e as provas escaneadas, corrija tudo de uma vez e
        acompanhe o desempenho da turma.</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def theme_mode():
    try:
        if st.context.theme.type == "dark":
            return "dark"
        return "light"
    except Exception:
        return "dark" if st.get_option("theme.base") == "dark" else "light"


@st.cache_resource
def get_client() -> CPEClient:
    return CPEClient()


client = get_client()

SUPPORTED_IMAGE_EXTENSIONS = ("png", "jpg", "jpeg")


def _mapping_from_editor(students_df):
    """Turn the editor table into {file: name} and {file: turma} maps."""
    names, classes = {}, {}
    if students_df is None or students_df.empty:
        return names, classes
    for _index, row in students_df.iterrows():
        file_name = row.get("Arquivo")
        if not file_name:
            continue
        if str(row.get("Nome do Aluno") or "").strip():
            names[file_name] = row["Nome do Aluno"].strip()
        if str(row.get("Turma") or "").strip():
            classes[file_name] = row["Turma"].strip()
    return names, classes


def _summarize(long_results: pd.DataFrame) -> pd.DataFrame:
    """One row per student: acertos, erros, em branco and accuracy."""
    if long_results.empty:
        return pd.DataFrame()
    counts = (
        long_results.pivot_table(
            index=["Nome do Aluno", "Turma"],
            columns="Resultado",
            values="Questão",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(columns=charts.RESULT_ORDER, fill_value=0)
        .reset_index()
    )
    counts["Questões"] = counts[charts.RESULT_ORDER].sum(axis=1)
    counts["% de acerto"] = (
        counts[charts.ACERTO] / counts["Questões"].replace(0, pd.NA) * 100
    ).round(1)
    return counts.sort_values(charts.ACERTO, ascending=False).reset_index(drop=True)

# Health banner - a clear message beats a stack trace when the API is down
if not client.health():
    st.error(
        f"Não consegui falar com a API em `{client.base_url}`. "
        "Inicie o backend (uvicorn api.app:app) e recarregue a página."
    )

tab_correcao, tab_dashboard, tab_evolucao, tab_dados = st.tabs(
    ["1️⃣ Correção", "2️⃣ Dashboard", "3️⃣ Evolução", "4️⃣ Dados e downloads"]
)


# --------------------------------------------------------------------------- #
# 1. Correção
# --------------------------------------------------------------------------- #
with tab_correcao:
    st.subheader("🗂️ Dados do simulado")
    meta_columns = st.columns([2, 1, 1])
    exam_name = meta_columns[0].text_input(
        "Nome do simulado", value="Simulado 1", help="Ex.: Simulado 1, ENEM Treino 2..."
    )
    applied_on = meta_columns[1].date_input("Data de aplicação", value=dt.date.today())
    sequence = meta_columns[2].number_input(
        "Nº na sequência", min_value=1, value=1, step=1,
        help="Ordem no tempo, usada para acompanhar a evolução da turma.",
    )

    st.subheader("📄 Gabarito")
    answer_key_file = st.file_uploader(
        "Planilha do gabarito (csv ou xlsx)",
        type=["csv", "xlsx", "xls"],
        help="Precisa ter ao menos a coluna da questão e a da resposta correta.",
    )

    st.subheader("📸 Provas escaneadas")
    exam_files = st.file_uploader(
        "Imagens das folhas de resposta",
        type=list(SUPPORTED_IMAGE_EXTENSIONS),
        accept_multiple_files=True,
    )

    # Optional per-sheet student/turma mapping
    students_df = None
    if exam_files:
        st.caption(f"{len(exam_files)} arquivo(s) prontos para correção.")
        st.subheader("👥 Alunos (opcional)")
        st.caption(
            "Informe o nome e a turma de cada folha. Em branco, o nome vem do arquivo."
        )
        default_rows = [
            {"Arquivo": f.name, "Nome do Aluno": "", "Turma": ""} for f in exam_files
        ]
        students_df = st.data_editor(
            pd.DataFrame(default_rows),
            width="stretch",
            hide_index=True,
            disabled=["Arquivo"],
            key="students_editor",
        )

    ready = bool(answer_key_file) and bool(exam_files)
    if st.button("✅ Corrigir provas", type="primary", disabled=not ready):
        names, classes = _mapping_from_editor(students_df)
        with st.spinner("Corrigindo as provas..."):
            try:
                result = client.grade_images(
                    images=[(f.name, f.getvalue()) for f in exam_files],
                    answer_key_bytes=answer_key_file.getvalue(),
                    answer_key_name=answer_key_file.name,
                    exam_name=exam_name,
                    applied_on=applied_on,
                    sequence=int(sequence),
                    student_names=names or None,
                    student_classes=classes or None,
                )
            except APIError as error:
                result = None
                st.error("Não foi possível corrigir as provas.")
                st.code(str(error))

        if result is not None:
            st.session_state["last_exam_id"] = result["exam_id"]
            st.success(
                f"{result['sheets_ingested']} prova(s) corrigida(s) e salvas. "
                "Confira o dashboard na próxima aba."
            )
            if result.get("log"):
                with st.expander("📋 Log da correção"):
                    st.code(result["log"])

    with st.expander("Já tem uma planilha ResultsByQuestion.csv?"):
        st.caption(
            "Se as provas já foram corrigidas, envie a planilha direto para o banco."
        )
        results_csv = st.file_uploader(
            "ResultsByQuestion.csv", type=["csv"], key="results_csv_upload"
        )
        if results_csv is not None and st.button("Enviar planilha"):
            try:
                res = client.ingest_results_csv(
                    csv_bytes=results_csv.getvalue(),
                    exam_name=exam_name,
                    applied_on=applied_on,
                    sequence=int(sequence),
                )
                st.session_state["last_exam_id"] = res["exam_id"]
                st.success(f"{res['sheets_ingested']} prova(s) importada(s).")
            except APIError as error:
                st.error(str(error))


# --------------------------------------------------------------------------- #
# 2. Dashboard
# --------------------------------------------------------------------------- #
with tab_dashboard:
    try:
        exams = client.exams()
    except APIError as error:
        exams = []
        st.error(str(error))

    if not exams:
        st.info("Nenhum simulado no banco ainda. Corrija provas na aba anterior.")
    else:
        exam_labels = {f"{e['name']}": e["id"] for e in exams}
        default_index = 0
        last_exam_id = st.session_state.get("last_exam_id")
        if last_exam_id in exam_labels.values():
            default_index = list(exam_labels.values()).index(last_exam_id)

        top = st.columns([2, 2, 2, 2])
        chosen_label = top[0].selectbox(
            "Simulado", list(exam_labels.keys()), index=default_index
        )
        exam_id = exam_labels[chosen_label]

        long_results = client.long_format_dataframe(exam_id=exam_id)

        if long_results.empty:
            st.warning("Este simulado ainda não tem respostas.")
        else:
            turmas = sorted(long_results["Turma"].dropna().unique())
            turma_sel = top[1].multiselect("Turma", turmas, default=turmas)
            visible = long_results[long_results["Turma"].isin(turma_sel)]

            alunos = sorted(visible["Nome do Aluno"].dropna().unique())
            aluno_sel = top[2].multiselect("Aluno", alunos, default=alunos)

            areas = sorted(long_results["Área"].dropna().unique())
            area_sel = top[3].multiselect("Área", areas, default=areas)

            subareas = sorted(long_results["Subárea"].dropna().unique())
            subarea_sel = st.multiselect("Subárea", subareas, default=subareas)

            filtered = visible[
                visible["Nome do Aluno"].isin(aluno_sel)
                & long_results["Área"].isin(area_sel)
                & long_results["Subárea"].isin(subarea_sel)
            ]
            st.session_state["filtered_results"] = filtered

            if filtered.empty:
                st.warning("Nenhum dado com os filtros atuais.")
            else:
                mode = theme_mode()
                total = len(filtered)
                acertos = int((filtered["Resultado"] == charts.ACERTO).sum())
                erros = int((filtered["Resultado"] == charts.ERRO).sum())
                em_branco = int((filtered["Resultado"] == charts.NAO_RESPONDEU).sum())

                kpis = st.columns(4)
                kpis[0].metric("Alunos", filtered["Nome do Aluno"].nunique())
                kpis[1].metric("Questões por prova", filtered["Questão"].nunique())
                kpis[2].metric("Taxa de acerto", f"{acertos / total * 100:.1f}%")
                kpis[3].metric(
                    "Respostas",
                    f"{acertos} acertos",
                    delta=f"{erros} erros · {em_branco} em branco",
                    delta_color="off",
                )

                st.divider()

                st.subheader("1. Desempenho por área")
                st.plotly_chart(
                    charts.performance_by_dimension(filtered, "Área", mode),
                    width="stretch",
                )

                st.subheader("2. Desempenho por subárea")
                st.plotly_chart(
                    charts.performance_by_dimension(filtered, "Subárea", mode, height=460),
                    width="stretch",
                )

                st.subheader("3. Taxa de acerto por questão")
                ordem = st.radio(
                    "Ordenar por",
                    ["Número da questão", "Taxa de acerto"],
                    horizontal=True,
                    label_visibility="collapsed",
                )
                st.plotly_chart(
                    charts.accuracy_by_question(
                        filtered, mode, sort_by_rate=ordem == "Taxa de acerto"
                    ),
                    width="stretch",
                )

                st.subheader("4. Desempenho por aluno")
                st.plotly_chart(
                    charts.ranking_by_student(filtered, mode),
                    width="stretch",
                )


# --------------------------------------------------------------------------- #
# 3. Evolução (longitudinal)
# --------------------------------------------------------------------------- #
with tab_evolucao:
    st.caption(
        "A turma está melhorando com o tempo? Compare o desempenho ao longo dos "
        "simulados, no geral e por área."
    )
    try:
        classes = client.classes()
    except APIError as error:
        classes = []
        st.error(str(error))

    if not classes:
        st.info(
            "Nenhuma turma no banco ainda. Corrija provas informando a turma de "
            "cada aluno para acompanhar a evolução."
        )
    else:
        class_labels = {c["name"]: c["id"] for c in classes}
        chosen_class = st.selectbox("Turma", list(class_labels.keys()))
        class_id = class_labels[chosen_class]

        try:
            trend = client.class_trend(class_id)
        except APIError as error:
            trend = {"points": []}
            st.error(str(error))

        points = trend.get("points", [])
        if len(points) < 1:
            st.warning("Esta turma ainda não tem simulados corrigidos.")
        elif len(points) < 2:
            st.info(
                "Só há um simulado para esta turma. Corrija outro simulado para "
                "ver a evolução ao longo do tempo."
            )
            mode = theme_mode()
            st.plotly_chart(
                charts.class_improvement(points, mode), width="stretch"
            )
        else:
            mode = theme_mode()
            first = points[0]["overall"]["taxa_acerto"]
            last = points[-1]["overall"]["taxa_acerto"]
            delta = round(last - first, 1)
            kpis = st.columns(3)
            kpis[0].metric("Simulados", len(points))
            kpis[1].metric("Taxa de acerto atual", f"{last:.1f}%")
            kpis[2].metric(
                "Variação desde o 1º",
                f"{delta:+.1f} pts",
                delta=f"{delta:+.1f}",
                delta_color="normal",
            )

            st.divider()
            st.subheader("Evolução geral da turma")
            st.plotly_chart(
                charts.class_improvement(points, mode), width="stretch"
            )

            st.subheader("Evolução por área")
            st.plotly_chart(
                charts.class_improvement(points, mode, per_subject=True),
                width="stretch",
            )


# --------------------------------------------------------------------------- #
# 4. Dados e downloads
# --------------------------------------------------------------------------- #
with tab_dados:
    filtered = st.session_state.get("filtered_results")
    if filtered is None or filtered.empty:
        st.info("Escolha um simulado no dashboard para ver os dados aqui.")
    else:
        st.subheader("Resumo por aluno")
        summary = _summarize(filtered)
        st.dataframe(summary, width="stretch", hide_index=True)

        st.subheader("Respostas (uma linha por questão)")
        st.dataframe(filtered, width="stretch", hide_index=True)

        download_columns = st.columns(2)
        download_columns[0].download_button(
            "⬇️ Resumo por aluno.csv",
            data=summary.to_csv(index=False).encode("utf-8-sig"),
            file_name="ResumoPorAluno.csv",
            mime="text/csv",
        )
        download_columns[1].download_button(
            "⬇️ Respostas.csv",
            data=filtered.to_csv(index=False).encode("utf-8-sig"),
            file_name="RespostasPorQuestao.csv",
            mime="text/csv",
        )
