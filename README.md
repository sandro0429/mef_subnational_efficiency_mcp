# MEF Subnational Efficiency MCP

Multi-agent AI pipeline para auditar y visualizar la ejecución presupuestal
subnacional del Perú 2025, combinando datos en tiempo real del portal MEF
con análisis histórico del presupuesto de 1964 vía OCR.

## Arquitectura

```
mef_subnational_efficiency_mcp/
├── src/
│   ├── utils.py               # Configuración base, rutas y logging
│   ├── data_pipeline.py       # Descarga y limpieza de datos 2025 (streaming)
│   ├── analytical_engine.py   # KPIs, rankings y Hall of Shame
│   ├── mcp_server.py          # Servidor MCP — herramientas para Claude Code
│   └── ocr_engine.py          # Extracción de tablas del PDF histórico 1964
├── app.py                     # Dashboard Streamlit (4 tabs)
├── data/
│   ├── raw_pdfs/              # PDF histórico 1964
│   ├── snapshots/             # Schema del CSV (primeras 10 filas)
│   └── processed/             # Parquets generados por el pipeline
├── .claude/skills/            # Skills del Executor y Evaluator
└── logs/                      # Logs rotativos del sistema
```

## Pipeline de datos

```
CSV remoto MEF (~1 GB)
    ↓ streaming chunk a chunk
    ↓ filtro al vuelo: año=2025, mes=12, PIM ≥ S/.10M
    ↓ solo columnas relevantes en RAM
    ↓ cast numérico + métricas
    → data/processed/budget_2025_12.parquet
    → data/processed/kpis_2025_12.json
    → data/processed/ranking_dept_2025_12.parquet
    → data/processed/hall_of_shame_2025_12.parquet
    → data/processed/distribucion_funcional_2025_12.parquet
    → data/processed/distribucion_sector_2025_12.parquet
```

## Métricas definidas

| Métrica | Fórmula | Uso |
|---|---|---|
| Avance (%) | Devengado / PIM × 100 | KPI principal |
| Saldo no devengado | PIM − Devengado | Capital congelado |
| Hall of Shame | PIM ≥ S/.10M y avance < 40% | Tab 3 |

El umbral del Hall of Shame se fijó en **40%** porque diciembre es el último
mes del año fiscal — una entidad con más de S/.10M presupuestados y menos
del 40% ejecutado representa subejecución crítica.

## Instalación

```bash
git clone https://github.com/sandro0429/mef_subnational_efficiency_mcp
cd mef_subnational_efficiency_mcp
pip install -r requirements.txt
```

## Uso

```bash
# 1. Generar Parquet de datos 2025
python -m src.data_pipeline --period 2025-12

# 2. Calcular KPIs, rankings y Hall of Shame
python -m src.analytical_engine --period 2025-12

# 3. Correr el dashboard
streamlit run app.py
```

## Fuentes de datos

| Fuente | URL | Descripción |
|---|---|---|
| MEF — Gasto Mensual 2025 | fs.datosabiertos.mef.gob.pe | CSV ~1 GB, actualización mensual |
| Portal CKAN | datosabiertos.gob.pe | API de búsqueda de datasets |
| PDF histórico 1964 | fuenteshistoricasdelperu.com | Presupuesto General de la República |

## Columnas del dataset 2025

El CSV del MEF contiene 63 columnas. El pipeline normaliza las siguientes:

| Columna original | Nombre normalizado | Tipo |
|---|---|---|
| ANO_EJE | anio | str |
| MES_EJE | mes | str |
| NIVEL_GOBIERNO_NOMBRE | nivel_gobierno | str |
| SECTOR_NOMBRE | sector | str |
| PLIEGO_NOMBRE | entidad | str |
| EJECUTORA_NOMBRE | unidad_ejecutora | str |
| DEPARTAMENTO_EJECUTORA_NOMBRE | departamento | str |
| FUNCION_NOMBRE | funcion | str |
| MONTO_PIM | pim | float |
| MONTO_DEVENGADO | devengado | float |
| MONTO_GIRADO | girado | float |

