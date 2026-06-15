"""
analytical_engine.py — Cálculo de métricas e indicadores MEF 2025.
 
Responsabilidad: leer los Parquets generados por data_pipeline.py
y calcular todos los indicadores de ejecución presupuestal.
 
Métricas principales:
    tasa_ejecucion_pct = (devengado / pim) × 100
    capital_congelado  = pim - devengado
 
Indicadores calculados:
    - KPIs nacionales (totales)
    - Ranking de gobiernos regionales por tasa de ejecución
    - Ranking de gobiernos locales por tasa de ejecución a nivel distrital
    - Hall of Shame: entidades con PIM > 10M y ejecución < 40%
    - Distribución por función presupuestal
 
Uso:
    python -m src.analytical_engine --period 2025
"""
 
import json
import argparse
from pathlib import Path
 
import polars as pl
 
from src.utils import DATA_PROC, parquet_regionales, parquet_locales, setup_logger
 
log = setup_logger("analytical_engine")
 
# Umbral de ejecución crítica para Hall of Shame
UMBRAL_EJECUCION = 40.0   # < 40% de avance
MIN_PIM_SHAME    = 10_000_000  # PIM > 10M soles
 
 
def cargar_datos(period: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Carga los Parquets de regionales y locales."""
    path_reg = parquet_regionales(period)
    path_loc = parquet_locales(period)
 
    if not path_reg.exists():
        raise FileNotFoundError(
            f"No existe {path_reg}\n"
            f"Ejecuta primero: python -m src.data_pipeline --period {period}"
        )
    if not path_loc.exists():
        raise FileNotFoundError(
            f"No existe {path_loc}\n"
            f"Ejecuta primero: python -m src.data_pipeline --period {period}"
        )
 
    df_reg = pl.read_parquet(path_reg)
    df_loc = pl.read_parquet(path_loc)
 
    log.info(f"Regionales cargados: {df_reg.shape} (pliego x función)")
    log.info(f"Locales cargados: {df_loc.shape} (distrito x función)")
    return df_reg, df_loc
 
 
def calcular_metricas(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calcula tasa de ejecución y capital congelado.
    Aplica para cualquier DataFrame que tenga columnas pim y devengado.
    """
    return df.with_columns([
        (pl.col("devengado") / pl.col("pim") * 100)
            .fill_nan(0.0)
            .fill_null(0.0)
            .alias("tasa_ejecucion_pct"),
        (pl.col("pim") - pl.col("devengado"))
            .alias("capital_congelado"),
    ])
 
 
def kpis_nacionales(df_reg: pl.DataFrame, df_loc: pl.DataFrame) -> dict:
    """KPIs globales combinando regionales y locales."""
    pim_reg = df_reg["pim"].sum()
    dev_reg = df_reg["devengado"].sum()
    pim_loc = df_loc["pim"].sum()
    dev_loc = df_loc["devengado"].sum()
 
    pim_total = pim_reg + pim_loc
    dev_total = dev_reg + dev_loc
    tasa      = (dev_total / pim_total * 100) if pim_total > 0 else 0.0
    congelado = pim_total - dev_total
 
    result = {
        # Totales nacionales
        "pim_total":              round(pim_total, 2),
        "devengado_total":        round(dev_total, 2),
        "tasa_ejecucion_pct":     round(tasa, 2),
        "capital_congelado":      round(congelado, 2),
        # Desagregado por nivel
        "pim_regionales":         round(pim_reg, 2),
        "devengado_regionales":   round(dev_reg, 2),
        "tasa_regionales":        round((dev_reg/pim_reg*100) if pim_reg > 0 else 0, 2),
        "pim_locales":            round(pim_loc, 2),
        "devengado_locales":      round(dev_loc, 2),
        "tasa_locales":           round((dev_loc/pim_loc*100) if pim_loc > 0 else 0, 2),
        # Conteos
        "n_gobiernos_regionales": df_reg["pliego"].n_unique() if "pliego" in df_reg.columns else 0,
        "n_gobiernos_locales":    df_loc["distrito"].n_unique() if "distrito" in df_loc.columns else 0,
    }
    log.info(
        f"KPIs: PIM=S/.{pim_total/1e9:.2f}B | "
        f"Devengado=S/.{dev_total/1e9:.2f}B | "
        f"Tasa={tasa:.1f}% | "
        f"Congelado=S/.{congelado/1e9:.2f}B"
    )
    return result
 
 
def ranking_regionales(df_reg: pl.DataFrame) -> pl.DataFrame:
    """
    Ranking de gobiernos regionales por tasa de ejecución.
    Agrupado por pliego (gobierno regional) sumando todas las funciones.
    """
    return (
        df_reg.group_by(["pliego_cod", "pliego"])
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("funcion").n_unique().alias("n_funciones"),
        ])
        .with_columns([
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("tasa_ejecucion_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("capital_congelado"),
        ])
        .sort("tasa_ejecucion_pct", descending=False)
    )
 
 
def ranking_regionales_por_funcion(df_reg: pl.DataFrame) -> pl.DataFrame:
    """
    Ranking por función para identificar qué sectores tienen
    más dificultad de ejecución en gobiernos regionales.
    """
    return (
        df_reg.group_by("funcion")
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("pliego").n_unique().alias("n_regionales"),
        ])
        .with_columns([
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("tasa_ejecucion_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("capital_congelado"),
        ])
        .sort("tasa_ejecucion_pct", descending=False)
    )
 
 
