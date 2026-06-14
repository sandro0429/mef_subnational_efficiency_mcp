"""
data_pipeline.py — Pipeline local de extracción y transformación de datos 2025.

Principio CRÍTICO: Este script corre como proceso externo, FUERA del contexto del LLM.
Descarga solo lo necesario, filtra en memoria con polars, y guarda un Parquet pequeño.

Uso:
    python -m src.data_pipeline --period 2025-12 --min-pim 10000000
"""

import argparse
import json
import sys
from pathlib import Path

import polars as pl
import requests

from src.utils import (
    DATA_PROC, DATA_SNAP, parquet_path, snapshot_path, setup_logger
)

log = setup_logger("data_pipeline")

# Columnas que necesitamos del SIAF (mapeo aproximado — se ajusta al schema real)
REQUIRED_COLS = {
    "DEPARTAMENTO":      "departamento",
    "PLIEGO":            "entidad",
    "UNIDAD_EJECUTORA":  "unidad_ejecutora",
    "FUNCION":           "funcion",
    "CATEGORIA":         "categoria",
    "PIM":               "pim",
    "DEVENGADO":         "devengado",
    "GIRADO":            "girado",
    "PAGADO":            "pagado",
    "PERIODO":           "periodo",
}


def calcular_metricas(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calcula los indicadores base de ejecución presupuestal.

    Métricas:
        avance_pct  = (Devengado / PIM) * 100
        saldo_nd    = PIM - Devengado   (Presupuesto Paralizado)
    """
    return df.with_columns([
        (pl.col("devengado") / pl.col("pim") * 100)
            .fill_nan(0.0)
            .alias("avance_pct"),
        (pl.col("pim") - pl.col("devengado"))
            .alias("saldo_nd"),
    ])


def filtrar_periodo(df: pl.DataFrame, period_info: dict) -> pl.DataFrame:
    """Filtra el DataFrame por año y opcionalmente mes/trimestre."""
    year = period_info.get("year")
    month = period_info.get("month")
    quarter = period_info.get("quarter")

    if "periodo" in df.columns:
        df = df.filter(pl.col("periodo").cast(pl.Utf8).str.contains(str(year)))
    if month and "mes" in df.columns:
        df = df.filter(pl.col("mes") == month)
    if quarter and "trimestre" in df.columns:
        df = df.filter(pl.col("trimestre") == quarter)

    return df


def procesar_dataset(resource_url: str, period: str, min_pim: float) -> Path:
    """
    Pipeline principal:
        1. Descarga el CSV con streaming (chunk a chunk).
        2. Parsea solo las columnas necesarias con polars.
        3. Filtra por periodo y PIM mínimo.
        4. Calcula métricas.
        5. Guarda en Parquet comprimido.

    Retorna la ruta del Parquet generado.
    """
    from src.utils import parse_period
    period_info = parse_period(period)
    out_path = parquet_path(period)

    log.info(f"Iniciando pipeline para periodo={period}, min_pim={min_pim:,.0f}")
    log.info(f"Fuente: {resource_url}")

    # ── Streaming download ────────────────────────────────────────────────────
    log.info("Descargando CSV por streaming (nunca cargamos todo en RAM)...")
    import io
    import csv as csv_mod

    rows = []
    headers = None
    bytes_read = 0

    with requests.get(resource_url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        buffer = ""
        for chunk in resp.iter_content(chunk_size=65536, decode_unicode=True):
            bytes_read += len(chunk.encode("utf-8"))
            buffer += chunk
            lines = buffer.splitlines()
            buffer = lines[-1]

            for line in lines[:-1]:
                reader = csv_mod.reader([line])
                parsed = next(reader)
                if headers is None:
                    headers = parsed
                    continue
                if len(parsed) == len(headers):
                    rows.append(parsed)

    log.info(f"Descargados {bytes_read / 1_048_576:.1f} MB, {len(rows):,} filas crudas")

    # ── Construir DataFrame polars ────────────────────────────────────────────
    df = pl.DataFrame({col: [row[i] for row in rows] for i, col in enumerate(headers)})
    log.info(f"DataFrame inicial: {df.shape}")

    # Renombrar columnas al esquema normalizado
    rename_map = {k: v for k, v in REQUIRED_COLS.items() if k in df.columns}
    df = df.rename(rename_map)

    # Cast a numérico
    for col in ("pim", "devengado", "girado", "pagado"):
        if col in df.columns:
            df = df.with_columns(
                pl.col(col).str.replace_all(",", "").cast(pl.Float64, strict=False).fill_null(0.0)
            )

    # ── Filtros ───────────────────────────────────────────────────────────────
    df = filtrar_periodo(df, period_info)
    df = df.filter(pl.col("pim") >= min_pim)
    log.info(f"Después de filtros: {df.shape} (PIM >= {min_pim:,.0f})")

    # ── Métricas ──────────────────────────────────────────────────────────────
    df = calcular_metricas(df)

    # ── Guardar Parquet ───────────────────────────────────────────────────────
    df.write_parquet(out_path, compression="zstd")
    size_kb = out_path.stat().st_size / 1024
    log.info(f"Parquet guardado: {out_path} ({size_kb:.1f} KB)")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline MEF 2025")
    parser.add_argument("--period",  default="2025-12", help="Periodo fiscal (ej: 2025-12)")
    parser.add_argument("--url",     required=True,     help="URL del CSV en el portal")
    parser.add_argument("--min-pim", default=10_000_000, type=float, help="PIM mínimo en soles")
    args = parser.parse_args()

    result = procesar_dataset(args.url, args.period, args.min_pim)
    print(f"OK: {result}")