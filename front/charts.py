"""Charts for the corrected sheets.

Ported unchanged from the backend's webapp/dashboard.py: desempenho por área,
por subárea, taxa de acerto por questão and ranking por aluno. The only change
from the original is that the Resultado constants are defined here instead of
imported from the old pipeline module, so front/ carries no backend dependency.

Every chart reads the canonical long-format DataFrame (Nome do Aluno, Turma,
Área, Subárea, Número da questão, Questão, Resposta do aluno, Resultado), which
is exactly what api_client.long_format_dataframe returns.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Resultado labels - the values the API sends in the 'Resultado' column
ACERTO, ERRO, NAO_RESPONDEU = "Acerto", "Erro", "Não Respondeu"
RESULT_ORDER = [ACERTO, ERRO, NAO_RESPONDEU]

# Status palette - fixed roles, never reused as series colors. The legend and the
# direct labels carry the meaning too, so nothing rides on hue alone.
#
# Steps derived from the CPE USP palette (#3676bb blue, #ef7b17 orange) and then
# snapped until every check passed against the surfaces below. Blue vs orange
# instead of the green/red this used to carry: that pair measured only ΔE 4.1
# under deuteranopia, far below the 6-8 floor, while blue/orange clears 16.
RESULT_COLORS = {
    "light": {ACERTO: "#2f6cae", ERRO: "#d96e10", NAO_RESPONDEU: "#748ba3"},
    "dark": {ACERTO: "#4a8ed0", ERRO: "#d1740f", NAO_RESPONDEU: "#7f93a8"},
}
# Texture repeats the distinction for print and forced-colors, where hue is lost
# entirely - the palette no longer depends on it, but the fallback stays.
RESULT_PATTERNS = {ACERTO: "", ERRO: "/", NAO_RESPONDEU: "."}
ACCENT = {"light": "#3676bb", "dark": "#4a8ed0"}

GRID_COLOR = {"light": "rgba(17,56,92,0.12)", "dark": "rgba(232,238,244,0.12)"}
TEXT_COLOR = {"light": "#4a5a6e", "dark": "#a8bacd"}
# The page background set in .streamlit/config.toml - used as the spacer between
# stacked segments and as the pattern background
SURFACE = {"light": "#f6f6f6", "dark": "#0d1b2a"}


def style(fig, mode="light", height=420, showlegend=True, bargap=0.4):
    """Recessive grid and axes, transparent surface so it sits on the app's own."""
    fig.update_layout(
        template="plotly_dark" if mode == "dark" else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        font=dict(color=TEXT_COLOR[mode], size=13),
        showlegend=showlegend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title_text="",
            traceorder="normal",
        ),
        bargap=bargap,
        bargroupgap=0.08,
        hovermode="closest",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID_COLOR[mode])
    fig.update_yaxes(
        showgrid=True, gridcolor=GRID_COLOR[mode], zeroline=False, linecolor="rgba(0,0,0,0)"
    )
    return fig


def _result_bars(long_results, dimension, mode, height, tickangle=0):
    # Every result gets a slot in every group, so an absent combination reads as
    # zero instead of shifting the remaining bars sideways
    categories = sorted(long_results[dimension].dropna().unique())
    counts = (
        long_results.groupby([dimension, "Resultado"], dropna=False)
        .size()
        .reindex(
            pd.MultiIndex.from_product(
                [categories, RESULT_ORDER], names=[dimension, "Resultado"]
            ),
            fill_value=0,
        )
        .reset_index(name="Quantidade")
    )
    fig = px.bar(
        counts,
        x=dimension,
        y="Quantidade",
        color="Resultado",
        pattern_shape="Resultado",
        barmode="group",
        text="Quantidade",
        category_orders={"Resultado": RESULT_ORDER},
        color_discrete_map=RESULT_COLORS[mode],
        pattern_shape_map=RESULT_PATTERNS,
    )
    fig.update_traces(
        marker_cornerradius=6,
        marker_line_width=0,
        marker_pattern_size=7,
        marker_pattern_solidity=0.22,
        marker_pattern_fgcolor=SURFACE[mode],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>",
    )
    fig.update_xaxes(title_text="", tickangle=tickangle)
    fig.update_yaxes(title_text="Questões")
    return style(fig, mode, height=height)


def performance_by_dimension(long_results, dimension, mode="light", height=420):
    """Acerto / erro / em branco per área or subárea."""
    tickangle = -30 if long_results[dimension].nunique() > 5 else 0
    return _result_bars(long_results, dimension, mode, height, tickangle)