def ranking_locales_por_departamento(df_loc: pl.DataFrame) -> pl.DataFrame:
    """
    Ranking de gobiernos locales agrupado por departamento.
    Para el mapa territorial del Tab 2.
    """
    return (
        df_loc.group_by(["departamento_cod", "departamento"])
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("distrito").n_unique().alias("n_distritos"),
        ])
        .with_columns([
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("tasa_ejecucion_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("capital_congelado"),
        ])
        .sort("tasa_ejecucion_pct", descending=False)
    )
 
 
def ranking_locales_por_funcion(df_loc: pl.DataFrame) -> pl.DataFrame:
    """
    Ranking por función para gobiernos locales.
    Identifica qué sectores tienen más capital congelado a nivel local.
    """
    return (
        df_loc.group_by("funcion")
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
            pl.col("distrito").n_unique().alias("n_distritos"),
        ])
        .with_columns([
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("tasa_ejecucion_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("capital_congelado"),
        ])
        .sort("tasa_ejecucion_pct", descending=False)
    )
 
 
def hall_of_shame(df_reg: pl.DataFrame, df_loc: pl.DataFrame) -> pl.DataFrame:
    """
    Entidades con PIM > 10M y tasa de ejecución < 40%.
    Combina regionales y locales en una sola tabla.
    """
    # Regionales: agrupa por pliego
    reg_agg = (
        df_reg.group_by(["pliego_cod", "pliego"])
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
        ])
        .with_columns([
            pl.lit("REGIONAL").alias("nivel"),
            pl.col("pliego").alias("entidad"),
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("tasa_ejecucion_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("capital_congelado"),
        ])
        .select(["nivel", "entidad", "pim_total", "devengado_total",
                 "tasa_ejecucion_pct", "capital_congelado"])
    )
 
    # Locales: agrupa por distrito
    loc_agg = (
        df_loc.group_by(["departamento", "provincia", "distrito"])
        .agg([
            pl.col("pim").sum().alias("pim_total"),
            pl.col("devengado").sum().alias("devengado_total"),
        ])
        .with_columns([
            pl.lit("LOCAL").alias("nivel"),
            (pl.col("distrito") + " (" + pl.col("provincia") + ")")
                .alias("entidad"),
            (pl.col("devengado_total") / pl.col("pim_total") * 100)
                .fill_nan(0.0).alias("tasa_ejecucion_pct"),
            (pl.col("pim_total") - pl.col("devengado_total"))
                .alias("capital_congelado"),
        ])
        .select(["nivel", "entidad", "pim_total", "devengado_total",
                 "tasa_ejecucion_pct", "capital_congelado"])
    )
 
    shame = (
        pl.concat([reg_agg, loc_agg])
        .filter(
            (pl.col("pim_total") >= MIN_PIM_SHAME) &
            (pl.col("tasa_ejecucion_pct") < UMBRAL_EJECUCION)
        )
        .sort("tasa_ejecucion_pct", descending=False)
    )
 
    log.info(
        f"Hall of Shame: {len(shame)} entidades con "
        f"PIM > S/.{MIN_PIM_SHAME/1e6:.0f}M y ejecución < {UMBRAL_EJECUCION}%"
    )
    return shame
 
 
def generar_reporte_completo(period: str) -> dict:
    """Genera todos los datasets analíticos y los guarda en data/processed/."""
    df_reg, df_loc = cargar_datos(period)
    safe = period.replace("-", "_")
    outputs = {}
 
    # KPIs
    kpis = kpis_nacionales(df_reg, df_loc)
    kpis_path = DATA_PROC / f"kpis_{safe}.json"
    kpis_path.write_text(
        json.dumps(kpis, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    outputs["kpis"] = str(kpis_path)
 
    # Ranking regionales
    rank_reg = ranking_regionales(df_reg)
    path = DATA_PROC / f"ranking_regionales_{safe}.parquet"
    rank_reg.write_parquet(path, compression="zstd")
    outputs["ranking_regionales"] = str(path)
    log.info(f"Ranking regionales: {len(rank_reg)} gobiernos regionales")
 
    # Ranking regionales por función
    rank_reg_func = ranking_regionales_por_funcion(df_reg)
    path = DATA_PROC / f"ranking_reg_funcion_{safe}.parquet"
    rank_reg_func.write_parquet(path, compression="zstd")
    outputs["ranking_reg_funcion"] = str(path)
 
    # Ranking locales por departamento
    rank_loc_dept = ranking_locales_por_departamento(df_loc)
    path = DATA_PROC / f"ranking_locales_dept_{safe}.parquet"
    rank_loc_dept.write_parquet(path, compression="zstd")
    outputs["ranking_locales_dept"] = str(path)
    log.info(f"Ranking locales por dpto: {len(rank_loc_dept)} departamentos")
 
    # Ranking locales por función
    rank_loc_func = ranking_locales_por_funcion(df_loc)
    path = DATA_PROC / f"ranking_loc_funcion_{safe}.parquet"
    rank_loc_func.write_parquet(path, compression="zstd")
    outputs["ranking_loc_funcion"] = str(path)
 
    # Hall of Shame
    shame = hall_of_shame(df_reg, df_loc)
    path = DATA_PROC / f"hall_of_shame_{safe}.parquet"
    shame.write_parquet(path, compression="zstd")
    outputs["hall_of_shame"] = str(path)
 
    log.info(f"Reporte completo generado: {list(outputs.keys())}")
    return outputs
 
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analytical Engine MEF 2025")
    parser.add_argument("--period", default="2025")
    args = parser.parse_args()
    result = generar_reporte_completo(args.period)
    print("\n=== Archivos generados ===")
    for k, v in result.items():
        print(f"  {k}: {v}")