"""
data_pipeline.py — Extracción y agrupación de datos MEF 2025.
 
Responsabilidad ÚNICA: leer el CSV del portal MEF, aplicar filtros,
agrupar correctamente según nivel de gobierno, y guardar Parquets limpios.
NO calcula métricas — eso lo hace analytical_engine.py.
 
Filtros aplicados:
    NIVEL_GOBIERNO IN ('R', 'M')  → Regionales y Locales
    TIPO_ACT_PROY = '2'           → Solo proyectos
    GENERICA = '6'                → Solo adquisición activos no financieros
 
Agrupación:
    Regionales (R): PLIEGO + FUNCION
    Locales    (M): DEPARTAMENTO + PROVINCIA + DISTRITO + FUNCION
 
Salida:
    data/processed/regionales_{period}.parquet
    data/processed/locales_{period}.parquet
 
Uso:
    python -m src.data_pipeline --period 2025
    python -m src.data_pipeline --period 2025 --url "C:/ruta/archivo.csv"
"""
 
import argparse
import json
from pathlib import Path
 
import duckdb
import polars as pl
 
from src.utils import (
    DATA_SNAP, snapshot_path, parquet_regionales, parquet_locales,
    setup_logger, CSV_2025_URL, parse_period
)
 
log = setup_logger("data_pipeline")
 
