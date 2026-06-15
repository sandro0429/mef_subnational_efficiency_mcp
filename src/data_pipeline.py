"""
data_pipeline.py — Pipeline MEF 2025 optimizado con DuckDB.

Uso:
    python -m src.data_pipeline --period 2025-9
    python -m src.data_pipeline --period 2025-9 --url "C:/ruta/al/archivo.csv"
"""

import argparse
import json
from pathlib import Path

import duckdb
import polars as pl

from src.utils import (
    DATA_PROC, DATA_SNAP, parquet_path, snapshot_path,
    setup_logger, CSV_2025_URL
)

log = setup_logger("data_pipeline")

# Columnas reales del CSV MEF 2025 → nombres normalizados
REQUIRED_COLS = {
    "ANO_EJE":                        "anio",
    "MES_EJE":                        "mes",
    "NIVEL_GOBIERNO_NOMBRE":          "nivel_gobierno",
    "SECTOR_NOMBRE":                  "sector",
    "PLIEGO_NOMBRE":                  "entidad",
    "EJECUTORA_NOMBRE":               "unidad_ejecutora",
    "DEPARTAMENTO_EJECUTORA_NOMBRE":  "departamento",
    "PROVINCIA_EJECUTORA_NOMBRE":     "provincia",
    "FUNCION_NOMBRE":                 "funcion",
    "DIVISION_FUNCIONAL_NOMBRE":      "division_funcional",
    "FUENTE_FINANCIAMIENTO_NOMBRE":   "fuente_financiamiento",
    "CATEGORIA_GASTO_NOMBRE":         "categoria_gasto",
    "GENERICA_NOMBRE":                "generica",
    "MONTO_PIA":                      "pia",
    "MONTO_PIM":                      "pim",
    "MONTO_DEVENGADO":                "devengado",
    "MONTO_GIRADO":                   "girado",
    "MONTO_COMPROMETIDO_ANUAL":       "comprometido_anual",
}

# Columnas monetarias que necesitan cast explícito
MONEY_COLS = ["MONTO_PIA", "MONTO_PIM", "MONTO_DEVENGADO", "MONTO_GIRADO", "MONTO_COMPROMETIDO_ANUAL"]


def tomar_snapshot(resource_url: str, period: str) -> dict:
    """Lee solo 10 filas para registrar el schema."""
    log.info(f"Tomando snapshot desde: {resource_url}")
    con = duckdb.connect()

    result = con.execute(f"""
        SELECT * FROM read_csv_auto('{resource_url}', header=true, all_varchar=true)
        LIMIT 10
    """).fetchdf()

    snap = {
        "columns": list(result.columns),
        "sample":  result.head(3).to_dict(orient="records"),
        "source":  resource_url
    }
    snapshot_path(period).write_text(
        json.dumps(snap, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    log.info(f"Snapshot: {len(result.columns)} columnas, 10 filas")
    con.close()
    return snap


def procesar_dataset(resource_url: str, period: str, min_pim: float) -> Path:
    from src.utils import parse_period
    period_info = parse_period(period)
    year    = period_info.get("year")
    month   = period_info.get("month")
    quarter = period_info.get("quarter")
    out_path = parquet_path(period)

    log.info(f"Iniciando pipeline | periodo={period} | min_pim=S/.{min_pim:,.0f}")

    # Paso 1: snapshot
    tomar_snapshot(resource_url, period)

    # Paso 2: SELECT con cast explícito en columnas monetarias
    # all_varchar=true para leer todo como texto primero
    # luego casteamos manualmente para manejar comas y formatos mixtos
    select_parts = []
    for src, dst in REQUIRED_COLS.items():
        if src in MONEY_COLS:
            # Reemplazar comas y castear a DOUBLE
            select_parts.append(
                f"TRY_CAST(REPLACE(REPLACE(\"{src}\", ',', ''), ' ', '') AS DOUBLE) AS {dst}"
            )
        else:
            select_parts.append(f'"{src}" AS {dst}')

    select_cols = ", ".join(select_parts)

    # Paso 3: WHERE dinámico — solo por año y mes, sin filtro de PIM aquí
    where_clauses = []
    if year:
        where_clauses.append(f'CAST("{chr(65)}NO_EJE" AS INTEGER) = {year}')
    if month:
        where_clauses.append(f'CAST("MES_EJE" AS INTEGER) = {month}')
    if quarter:
        mes_inicio = (quarter - 1) * 3 + 1
        mes_fin    = quarter * 3
        where_clauses.append(f'CAST("MES_EJE" AS INTEGER) BETWEEN {mes_inicio} AND {mes_fin}')

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    query = f"""
        SELECT {select_cols}
        FROM read_csv_auto('{resource_url}', header=true, all_varchar=true)
        WHERE {where_sql}
    """

    log.info("Ejecutando query DuckDB...")
    log.info(f"Filtros activos: {where_sql}")

    con = duckdb.connect()
    df_duck = con.execute(query).fetchdf()
    con.close()

    log.info(f"Filas obtenidas: {len(df_duck):,}")

    if len(df_duck) == 0:
        raise ValueError(f"Sin datos para periodo={period}. Verifica año/mes en el CSV.")

    # Paso 4: polars + limpiar nulos en columnas monetarias
    df = pl.from_pandas(df_duck)
    for col in ("pia", "pim", "devengado", "girado", "comprometido_anual"):
        if col in df.columns:
            df = df.with_columns(
                pl.col(col).cast(pl.Float64, strict=False).fill_null(0.0)
            )

    # Paso 5: filtrar por PIM mínimo DESPUÉS del cast
    if min_pim > 0:
        antes = len(df)
        df = df.filter(pl.col("pim") >= min_pim)
        log.info(f"Filtro PIM >= S/.{min_pim:,.0f}: {antes:,} → {len(df):,} filas")

    # Paso 6: métricas
    df = df.with_columns([
        (pl.col("devengado") / pl.col("pim") * 100)
            .fill_nan(0.0).fill_null(0.0).alias("avance_pct"),
        (pl.col("pim") - pl.col("devengado")).alias("saldo_nd"),
    ])

    # Paso 7: guardar Parquet
    df.write_parquet(out_path, compression="zstd")
    size_kb = out_path.stat().st_size / 1024
    log.info(f"Parquet guardado: {out_path} ({size_kb:.1f} KB, {len(df):,} filas)")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline MEF 2025 — DuckDB")
    parser.add_argument("--period",  default="2025-9")
    parser.add_argument("--url",     default=CSV_2025_URL)
    parser.add_argument("--min-pim", default=10_000_000, type=float)
    args = parser.parse_args()
    result = procesar_dataset(args.url, args.period, args.min_pim)
    print(f"\nOK: {result}")
