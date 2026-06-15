"""
app.py — Dashboard Streamlit: MEF Subnational Efficiency Audit (2025 + 1964)

Tabs:
    1  Executive Macro Summary & Dual-Era Opening Dashboard
    2  Territorial Distribution & Geospatial Analysis (2025)
    3  Budget "Hall of Shame" & Anomaly Explorer (2025)
    4  Multi-Agent Audit Log & Live Playground (2025)

Ejecución:
    streamlit run app.py
"""

import json
import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import polars as pl
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from src.utils import DATA_PROC

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MEF Subnational Efficiency Audit",
    page_icon="🇵🇪",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; line-height: 1.6; }
    [data-testid="metric-container"] {
        background: #f8f9fc; border-radius: 10px;
        padding: 16px 20px; border-left: 4px solid #1a56db;
    }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; padding: 10px 20px; }
    .shame-header {
        background: linear-gradient(90deg, #ff4b4b22, transparent);
        border-left: 4px solid #ff4b4b; padding: 12px 16px;
        border-radius: 0 8px 8px 0; margin-bottom: 16px;
    }
    .era-divider {
        height: 3px;
        background: linear-gradient(90deg, #1a56db, #7c3aed, #db2777);
        margin: 28px 0; border-radius: 2px;
    }
    .section-title {
        font-size: 1.1rem; font-weight: 700;
        color: #1a56db; margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Flag_of_Peru.svg/320px-Flag_of_Peru.svg.png",
        width=60
    )
    st.title("MEF Audit Pipeline")
    st.caption("Ministerio de Economía y Finanzas — Perú")
    st.divider()

    period = st.selectbox(
        "Periodo fiscal",
        ["2025", "2025-Q3", "2025-Q2", "2025-Q1"],
        index=0,
    )

    nivel_filtro = st.radio(
        "Nivel de gobierno",
        ["Ambos", "Solo Regionales", "Solo Locales"],
        index=0,
    )

    st.divider()
    st.caption("🤖 Pipeline multi-agente")
    st.caption("Executor + Evaluator Skills")
    st.caption("Claude Code CLI + MCP")


# ── Loaders con @st.cache_data ────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_kpis(period: str) -> dict:
    safe = period.replace("-", "_")
    path = DATA_PROC / f"kpis_{safe}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

@st.cache_data(ttl=3600, show_spinner=False)
def load_ranking_regionales(period: str) -> pd.DataFrame | None:
    safe = period.replace("-", "_")
    path = DATA_PROC / f"ranking_regionales_{safe}.parquet"
    if not path.exists():
        return None
    return pl.read_parquet(path).to_pandas()

@st.cache_data(ttl=3600, show_spinner=False)
def load_ranking_reg_funcion(period: str) -> pd.DataFrame | None:
    safe = period.replace("-", "_")
    path = DATA_PROC / f"ranking_reg_funcion_{safe}.parquet"
    if not path.exists():
        return None
    return pl.read_parquet(path).to_pandas()

@st.cache_data(ttl=3600, show_spinner=False)
def load_ranking_locales_dept(period: str) -> pd.DataFrame | None:
    safe = period.replace("-", "_")
    path = DATA_PROC / f"ranking_locales_dept_{safe}.parquet"
    if not path.exists():
        return None
    return pl.read_parquet(path).to_pandas()

@st.cache_data(ttl=3600, show_spinner=False)
def load_ranking_loc_funcion(period: str) -> pd.DataFrame | None:
    safe = period.replace("-", "_")
    path = DATA_PROC / f"ranking_loc_funcion_{safe}.parquet"
    if not path.exists():
        return None
    return pl.read_parquet(path).to_pandas()

@st.cache_data(ttl=3600, show_spinner=False)
def load_shame(period: str) -> pd.DataFrame | None:
    safe = period.replace("-", "_")
    path = DATA_PROC / f"hall_of_shame_{safe}.parquet"
    if not path.exists():
        return None
    return pl.read_parquet(path).to_pandas()

@st.cache_data(ttl=86400, show_spinner=False)
def load_ocr_1964() -> pd.DataFrame | None:
    path = DATA_PROC / "ocr_1964_extracted.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)

@st.cache_data(ttl=3600, show_spinner=False)
def load_evaluator_report(period: str) -> str:
    safe = period.replace("-", "_")
    path = DATA_PROC / f"evaluator_report_{safe}.md"
    if not path.exists():
        return "_El reporte del Evaluator aún no ha sido generado para este periodo._"
    return path.read_text(encoding="utf-8")


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Resumen Ejecutivo",
    "🗺️ Distribución Territorial",
    "🚨 Hall of Shame",
    "🤖 Audit Log & Playground",
])


# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — Executive Macro Summary & Dual-Era Opening Dashboard
# ════════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── Sección 2025 ──────────────────────────────────────────────────────────
    st.subheader("🇵🇪 Ejecución de Inversión Pública 2025")
    st.caption("Proyectos de adquisición de activos no financieros — Gobiernos Regionales y Locales")

    kpis = load_kpis(period)

    if not kpis:
        st.warning(
            f"⚠️ No hay datos para el periodo **{period}**. Ejecuta primero:\n\n"
            f"```bash\npython -m src.data_pipeline --period {period}\n"
            f"python -m src.analytical_engine --period {period}\n```"
        )
    else:
        # KPIs nacionales
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "PIM Total (S/.)",
            f"{kpis.get('pim_total', 0)/1e9:.2f}B",
            help="Presupuesto Institucional Modificado — proyectos activos NF"
        )
        c2.metric(
            "Devengado Total (S/.)",
            f"{kpis.get('devengado_total', 0)/1e9:.2f}B",
            help="Gasto efectivamente ejecutado"
        )
        c3.metric(
            "Tasa de Ejecución",
            f"{kpis.get('tasa_ejecucion_pct', 0):.1f}%",
            help="Devengado / PIM × 100"
        )
        c4.metric(
            "Capital Congelado (S/.)",
            f"{kpis.get('capital_congelado', 0)/1e9:.2f}B",
            help="PIM no ejecutado = PIM - Devengado"
        )

        st.divider()

        # KPIs por nivel
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🏛️ Gobiernos Regionales**")
            r1, r2, r3 = st.columns(3)
            r1.metric("PIM", f"S/. {kpis.get('pim_regionales', 0)/1e9:.2f}B")
            r2.metric("Devengado", f"S/. {kpis.get('devengado_regionales', 0)/1e9:.2f}B")
            r3.metric("Tasa", f"{kpis.get('tasa_regionales', 0):.1f}%")

        with col2:
            st.markdown("**🏘️ Gobiernos Locales**")
            l1, l2, l3 = st.columns(3)
            l1.metric("PIM", f"S/. {kpis.get('pim_locales', 0)/1e9:.2f}B")
            l2.metric("Devengado", f"S/. {kpis.get('devengado_locales', 0)/1e9:.2f}B")
            l3.metric("Tasa", f"{kpis.get('tasa_locales', 0):.1f}%")

        st.divider()
        st.markdown("**🤖 Análisis del Advisor IA — Cuellos de Botella Fiscales 2025**")
        tasa = kpis.get('tasa_ejecucion_pct', 0)
        congelado = kpis.get('capital_congelado', 0)
        n_reg = kpis.get('n_gobiernos_regionales', 0)
        n_loc = kpis.get('n_gobiernos_locales', 0)
        st.info(
            f"Al cierre del periodo fiscal **{period}**, los {n_reg} gobiernos regionales y "
            f"{n_loc:,} gobiernos locales registran una tasa de ejecución del **{tasa:.1f}%** "
            f"en proyectos de adquisición de activos no financieros. El capital congelado "
            f"asciende a **S/. {congelado/1e9:.2f}B**, concentrado principalmente en "
            f"infraestructura vial, equipamiento hospitalario y obras de saneamiento. "
            f"Los cuellos de botella se originan en retrasos de procesos de contratación "
            f"pública bajo la Ley 30225 y en la baja capacidad de gasto de gobiernos "
            f"locales con presupuestos superiores a S/. 10M."
        )

    # ── Divider visual ────────────────────────────────────────────────────────
    st.markdown('<div class="era-divider"></div>', unsafe_allow_html=True)

    # ── Sección 1964 ──────────────────────────────────────────────────────────
    st.subheader("📜 Archivo Histórico 1964 — Ministerio de Hacienda y Comercio")
    st.caption("Datos extraídos mediante PaddleOCR del documento oficial. Registro histórico independiente.")

    ocr_df = load_ocr_1964()
    if ocr_df is None:
        st.warning(
            "⚠️ No hay datos OCR 1964. Ejecuta:\n\n"
            "```bash\npython -m src.ocr_engine --pages 1-30 --pdf data/raw_pdfs/hacienda_1964.pdf\n```"
        )
    else:
        pages_covered = ocr_df["page_number"].nunique()
        total_blocks  = len(ocr_df)
        avg_conf      = ocr_df["confidence"].mean()

        m1, m2, m3 = st.columns(3)
        m1.metric("Páginas procesadas", pages_covered)
        m2.metric("Bloques de texto", f"{total_blocks:,}")
        m3.metric("Confianza promedio OCR", f"{avg_conf:.1%}")

        col1, col2 = st.columns(2)
        with col1:
            blocks_per_page = (
                ocr_df.groupby("page_number")
                .size()
                .reset_index(name="n_bloques")
            )
            fig1 = px.bar(
                blocks_per_page,
                x="page_number", y="n_bloques",
                title="Densidad de texto extraído por página (PaddleOCR 1964)",
                labels={"page_number": "Página", "n_bloques": "Bloques"},
                color="n_bloques",
                color_continuous_scale="Blues",
            )
            fig1.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            fig2 = px.histogram(
                ocr_df, x="confidence", nbins=20,
                title="Distribución de confianza OCR — Documento 1964",
                labels={"confidence": "Confianza (0-1)"},
                color_discrete_sequence=["#7c3aed"],
            )
            fig2.update_layout(height=300)
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("**Conclusiones extraídas del archivo histórico 1964:**")
        high_conf = ocr_df[ocr_df["confidence"] > 0.85].sort_values("page_number")
        sample_texts = high_conf["text"].head(20).tolist()
        for i, text in enumerate(sample_texts, 1):
            st.markdown(f"{i}. _{text}_")


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — Territorial Distribution & Geospatial Analysis (2025)
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("🗺️ Distribución Territorial de la Inversión Pública 2025")
    st.caption("Proyectos de activos no financieros — Tasa de ejecución = Devengado / PIM × 100")

    rank_reg     = load_ranking_regionales(period)
    rank_reg_fun = load_ranking_reg_funcion(period)
    rank_loc_dep = load_ranking_locales_dept(period)
    rank_loc_fun = load_ranking_loc_funcion(period)

    subtab1, subtab2 = st.tabs(["🏛️ Gobiernos Regionales", "🏘️ Gobiernos Locales"])

    # ── Regionales ────────────────────────────────────────────────────────────
    with subtab1:
        if rank_reg is None:
            st.warning("Sin datos de regionales. Ejecuta analytical_engine.py primero.")
        else:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = px.bar(
                    rank_reg.sort_values("tasa_ejecucion_pct"),
                    x="tasa_ejecucion_pct",
                    y="pliego",
                    orientation="h",
                    title=f"Tasa de Ejecución por Gobierno Regional — {period}",
                    labels={
                        "tasa_ejecucion_pct": "Tasa de Ejecución (%)",
                        "pliego": "Gobierno Regional"
                    },
                    color="tasa_ejecucion_pct",
                    color_continuous_scale="RdYlGn",
                    range_color=[0, 100],
                )
                fig.add_vline(
                    x=40, line_dash="dash", line_color="red",
                    annotation_text="Umbral crítico 40%"
                )
                fig.update_layout(height=600, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("**Capital Congelado por Región**")
                top_congelado = rank_reg.nlargest(10, "capital_congelado")[
                    ["pliego", "pim_total", "devengado_total",
                     "tasa_ejecucion_pct", "capital_congelado"]
                ].copy()
                top_congelado["capital_M"] = (top_congelado["capital_congelado"] / 1e6).round(1)
                top_congelado["pim_M"]     = (top_congelado["pim_total"] / 1e6).round(1)
                st.dataframe(
                    top_congelado[["pliego", "pim_M", "tasa_ejecucion_pct", "capital_M"]].rename(columns={
                        "pliego":             "Gobierno Regional",
                        "pim_M":              "PIM (M S/.)",
                        "tasa_ejecucion_pct": "Tasa (%)",
                        "capital_M":          "Congelado (M S/.)",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

        if rank_reg_fun is not None:
            st.divider()
            st.markdown("**Tasa de ejecución por función presupuestal — Regionales**")
            fig3 = px.bar(
                rank_reg_fun.sort_values("tasa_ejecucion_pct"),
                x="tasa_ejecucion_pct",
                y="funcion",
                orientation="h",
                title="¿Qué sectores tienen más dificultad de ejecución en regionales?",
                labels={
                    "tasa_ejecucion_pct": "Tasa de Ejecución (%)",
                    "funcion": "Función"
                },
                color="tasa_ejecucion_pct",
                color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                hover_data=["pim_total", "devengado_total", "n_regionales"],
            )
            fig3.add_vline(x=40, line_dash="dash", line_color="red")
            fig3.update_layout(height=500, showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)

    # ── Locales ───────────────────────────────────────────────────────────────
    with subtab2:
        if rank_loc_dep is None:
            st.warning("Sin datos de locales. Ejecuta analytical_engine.py primero.")
        else:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = px.bar(
                    rank_loc_dep.sort_values("tasa_ejecucion_pct"),
                    x="tasa_ejecucion_pct",
                    y="departamento",
                    orientation="h",
                    title=f"Tasa de Ejecución Gobiernos Locales por Departamento — {period}",
                    labels={
                        "tasa_ejecucion_pct": "Tasa de Ejecución (%)",
                        "departamento": "Departamento"
                    },
                    color="tasa_ejecucion_pct",
                    color_continuous_scale="RdYlGn",
                    range_color=[0, 100],
                    hover_data=["pim_total", "devengado_total", "n_distritos"],
                )
                fig.add_vline(
                    x=40, line_dash="dash", line_color="red",
                    annotation_text="Umbral crítico 40%"
                )
                fig.update_layout(height=600, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("**Top 10 departamentos con más capital congelado (locales)**")
                top_loc = rank_loc_dep.nlargest(10, "capital_congelado")[
                    ["departamento", "pim_total", "tasa_ejecucion_pct",
                     "capital_congelado", "n_distritos"]
                ].copy()
                top_loc["capital_M"] = (top_loc["capital_congelado"] / 1e6).round(1)
                top_loc["pim_M"]     = (top_loc["pim_total"] / 1e6).round(1)
                st.dataframe(
                    top_loc[["departamento", "pim_M", "tasa_ejecucion_pct",
                              "capital_M", "n_distritos"]].rename(columns={
                        "departamento":       "Departamento",
                        "pim_M":              "PIM (M S/.)",
                        "tasa_ejecucion_pct": "Tasa (%)",
                        "capital_M":          "Congelado (M S/.)",
                        "n_distritos":        "Distritos",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

        if rank_loc_fun is not None:
            st.divider()
            st.markdown("**Tasa de ejecución por función presupuestal — Locales**")
            fig4 = px.bar(
                rank_loc_fun.sort_values("tasa_ejecucion_pct"),
                x="tasa_ejecucion_pct",
                y="funcion",
                orientation="h",
                title="¿Qué sectores tienen más dificultad de ejecución en municipios?",
                labels={
                    "tasa_ejecucion_pct": "Tasa de Ejecución (%)",
                    "funcion": "Función"
                },
                color="tasa_ejecucion_pct",
                color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                hover_data=["pim_total", "devengado_total", "n_distritos"],
            )
            fig4.add_vline(x=40, line_dash="dash", line_color="red")
            fig4.update_layout(height=500, showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — Hall of Shame & Anomaly Explorer (2025)
# ════════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown(
        '<div class="shame-header">'
        '<h3 style="margin:0">🚨 Hall of Shame — Peores Ejecutores de Inversión 2025</h3>'
        '</div>',
        unsafe_allow_html=True
    )
    st.caption("Entidades con PIM > S/. 10M y tasa de ejecución < 40% en proyectos de activos no financieros")

    shame_df = load_shame(period)

    if shame_df is None:
        st.warning("Sin datos. Ejecuta analytical_engine.py primero.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Entidades en riesgo", len(shame_df))
        m2.metric(
            "Capital congelado total",
            f"S/. {shame_df['capital_congelado'].sum()/1e9:.2f}B"
        )
        m3.metric(
            "Tasa promedio",
            f"{shame_df['tasa_ejecucion_pct'].mean():.1f}%"
        )

        st.divider()

        # Filtros interactivos
        col1, col2, col3 = st.columns(3)
        with col1:
            niveles = ["Todos"] + sorted(shame_df["nivel"].dropna().unique().tolist()) \
                if "nivel" in shame_df.columns else ["Todos"]
            nivel_filter = st.selectbox("Nivel de gobierno", niveles)
        with col2:
            max_tasa = st.slider("Tasa máxima (%)", 0, 100, 40)
        with col3:
            min_pim_filter = st.number_input(
                "PIM mínimo (M S/.)", min_value=0, value=10, step=5
            )

        # Aplicar filtros
        filtered = shame_df[shame_df["tasa_ejecucion_pct"] <= max_tasa].copy()
        filtered = filtered[filtered["pim_total"] >= min_pim_filter * 1e6]
        if "nivel" in filtered.columns and nivel_filter != "Todos":
            filtered = filtered[filtered["nivel"] == nivel_filter]

        # Formatear columnas para display
        display = filtered.copy()
        for col in ["pim_total", "devengado_total", "capital_congelado"]:
            if col in display.columns:
                display[col] = (display[col] / 1e6).round(1)

        st.dataframe(
            display.rename(columns={
                "nivel":              "Nivel",
                "entidad":            "Entidad",
                "pim_total":          "PIM (M S/.)",
                "devengado_total":    "Devengado (M S/.)",
                "tasa_ejecucion_pct": "Tasa (%)",
                "capital_congelado":  "Congelado (M S/.)",
            }).style.background_gradient(
                subset=["Tasa (%)"], cmap="RdYlGn", vmin=0, vmax=100
            ),
            use_container_width=True,
            height=400,
        )

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if len(filtered) > 0:
                fig = px.scatter(
                    filtered,
                    x="pim_total",
                    y="tasa_ejecucion_pct",
                    size="capital_congelado",
                    color="nivel" if "nivel" in filtered.columns else "tasa_ejecucion_pct",
                    hover_data=["entidad"] if "entidad" in filtered.columns else None,
                    title="PIM vs Tasa de Ejecución (tamaño = capital congelado)",
                    labels={
                        "pim_total":          "PIM (S/.)",
                        "tasa_ejecucion_pct": "Tasa de Ejecución (%)",
                    },
                )
                fig.add_hline(
                    y=40, line_dash="dash", line_color="red",
                    annotation_text="Umbral crítico 40%"
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if "nivel" in filtered.columns and len(filtered) > 0:
                by_nivel = filtered.groupby("nivel").agg(
                    n_entidades=("entidad", "count"),
                    capital_total=("capital_congelado", "sum"),
                ).reset_index()
                fig2 = px.bar(
                    by_nivel,
                    x="nivel", y="capital_total",
                    title="Capital congelado por nivel de gobierno",
                    labels={
                        "nivel":         "Nivel",
                        "capital_total": "Capital Congelado (S/.)"
                    },
                    color="nivel",
                    color_discrete_map={"REGIONAL": "#1a56db", "LOCAL": "#7c3aed"},
                )
                st.plotly_chart(fig2, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 — Multi-Agent Audit Log & Live Playground (2025)
# ════════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🤖 Reporte del Evaluator Agent")
    report_md = load_evaluator_report(period)
    st.markdown(report_md)

    st.divider()
    st.subheader("⚡ Live Playground — Re-ejecutar Pipeline")

    col1, col2 = st.columns([3, 1])
    with col1:
        custom_period = st.text_input(
            "Periodo a procesar",
            value=period,
            placeholder="ej: 2025, 2025-Q4"
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("🚀 Ver comandos", type="primary"):
            st.code(
                f"python -m src.data_pipeline --period {custom_period}\n"
                f"python -m src.analytical_engine --period {custom_period}",
                language="bash"
            )

    st.divider()
    st.subheader("📋 Arquitectura del Sistema")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Pipeline de datos (Executor Skill)**")
        st.code("""
# 1. Snapshot anti-context-flooding
python -m src.data_pipeline --period 2025

# Filtros aplicados:
# - NIVEL_GOBIERNO IN ('R', 'M')
# - TIPO_ACT_PROY = '2' (solo proyectos)
# - GENERICA = '6' (activos no financieros)

# Salida:
# data/processed/regionales_2025.parquet
# data/processed/locales_2025.parquet
""", language="bash")

    with col2:
        st.markdown("**Métricas (Evaluator Skill)**")
        st.code("""
# 2. Cálculo de indicadores
python -m src.analytical_engine --period 2025

# Métricas calculadas:
# tasa_ejecucion = devengado / pim × 100
# capital_congelado = pim - devengado

# Salida:
# kpis_2025.json
# ranking_regionales_2025.parquet
# hall_of_shame_2025.parquet
""", language="bash")

    st.divider()
    st.subheader("🔧 MCP Tools disponibles")
    st.code("""
buscar_datasets              → Busca en datosabiertos.gob.pe vía CKAN API
obtener_detalle_dataset      → URLs de descarga por dataset ID
inspeccionar_esquema_csv     → Snapshot de 10 filas sin descargar completo
consultar_datastore_filtrado → Query SQL directa al datastore CKAN
descargar_documento_1964     → Verifica PDF histórico local
procesar_ocr_paginas_1964    → Lanza PaddleOCR sobre páginas seleccionadas
ejecutar_pipeline_datos      → Corre data_pipeline.py como proceso externo
ejecutar_analytical_engine   → Corre analytical_engine.py como proceso externo
""", language="text")