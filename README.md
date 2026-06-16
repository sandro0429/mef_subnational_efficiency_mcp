# MEF Subnational Efficiency MCP
## Pipeline Multi-Agente de Auditoría del Gasto Público Peruano

> **Curso:** Applied AI Architecture / AI Engineering
> **Sistema:** Local Multi-Agent Analytics Pipeline via Claude Code CLI + MCP
> **Periodo fiscal analizado:** 2025
> **Datos:** Ministerio de Economía y Finanzas (MEF) — Portal de Datos Abiertos del Perú

---

## Descripción del sistema

Pipeline autónomo multi-skill que combina:
- **MCP Server local** conectado al portal `datosabiertos.gob.pe` (SIAF/MEF 2025)
- **DuckDB** para extracción y filtrado eficiente sin saturar memoria
- **PaddleOCR** para digitalización del archivo histórico de Hacienda 1964
- **Dos Claude Code Skills** cooperativos (Executor + Evaluator)
- **Dashboard Streamlit** de 4 tabs con análisis dual-era (2025 + 1964)

---

## Decisiones Metodológicas

### Universo de análisis: Gobiernos Subnacionales

El análisis se restringe a Gobiernos Regionales (R) y Locales (M) porque son los niveles donde se concentran los mayores cuellos de botella en ejecución de inversión pública. El Gobierno Central opera bajo lógicas presupuestales distintas — contratos marco, transferencias intergubernamentales, deuda pública — que distorsionarían el diagnóstico de capacidad de gasto territorial.

### Solo Proyectos, no Actividades

El clasificador presupuestal distingue entre actividades (gasto corriente recurrente: planillas, bienes de consumo) y proyectos (inversión pública: obras, equipamiento, infraestructura). Las actividades tienen tasas de ejecución cercanas al 100% por responder a obligaciones contractuales preexistentes. El capital congelado ocurre en proyectos, donde la ejecución depende de licitaciones, expedientes técnicos y supervisión de obra. Incluir actividades inflaría artificialmente la tasa de ejecución y ocultaría los problemas reales de inversión.

### Genérica 6: Adquisición de Activos No Financieros

De todas las genéricas del clasificador presupuestal peruano, la Genérica 6 es la que mejor representa la inversión pública tangible: infraestructura vial, edificaciones, maquinaria, equipamiento hospitalario, sistemas de saneamiento. Es el gasto con impacto directo en provisión de servicios públicos y el que la ciudadanía percibe como "obra pública". Las genéricas 1 (personal) y 5 (bienes y servicios) corresponden a gasto operativo y quedan excluidas del análisis.

### Umbral de PIM: S/. 10 millones

El umbral responde a tres criterios. Primero, entidades con presupuestos menores tienen impacto marginal en el capital congelado total — filtrarlas reduce el ruido sin perder información relevante. Segundo, una entidad con PIM superior a 10M debe tener estructura técnica suficiente para ejecutar; si no lo hace, es un problema de gestión, no de escala. Tercero, el umbral está alineado con el enunciado del proyecto que especifica "presupuestos superiores a 10 millones de soles (PEN)". El filtro se aplica post-agrupación, sobre el PIM acumulado por entidad.

### Agrupación diferenciada por nivel de gobierno

La estructura institucional de Regionales y Locales exige agrupaciones distintas. Los Gobiernos Regionales se identifican por **Pliego** (código institucional único), por lo que la agrupación `PLIEGO + FUNCION` captura cuánto invierte cada gobierno regional en cada sector. Los Gobiernos Locales no tienen un identificador único equivalente, por lo que la agrupación correcta es `DEPARTAMENTO + PROVINCIA + DISTRITO + FUNCION`, lo que permite ver el presupuesto de inversión a nivel distrital por función. Esta granularidad es necesaria para identificar exactamente qué municipio tiene capital congelado en qué sector.

### Métrica principal: Tasa de Ejecución

El devengado absoluto no es comparable entre entidades de distinto tamaño. La tasa de ejecución es relativa al presupuesto asignado, lo que permite comparar gobiernos regionales y locales independientemente de su escala:

```
Tasa de Ejecución (%) = (Devengado / PIM) × 100
Capital Congelado     = PIM − Devengado
```

Un departamento con S/. 500M de PIM al 60% de ejecución tiene más capital congelado en términos absolutos que uno con S/. 50M al 30%, pero el segundo tiene un problema de gestión más severo. La tasa permite identificar ambos tipos de problema simultáneamente.

---

## Estructura del repositorio