def accuracy_by_question(long_results, mode="light", height=430, sort_by_rate=False):
    """Taxa de acerto per question.

    A percentage rather than a headcount: with a handful of sheets the raw count
    only ever spans 0-3 and says nothing about which questions were hard.
    """
    per_question = (
        long_results.groupby(["Número da questão", "Questão"], dropna=False)
        .agg(
            Acertos=("Resultado", lambda values: (values == ACERTO).sum()),
            Respostas=("Resultado", "size"),
        )
        .reset_index()
    )
    per_question["Taxa"] = (
        per_question["Acertos"] / per_question["Respostas"].replace(0, 1) * 100
    ).round(1)
    per_question = per_question.sort_values(
        "Taxa" if sort_by_rate else "Número da questão"
    )
    overall = round(
        (long_results["Resultado"] == ACERTO).sum() / max(len(long_results), 1) * 100, 1
    )

    fig = px.bar(
        per_question,
        x="Questão",
        y="Taxa",
        custom_data=["Acertos", "Respostas"],
        color_discrete_sequence=[ACCENT[mode]],
    )
    fig.update_traces(
        marker_cornerradius=6,
        marker_line_width=0,
        hovertemplate=(
            "<b>%{x}</b><br>Taxa de acerto: %{y}%"
            "<br>%{customdata[0]} de %{customdata[1]} alunos<extra></extra>"
        ),
    )
    fig.add_hline(
        y=overall,
        line=dict(color=TEXT_COLOR[mode], width=1, dash="dash"),
        annotation_text=f"média geral {overall}%",
        # À esquerda para não encostar na borda, e sobre a superfície da página
        # para continuar legível quando uma barra alta passar por baixo
        annotation_position="top left",
        annotation_font=dict(color=TEXT_COLOR[mode], size=12),
        annotation_bgcolor=SURFACE[mode],
        annotation_borderpad=3,
    )
    fig.update_xaxes(
        type="category",
        title_text="",
        tickangle=-90,
        tickfont=dict(size=10),
    )
    fig.update_yaxes(title_text="Taxa de acerto (%)", range=[0, 105], dtick=25)
    return style(fig, mode, height=height, showlegend=False, bargap=0.25)


def ranking_by_student(long_results, mode="light", height=None):
    """Stacked acerto / erro / em branco per student, longest bar on top."""
    counts = (
        long_results.groupby(["Nome do Aluno", "Resultado"], dropna=False)
        .size()
        .unstack("Resultado", fill_value=0)
        .reindex(columns=RESULT_ORDER, fill_value=0)
        .sort_values(ACERTO)
    )
    fig = go.Figure()
    for result in RESULT_ORDER:
        fig.add_bar(
            y=counts.index,
            x=counts[result],
            name=result,
            orientation="h",
            marker=dict(
                color=RESULT_COLORS[mode][result],
                line=dict(width=2, color=SURFACE[mode]),
                pattern=dict(
                    shape=RESULT_PATTERNS[result],
                    size=7,
                    solidity=0.22,
                    fgcolor=SURFACE[mode],
                ),
            ),
            hovertemplate="<b>%{y}</b><br>" + result + ": %{x}<extra></extra>",
        )
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Questões", showgrid=True, gridcolor=GRID_COLOR[mode])
    fig.update_yaxes(title_text="", showgrid=False)
    return style(
        fig, mode, height=height or max(240, 44 * len(counts) + 100), bargap=0.45
    )


def class_improvement(points, mode="light", per_subject=False, height=430):
    """Line chart of a class's accuracy across exams, over time.

    `points` is the list the API's /trends endpoint returns: each item has
    exam_name, sequence/applied_on and an `overall` accuracy, plus a `by_subject`
    map. With per_subject=False it draws the overall trend; with True it draws one
    line per subject so subject-level improvement stands out.
    """
    if not points:
        fig = go.Figure()
        return style(fig, mode, height=height, showlegend=False)

    labels = [p["exam_name"] for p in points]

    fig = go.Figure()
    if per_subject:
        subjects = sorted(
            {name for p in points for name in (p.get("by_subject") or {})}
        )
        palette = _subject_palette(subjects, mode)
        for subject in subjects:
            fig.add_scatter(
                x=labels,
                y=[(p.get("by_subject") or {}).get(subject) for p in points],
                mode="lines+markers",
                name=subject,
                line=dict(width=2, color=palette[subject]),
                marker=dict(size=8),
                connectgaps=True,
                hovertemplate="<b>%{x}</b><br>" + subject + ": %{y:.1f}%<extra></extra>",
            )
    else:
        fig.add_scatter(
            x=labels,
            y=[p["overall"]["taxa_acerto"] for p in points],
            mode="lines+markers+text",
            name="Turma",
            text=[f"{p['overall']['taxa_acerto']:.0f}%" for p in points],
            textposition="top center",
            line=dict(width=3, color=ACCENT[mode]),
            marker=dict(size=10),
            hovertemplate="<b>%{x}</b><br>Taxa de acerto: %{y:.1f}%<extra></extra>",
        )

    fig.update_xaxes(title_text="", type="category")
    fig.update_yaxes(title_text="Taxa de acerto (%)", range=[0, 105], dtick=25)
    return style(fig, mode, height=height, showlegend=per_subject)


def _subject_palette(subjects, mode):
    """Stable, high-contrast colors per subject line."""
    # Extends the brand pair with a few distinguishable hues for extra subjects
    base = (
        ["#3676bb", "#ef7b17", "#2e8b57", "#8e44ad", "#c0392b", "#16a085"]
        if mode == "light"
        else ["#4a8ed0", "#d1740f", "#3fbf7f", "#a569bd", "#e07a6a", "#48c9b0"]
    )
    return {subject: base[index % len(base)] for index, subject in enumerate(subjects)}
