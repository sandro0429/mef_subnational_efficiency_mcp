"""
analytical_engine.py — Motor de métricas y agrupaciones para el análisis 2025.

Lee el Parquet procesado por data_pipeline.py y produce:
    - Resumen nacional (KPIs globales)
    - Ranking por departamento
    - Hall of Shame: peores ejecutores (PIM > 10M PEN, avance < umbral)
    - Distribución por función presupuestal
    - Capital congelado (Saldo No Devengado) por región

Columnas disponibles (nombres normalizados por data_pipeline.py):
    anio, mes, nivel_gobierno, sector, entidad, unidad_ejecutora,
    departamento, provincia, funcion, division_funcional,
    fuente_financiamiento, categoria_gasto, generica,
    pia, pim, devengado, girado, avance_pct, saldo_nd
"""

import json
from pathlib import Path

import polars as pl

from src.utils import DATA_PROC, parquet_path, setup_logger

log = setup_logger("analytical_engine")

SHAME_THRESHOLD_PCT = 40.0
MIN_PIM_SHAME       = 10_000_000


def cargar_datos(period: str) -> pl.DataFrame:
    """Carga el Parquet procesado para un periodo."""
    path = parquet_path(period)
    if not path.exists():
        raise FileNotFoundError(
            f"Parquet no encontrado: {path}\n"
            f"Ejecuta primero: python -m src.data_pipeline --period {period} --url URL_CSV"
        )
    df = pl.read_parquet(path)
    log.info(f"Cargado: {df.shape} para periodo={period}")
    log.info(f"Columnas: {df.columns}")
    return df


def kpis_nacionales(df: pl.DataFrame) -> dict:
    """KPIs a nivel nacional para el Tab 1 del dashboard."""
    total_pim       = df["pim"].sum()
    total_devengado = df["devengado"].sum()
    total_girado    = df["girado"].sum() if "girado" in df.columns else 0.0
    avance_pct      = (total_devengado / total_pim * 100) if total_pim > 0 else 0.0
    capital_congelado = total_pim - total_devengado

    result = {
        "total_pim":           round(total_pim, 2),
        "total_devengado":     round(total_devengado, 2),
        "total_girado":        round(total_girado, 2),
        "avance_nacional_pct": round(avance_pct, 2),
        "capital_congelado":   round(capital_congelado, 2),
        "n_entidades":         df["entidad"].n_unique() if "entidad" in df.columns else 0,
        "n_departamentos":     df["departamento"].n_unique() if "departamento" in df.columns else 0,
    }
    log.info(f"KPIs nacionales: avance={result['avance_nacional_pct']}% | "
             f"PIM=S/.{result['total_pim']/1e9:.2f}B | "
             f"congelado=S/.{result['capital_congelado']/1e9:.2f}B")
    return result


def ranking_departamentos(df: pl.DataFrame) -> pl.DataFrame:
    if "departamento" not in df.columns:
        log.warning("Columna 'departamento' no encontrada")
        return pl.DataFrame()

    agg_exprs = [
        pl.col("pim").sum().alias("pim_total"),
        pl.col("devengado").sum().alias("devengado_total"),
        pl.col("entidad").n_unique().alias("n_entidades"),
    ]
    # Evita el if dentro de .agg()
    if "girado" in df.columns:
        agg_exprs.append(pl.col("girado").sum().alias("girado_total"))
    else:
        agg_exprs.append(pl.lit(0.0).alias("girado_total"))

    return (
        df.group_by("departamento")
        .agg(agg_exprs)
        .with_columns([
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("avance_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("saldo_nd"),
        ])
        .sort("avance_pct", descending=False)
    )

def hall_of_shame(df: pl.DataFrame,
                  threshold_pct: float = SHAME_THRESHOLD_PCT) -> pl.DataFrame:
    """
    Peores ejecutores: PIM > 10M PEN Y avance < threshold_pct.
    Para Tab 3.
    """
    cols_base = ["entidad", "unidad_ejecutora", "departamento",
                 "funcion", "sector", "pim", "devengado",
                 "avance_pct", "saldo_nd"]
    cols_disponibles = [c for c in cols_base if c in df.columns]

    shame = (
        df.filter(
            (pl.col("pim") >= MIN_PIM_SHAME) &
            (pl.col("avance_pct") < threshold_pct)
        )
        .select(cols_disponibles)
        .sort("avance_pct", descending=False)
    )
    log.info(f"Hall of Shame: {len(shame)} entidades con "
             f"avance < {threshold_pct}% y PIM > S/.{MIN_PIM_SHAME/1e6:.0f}M")
    return shame


def distribucion_funcional(df: pl.DataFrame) -> pl.DataFrame:
    """Distribución del presupuesto por función. Para Tab 2."""
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
                .fill_nan(0.0).alias("avance_pct")
        )
        .sort("pim_total", descending=True)
    )


def distribucion_por_sector(df: pl.DataFrame) -> pl.DataFrame:
    """Distribución por sector para análisis adicional."""
    if "sector" not in df.columns:
        return pl.DataFrame()

    return (
        df.group_by("sector")
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
        ])
        .with_columns(
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("avance_pct")
        )
        .sort("pim_total", descending=True)
    )


def generar_reporte_completo(period: str) -> dict:
    """
    Genera todos los datasets analíticos y los guarda en data/processed/.
    Retorna dict con rutas de archivos generados.
    """
    df   = cargar_datos(period)
    safe = period.replace("-", "_")

    outputs = {}

    # KPIs → JSON
    kpis = kpis_nacionales(df)
    kpis_path = DATA_PROC / f"kpis_{safe}.json"
    kpis_path.write_text(json.dumps(kpis, indent=2, ensure_ascii=False))
    outputs["kpis"] = str(kpis_path)
    log.info(f"KPIs guardados: {kpis_path}")

    # Ranking departamentos
    rank_df = ranking_departamentos(df)
    if len(rank_df) > 0:
        rank_path = DATA_PROC / f"ranking_dept_{safe}.parquet"
        rank_df.write_parquet(rank_path, compression="zstd")
        outputs["ranking_departamentos"] = str(rank_path)
        log.info(f"Ranking guardado: {rank_path} ({len(rank_df)} departamentos)")

    # Hall of Shame
    shame_df = hall_of_shame(df)
    if len(shame_df) > 0:
        shame_path = DATA_PROC / f"hall_of_shame_{safe}.parquet"
        shame_df.write_parquet(shame_path, compression="zstd")
        outputs["hall_of_shame"] = str(shame_path)
        log.info(f"Hall of Shame guardado: {shame_path} ({len(shame_df)} entidades)")

    # Distribución funcional
    func_df = distribucion_funcional(df)
    if len(func_df) > 0:
        func_path = DATA_PROC / f"distribucion_funcional_{safe}.parquet"
        func_df.write_parquet(func_path, compression="zstd")
        outputs["distribucion_funcional"] = str(func_path)

    # Distribución por sector
    sect_df = distribucion_por_sector(df)
    if len(sect_df) > 0:
        sect_path = DATA_PROC / f"distribucion_sector_{safe}.parquet"
        sect_df.write_parquet(sect_path, compression="zstd")
        outputs["distribucion_sector"] = str(sect_path)

    log.info(f"Reporte completo generado para periodo={period}: {list(outputs.keys())}")
    return outputs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analytical Engine MEF 2025")
    parser.add_argument("--period", default="2025-12",
                        help="Periodo fiscal. Ej: '2025-12', '2025-Q4'")
    args = parser.parse_args()

    result = generar_reporte_completo(args.period)
    print("\n=== Archivos generados ===")
    for k, v in result.items():
        print(f"  {k}: {v}")