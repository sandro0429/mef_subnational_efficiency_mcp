"""
analytical_engine.py — Motor de métricas y agrupaciones para el análisis 2025.

Lee el Parquet procesado por data_pipeline.py y produce:
    - Resumen nacional (KPIs globales)
    - Ranking por departamento
    - Hall of Shame: peores ejecutores (PIM > 10M PEN, avance < umbral)
    - Distribución por función presupuestal
    - Capital congelado (Saldo No Devengado) por región
"""

from pathlib import Path
from typing import Optional

import polars as pl

from src.utils import DATA_PROC, parquet_path, setup_logger

log = setup_logger("analytical_engine")

# Umbral crítico de ejecución para "Hall of Shame"
SHAME_THRESHOLD_PCT = 40.0   # < 40% de avance
MIN_PIM_SHAME       = 10_000_000  # PIM > 10M soles


def cargar_datos(period: str) -> pl.DataFrame:
    """Carga el Parquet procesado para un periodo."""
    path = parquet_path(period)
    if not path.exists():
        raise FileNotFoundError(
            f"Parquet no encontrado para periodo={period}: {path}\n"
            "Ejecuta primero data_pipeline.py para generar el archivo."
        )
    df = pl.read_parquet(path)
    log.info(f"Cargado: {df.shape} filas/cols para periodo={period}")
    return df


def kpis_nacionales(df: pl.DataFrame) -> dict:
    """
    Calcula KPIs a nivel nacional para el Tab 1 del dashboard.

    Retorna:
        total_pim, total_devengado, avance_nacional_pct, capital_congelado
    """
    total_pim        = df["pim"].sum()
    total_devengado  = df["devengado"].sum()
    avance_pct       = (total_devengado / total_pim * 100) if total_pim > 0 else 0.0
    capital_congelado = total_pim - total_devengado

    result = {
        "total_pim":          round(total_pim, 2),
        "total_devengado":    round(total_devengado, 2),
        "avance_nacional_pct": round(avance_pct, 2),
        "capital_congelado":  round(capital_congelado, 2),
        "n_entidades":        df["entidad"].n_unique() if "entidad" in df.columns else 0,
    }
    log.info(f"KPIs nacionales: {result}")
    return result


def ranking_departamentos(df: pl.DataFrame) -> pl.DataFrame:
    """
    Agrupación por departamento con métricas de ejecución.
    Para Tab 2 (mapa territorial).
    """
    if "departamento" not in df.columns:
        log.warning("Columna 'departamento' no encontrada, saltando ranking por departamento")
        return pl.DataFrame()

    return (
        df.group_by("departamento")
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("entidad").n_unique().alias("n_entidades"),
        ])
        .with_columns([
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0)
                .alias("avance_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("saldo_nd"),
        ])
        .sort("avance_pct", descending=False)
    )


def hall_of_shame(df: pl.DataFrame, threshold_pct: float = SHAME_THRESHOLD_PCT) -> pl.DataFrame:
    """
    Peores ejecutores: PIM > 10M PEN Y avance < threshold_pct.
    Para Tab 3.
    """
    shame = (
        df.filter(
            (pl.col("pim") >= MIN_PIM_SHAME) &
            (pl.col("avance_pct") < threshold_pct)
        )
        .select([
            "entidad", "departamento", "funcion", "categoria",
            "pim", "devengado", "avance_pct", "saldo_nd"
        ] if all(c in df.columns for c in ["entidad", "departamento", "funcion", "categoria"]) else df.columns[:8])
        .sort("avance_pct", descending=False)
    )
    log.info(f"Hall of Shame: {len(shame)} entidades con avance < {threshold_pct}% y PIM > 10M")
    return shame


def distribucion_funcional(df: pl.DataFrame) -> pl.DataFrame:
    """Distribución del presupuesto y ejecución por función presupuestal."""
    if "funcion" not in df.columns:
        return pl.DataFrame()

    return (
        df.group_by("funcion")
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("entidad").n_unique().alias("n_entidades"),
        ])
        .with_columns(
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0)
                .alias("avance_pct")
        )
        .sort("pim_total", descending=True)
    )


def generar_reporte_completo(period: str) -> dict:
    """
    Punto de entrada principal: genera todos los datasets analíticos
    y los guarda como Parquets separados para el dashboard.

    Retorna un dict con las rutas de los archivos generados.
    """
    df = cargar_datos(period)
    safe = period.replace("-", "_")

    outputs = {}

    # KPIs nacionales → JSON
    kpis = kpis_nacionales(df)
    kpis_path = DATA_PROC / f"kpis_{safe}.json"
    import json
    kpis_path.write_text(json.dumps(kpis, indent=2))
    outputs["kpis"] = str(kpis_path)

    # Ranking departamentos
    rank_df = ranking_departamentos(df)
    if len(rank_df) > 0:
        rank_path = DATA_PROC / f"ranking_dept_{safe}.parquet"
        rank_df.write_parquet(rank_path, compression="zstd")
        outputs["ranking_departamentos"] = str(rank_path)

    # Hall of Shame
    shame_df = hall_of_shame(df)
    if len(shame_df) > 0:
        shame_path = DATA_PROC / f"hall_of_shame_{safe}.parquet"
        shame_df.write_parquet(shame_path, compression="zstd")
        outputs["hall_of_shame"] = str(shame_path)

    # Distribución funcional
    func_df = distribucion_funcional(df)
    if len(func_df) > 0:
        func_path = DATA_PROC / f"distribucion_funcional_{safe}.parquet"
        func_df.write_parquet(func_path, compression="zstd")
        outputs["distribucion_funcional"] = str(func_path)

    log.info(f"Reporte completo generado para periodo={period}: {list(outputs.keys())}")
    return outputs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="2025-12")
    args = parser.parse_args()
    result = generar_reporte_completo(args.period)
    print(result)