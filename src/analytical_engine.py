"""
analytical_engine.py — Motor de métricas usando DEVENGADO como métrica principal.

Dado que el CSV 2025-Gasto-Mensual.csv contiene registros de gasto devengado
(MONTO_PIM = 0 en filas individuales), usamos MONTO_DEVENGADO como base
para todos los análisis. Los rankings y agrupaciones reflejan el gasto real ejecutado.

Métricas principales:
    devengado_total  = suma del gasto devengado por entidad/departamento
    girado_total     = suma del gasto girado (pagado efectivamente)
    ratio_giro       = girado / devengado (eficiencia de pago)
"""

import json
from pathlib import Path

import polars as pl

from src.utils import DATA_PROC, parquet_path, setup_logger

log = setup_logger("analytical_engine")

MIN_DEVENGADO_SHAME = 10_000_000  # 10M soles devengados


def cargar_datos(period: str) -> pl.DataFrame:
    path = parquet_path(period)
    if not path.exists():
        raise FileNotFoundError(
            f"Parquet no encontrado: {path}\n"
            f"Ejecuta primero: python -m src.data_pipeline --period {period} --min-pim 0"
        )
    df = pl.read_parquet(path)
    log.info(f"Cargado: {df.shape} para periodo={period}")
    log.info(f"Columnas: {df.columns}")
    return df


def kpis_nacionales(df: pl.DataFrame) -> dict:
    """KPIs nacionales basados en devengado real."""
    total_devengado  = df["devengado"].sum()
    total_girado     = df["girado"].sum() if "girado" in df.columns else 0.0
    ratio_giro       = (total_girado / total_devengado * 100) if total_devengado > 0 else 0.0
    n_entidades      = df["entidad"].n_unique() if "entidad" in df.columns else 0
    n_departamentos  = df["departamento"].n_unique() if "departamento" in df.columns else 0

    result = {
        "total_devengado":    round(total_devengado, 2),
        "total_girado":       round(total_girado, 2),
        "ratio_giro_pct":     round(ratio_giro, 2),
        "n_entidades":        n_entidades,
        "n_departamentos":    n_departamentos,
        "periodo":            str(df["anio"][0]) + "-" + str(df["mes"][0]) if "anio" in df.columns else "2025",
        "nota":               "KPIs basados en MONTO_DEVENGADO. CSV fuente es de gasto mensual devengado."
    }
    log.info(
        f"KPIs nacionales: devengado=S/.{result['total_devengado']/1e9:.2f}B | "
        f"girado=S/.{result['total_girado']/1e9:.2f}B | "
        f"ratio_giro={result['ratio_giro_pct']:.1f}%"
    )
    return result


def ranking_departamentos(df: pl.DataFrame) -> pl.DataFrame:
    """Ranking de departamentos por devengado total."""
    if "departamento" not in df.columns:
        return pl.DataFrame()

    return (
        df.group_by("departamento")
        .agg([
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("girado").sum().alias("girado_total"),
            pl.col("entidad").n_unique().alias("n_entidades"),
            pl.col("funcion").n_unique().alias("n_funciones"),
        ])
        .with_columns([
            (pl.col("girado_total") / pl.col("devengado_total") * 100)
                .fill_nan(0.0).alias("ratio_giro_pct"),
            (pl.col("devengado_total") - pl.col("girado_total"))
                .alias("devengado_no_girado"),
        ])
        .sort("devengado_total", descending=True)
    )


def hall_of_shame(df: pl.DataFrame) -> pl.DataFrame:
    """
    Entidades con alto devengado pero bajo ratio de giro.
    Identifica unidades que gastan pero no pagan efectivamente.
    Umbral: devengado > 10M Y ratio_giro < 80%
    """
    cols_base = ["entidad", "unidad_ejecutora", "departamento",
                 "funcion", "sector", "devengado", "girado"]
    cols_disponibles = [c for c in cols_base if c in df.columns]

    # Agrupar por entidad
    df_entidad = (
        df.group_by(["entidad", "departamento", "funcion", "sector"] if
                    all(c in df.columns for c in ["entidad", "departamento", "funcion", "sector"])
                    else ["entidad"])
        .agg([
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("girado").sum().alias("girado_total"),
        ])
        .with_columns(
            (pl.col("girado_total") / pl.col("devengado_total") * 100)
                .fill_nan(0.0).alias("ratio_giro_pct")
        )
        .filter(
            (pl.col("devengado_total") >= MIN_DEVENGADO_SHAME) &
            (pl.col("ratio_giro_pct") < 80.0)
        )
        .sort("devengado_total", descending=True)
    )

    log.info(
        f"Hall of Shame: {len(df_entidad)} entidades con "
        f"devengado > S/.{MIN_DEVENGADO_SHAME/1e6:.0f}M y ratio_giro < 80%"
    )
    return df_entidad


def distribucion_funcional(df: pl.DataFrame) -> pl.DataFrame:
    """Distribución del gasto devengado por función."""
    if "funcion" not in df.columns:
        return pl.DataFrame()

    return (
        df.group_by("funcion")
        .agg([
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("girado").sum().alias("girado_total"),
            pl.col("entidad").n_unique().alias("n_entidades"),
        ])
        .with_columns(
            (pl.col("girado_total") / pl.col("devengado_total") * 100)
                .fill_nan(0.0).alias("ratio_giro_pct")
        )
        .sort("devengado_total", descending=True)
    )


def distribucion_por_sector(df: pl.DataFrame) -> pl.DataFrame:
    """Distribución del gasto por sector."""
    if "sector" not in df.columns:
        return pl.DataFrame()

    return (
        df.group_by("sector")
        .agg([
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("girado").sum().alias("girado_total"),
        ])
        .with_columns(
            (pl.col("girado_total") / pl.col("devengado_total") * 100)
                .fill_nan(0.0).alias("ratio_giro_pct")
        )
        .sort("devengado_total", descending=True)
    )


def generar_reporte_completo(period: str) -> dict:
    df   = cargar_datos(period)
    safe = period.replace("-", "_")
    outputs = {}

    # KPIs
    kpis = kpis_nacionales(df)
    kpis_path = DATA_PROC / f"kpis_{safe}.json"
    kpis_path.write_text(
        json.dumps(kpis, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
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

    # Distribución sector
    sect_df = distribucion_por_sector(df)
    if len(sect_df) > 0:
        sect_path = DATA_PROC / f"distribucion_sector_{safe}.parquet"
        sect_df.write_parquet(sect_path, compression="zstd")
        outputs["distribucion_sector"] = str(sect_path)

    log.info(f"Reporte completo generado: {list(outputs.keys())}")
    return outputs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="2025-9")
    args = parser.parse_args()
    result = generar_reporte_completo(args.period)
    print("\n=== Archivos generados ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