```
mef_subnational_efficiency_mcp/
│
├── app.py                          # Dashboard Streamlit (4 tabs)
├── README.md
├── requirements.txt
│
├── .claude/
│   └── skills/
│       ├── executor_skill.json     # Agente de procesamiento y construcción
│       └── evaluator_skill.json    # Agente de auditoría y optimización UX
│
├── src/
│   ├── mcp_server.py               # Servidor MCP local (8 herramientas)
│   ├── data_pipeline.py            # Pipeline DuckDB anti-context-flooding
│   ├── ocr_engine.py               # PaddleOCR — 39 páginas del PDF 1964
│   ├── analytical_engine.py        # Métricas: tasa ejecución, capital congelado, rankings
│   └── utils.py                    # Logging, constantes, helpers de periodo
│
├── data/
│   ├── raw_pdfs/                   # hacienda_1964.pdf (archivo histórico)
│   ├── snapshots/                  # Schema JSON (10 filas del CSV MEF)
│   └── processed/                  # Parquets reducidos para el dashboard
│
└── video/
    └── link.txt                    # URL del video de presentación (5 min)
```

---

## Arquitectura Multi-Agente

### Executor Skill (`.claude/skills/executor_skill.json`)
Agente de ingeniería de datos. Sus pasos:
1. Usa MCP para tomar snapshot del CSV (10 filas) — sin descargar el dataset completo
2. Ejecuta `data_pipeline.py` con DuckDB para filtrar y agregar datos
3. Corre `ocr_engine.py` sobre ≥15 páginas del PDF 1964
4. Genera el borrador del dashboard `app.py`

### Evaluator Skill (`.claude/skills/evaluator_skill.json`)
Agente auditor y optimizador. Sus pasos:
1. Extrae muestra independiente del portal vía MCP y cruza vs Parquet del Executor
2. Recalcula métricas para detectar drift de cálculo
3. Inyecta `@st.cache_data`, manejo de errores y CSS en `app.py`
4. Genera reporte de auditoría en `data/processed/evaluator_report_{period}.md`

---

## Resultados 2025

| Indicador | Valor |
|-----------|-------|
| PIM Total (Regionales + Locales) | S/. 29.19B |
| Devengado Total | S/. 24.55B |
| Tasa de Ejecución Nacional | 84.1% |
| Capital Congelado | S/. 4.64B |
| Tasa Regionales | 94.1% |
| Tasa Locales | 73.9% |
| Entidades en Hall of Shame | 32 |
| Páginas 1964 procesadas con OCR | 39 |
| Bloques de texto extraídos | 2,207 |

---

## Instalación

```bash
git clone https://github.com/[usuario]/mef_subnational_efficiency_mcp
cd mef_subnational_efficiency_mcp
conda create -n mef_mcp python=3.11 -y
conda activate mef_mcp
pip install -r requirements.txt
conda install -c conda-forge poppler -y
```

---

## Uso

### 1. Pipeline de datos
```bash
python -m src.data_pipeline --period 2025
```

### 2. Motor analítico
```bash
python -m src.analytical_engine --period 2025
```

### 3. OCR histórico 1964
```bash
python -m src.ocr_engine --pages 1000-1038 --pdf data/raw_pdfs/hacienda_1964.pdf
```

### 4. Dashboard
```bash
streamlit run app.py
```

### 5. Via Claude Code CLI
```bash
claude "run executor_skill for period 2025"
claude "run evaluator_skill for period 2025"
```

---

## MCP Server — Herramientas disponibles

| Herramienta | Descripción |
|-------------|-------------|
| `buscar_datasets` | Busca en datosabiertos.gob.pe vía CKAN API |
| `obtener_detalle_dataset` | URLs de descarga por dataset ID |
| `inspeccionar_esquema_csv` | Snapshot de 10 filas sin descargar el CSV completo |
| `consultar_datastore_filtrado` | Query SQL directa al datastore CKAN |
| `descargar_documento_1964` | Verifica PDF histórico local |
| `procesar_ocr_paginas_1964` | Lanza PaddleOCR sobre páginas seleccionadas |
| `ejecutar_pipeline_datos` | Corre data_pipeline.py como proceso externo |
| `ejecutar_analytical_engine` | Corre analytical_engine.py como proceso externo |

---

## Principio Anti-Context-Flooding

El sistema NUNCA carga el CSV completo (9.8GB) en el contexto del LLM:

```
MCP inspecciona esquema (10 filas snapshot)
    ↓
DuckDB ejecuta query SQL con filtros directamente sobre el CSV
    ↓
Polars procesa el resultado y guarda Parquet reducido (~20KB)
    ↓
Streamlit lee solo el Parquet con @st.cache_data
```

---

## Dashboard — 4 Tabs

| Tab | Contenido |
|-----|-----------|
| 📊 Resumen Ejecutivo | KPIs nacionales 2025 + análisis histórico 1964 (OCR) |
| 🗺️ Distribución Territorial | Rankings regionales y locales por tasa de ejecución y función |
| 🚨 Hall of Shame | Entidades con PIM > 10M y ejecución < 40% |
| 🤖 Audit Log & Playground | Reporte del Evaluator + CLI reference |

---

## Video de presentación

Ver `https://drive.google.com/drive/folders/1ymrC1IwmIt8bWQYrIc5TzUo0CNfeqXek?usp=sharing`