# ── Filtros según la tarea ────────────────────────────────────────────────────
NIVELES_OBJETIVO = ["R", "M"]  # R=Regional, M=Municipal/Local
TIPO_PROYECTO    = "2"          # Solo proyectos, no actividades
GENERICA_ACTIVOS = "6"          # Adquisición de Activos No Financieros
 
 
def tomar_snapshot(resource_url: str, period: str) -> dict:
    """
    Lee solo 10 filas del CSV para registrar el esquema.
    Principio anti-context-flooding: nunca se carga el CSV completo en memoria.
    """
    log.info(f"Tomando snapshot (10 filas) desde: {resource_url}")
    con = duckdb.connect()
    result = con.execute(f"""
        SELECT * 
        FROM read_csv_auto('{resource_url}', header=true, all_varchar=true)
        LIMIT 10
    """).fetchdf()
    con.close()
 
    snap = {
        "columns": list(result.columns),
        "n_columns": len(result.columns),
        "sample": result.head(3).to_dict(orient="records"),
        "source": resource_url,
    }
    snapshot_path(period).write_text(
        json.dumps(snap, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    log.info(f"Snapshot guardado: {len(result.columns)} columnas detectadas")
    return snap
 
 
def extraer_y_agrupar(resource_url: str, period: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Ejecuta la query DuckDB con todos los filtros y devuelve
    dos DataFrames: uno para regionales y otro para locales.
    """
    period_info = parse_period(period)
    year    = period_info.get("year")
    month   = period_info.get("month")
    quarter = period_info.get("quarter")
 
    # ── WHERE base ────────────────────────────────────────────────────────────
    niveles_sql = ", ".join([f"'{n}'" for n in NIVELES_OBJETIVO])
    where_clauses = [
        f'"NIVEL_GOBIERNO" IN ({niveles_sql})',
        f'"TIPO_ACT_PROY" = \'{TIPO_PROYECTO}\'',
        f'"GENERICA" = \'{GENERICA_ACTIVOS}\'',
    ]
    if year:
        where_clauses.append(f'CAST("ANO_EJE" AS INTEGER) = {year}')
    if month:
        where_clauses.append(f'CAST("MES_EJE" AS INTEGER) = {month}')
    if quarter:
        mes_inicio = (quarter - 1) * 3 + 1
        mes_fin    = quarter * 3
        where_clauses.append(
            f'CAST("MES_EJE" AS INTEGER) BETWEEN {mes_inicio} AND {mes_fin}'
        )
    where_sql = " AND ".join(where_clauses)
 
    # ── Query para REGIONALES (R) ─────────────────────────────────────────────
    # Agrupación: PLIEGO + FUNCION
    # El pliego identifica al gobierno regional (ej: pliego 440 = GR Amazonas)
    query_regionales = f"""
        SELECT
            "PLIEGO"        AS pliego_cod,
            "PLIEGO_NOMBRE" AS pliego,
            "FUNCION_NOMBRE" AS funcion,
            SUM(TRY_CAST(REPLACE("MONTO_PIM",      ',', '') AS DOUBLE)) AS pim,
            SUM(TRY_CAST(REPLACE("MONTO_DEVENGADO", ',', '') AS DOUBLE)) AS devengado
        FROM read_csv_auto('{resource_url}', header=true, all_varchar=true)
        WHERE {where_sql} AND "NIVEL_GOBIERNO" = 'R'
        GROUP BY "PLIEGO", "PLIEGO_NOMBRE", "FUNCION_NOMBRE"
    """
 
    # ── Query para LOCALES (M) ────────────────────────────────────────────────
    # Agrupación: DEPARTAMENTO + PROVINCIA + DISTRITO + FUNCION
    # Permite ver el PIM a nivel distrital por función
    query_locales = f"""
        SELECT
            "DEPARTAMENTO_EJECUTORA"        AS departamento_cod,
            "DEPARTAMENTO_EJECUTORA_NOMBRE" AS departamento,
            "PROVINCIA_EJECUTORA"           AS provincia_cod,
            "PROVINCIA_EJECUTORA_NOMBRE"    AS provincia,
            "DISTRITO_EJECUTORA"            AS distrito_cod,
            "DISTRITO_EJECUTORA_NOMBRE"     AS distrito,
            "FUNCION_NOMBRE"                AS funcion,
            SUM(TRY_CAST(REPLACE("MONTO_PIM",       ',', '') AS DOUBLE)) AS pim,
            SUM(TRY_CAST(REPLACE("MONTO_DEVENGADO",  ',', '') AS DOUBLE)) AS devengado
        FROM read_csv_auto('{resource_url}', header=true, all_varchar=true)
        WHERE {where_sql} AND "NIVEL_GOBIERNO" = 'M'
        GROUP BY
            "DEPARTAMENTO_EJECUTORA", "DEPARTAMENTO_EJECUTORA_NOMBRE",
            "PROVINCIA_EJECUTORA", "PROVINCIA_EJECUTORA_NOMBRE",
            "DISTRITO_EJECUTORA", "DISTRITO_EJECUTORA_NOMBRE",
            "FUNCION_NOMBRE"
    """
 
    con = duckdb.connect()
 
    log.info("Extrayendo datos de Gobiernos Regionales...")
    log.info(f"Filtros: {where_sql} AND NIVEL='R'")
    df_reg = pl.from_pandas(con.execute(query_regionales).fetchdf())
    log.info(f"Regionales: {len(df_reg):,} registros (pliego x función)")
 
    log.info("Extrayendo datos de Gobiernos Locales...")
    log.info(f"Filtros: {where_sql} AND NIVEL='M'")
    df_loc = pl.from_pandas(con.execute(query_locales).fetchdf())
    log.info(f"Locales: {len(df_loc):,} registros (distrito x función)")
 
    con.close()
    return df_reg, df_loc
 
 
def limpiar_numericos(df: pl.DataFrame) -> pl.DataFrame:
    """Asegura que pim y devengado sean Float64 sin nulos."""
    for col in ("pim", "devengado"):
        if col in df.columns:
            df = df.with_columns(
                pl.col(col).cast(pl.Float64, strict=False).fill_null(0.0)
            )
    return df
 
 
def procesar_dataset(resource_url: str, period: str, min_pim: float) -> dict:
    """
    Pipeline completo:
        1. Snapshot
        2. Extracción y agrupación con DuckDB
        3. Limpieza numérica con Polars
        4. Filtro PIM mínimo
        5. Guardar Parquets
    """
    log.info("=" * 60)
    log.info(f"PIPELINE MEF 2025 | periodo={period} | min_pim=S/.{min_pim:,.0f}")
    log.info(f"Filtros: Regionales+Locales | Solo Proyectos | Activos NF")
    log.info("=" * 60)
 
    # Paso 1: Snapshot
    tomar_snapshot(resource_url, period)
 
    # Paso 2: Extracción y agrupación
    df_reg, df_loc = extraer_y_agrupar(resource_url, period)
 
    # Paso 3: Limpieza numérica
    df_reg = limpiar_numericos(df_reg)
    df_loc = limpiar_numericos(df_loc)
 
    # Paso 4: Filtro PIM mínimo
    if min_pim > 0:
        n_antes = len(df_reg)
        df_reg = df_reg.filter(pl.col("pim") >= min_pim)
        log.info(f"Regionales filtrados (PIM >= S/.{min_pim:,.0f}): {n_antes} → {len(df_reg)}")
 
        n_antes = len(df_loc)
        df_loc = df_loc.filter(pl.col("pim") >= min_pim)
        log.info(f"Locales filtrados (PIM >= S/.{min_pim:,.0f}): {n_antes} → {len(df_loc)}")
 
    # Paso 5: Guardar Parquets
    out_reg = parquet_regionales(period)
    out_loc = parquet_locales(period)
 
    df_reg.write_parquet(out_reg, compression="zstd")
    df_loc.write_parquet(out_loc, compression="zstd")
 
    log.info(f"Regionales → {out_reg} ({out_reg.stat().st_size/1024:.1f} KB)")
    log.info(f"Locales    → {out_loc} ({out_loc.stat().st_size/1024:.1f} KB)")
 
    return {
        "regionales": str(out_reg),
        "locales":    str(out_loc),
        "n_regionales": len(df_reg),
        "n_locales":    len(df_loc),
    }
 
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline MEF 2025 — Proyectos de inversión R y M"
    )
    parser.add_argument("--period",  default="2025",
                        help="Periodo: '2025' anual, '2025-9' mensual")
    parser.add_argument("--url",     default=CSV_2025_URL)
    parser.add_argument("--min-pim", default=10_000_000, type=float,
                        help="PIM mínimo por registro agrupado (default: 10M)")
    args = parser.parse_args()
 
    result = procesar_dataset(args.url, args.period, args.min_pim)
    print("\n=== Archivos generados ===")
    for k, v in result.items():
        print(f"  {k}: {v}")