"""
utils.py — Helpers, logging estructurado y constantes del sistema.

Responsabilidades:
- Configurar loguru para logs con rotación diaria en logs/
- Constantes del portal (base URLs, dataset IDs)
- Funciones de utilidad compartidas entre módulos
"""

import os
from pathlib import Path
from loguru import logger

# ── Rutas base ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_RAW     = ROOT / "data" / "raw_pdfs"
DATA_SNAP    = ROOT / "data" / "snapshots"
DATA_PROC    = ROOT / "data" / "processed"
LOGS_DIR     = ROOT / "logs"

for _dir in (DATA_RAW, DATA_SNAP, DATA_PROC, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Portal CKAN ───────────────────────────────────────────────────────────────
PORTAL_BASE   = "https://datosabiertos.gob.pe"
CKAN_API      = f"{PORTAL_BASE}/api/3/action"
DATASTORE_API = f"{CKAN_API}/datastore_search_sql"

# Palabras clave para búsqueda del dataset SIAF 2025
SIAF_KEYWORDS = ["ejecucion presupuestal", "SIAF", "MEF", "2025", "devengado"]

# URL del PDF histórico 1964
PDF_1964_URL = (
    "https://fuenteshistoricasdelperu.com/2021/08/12/"
    "ministerio-de-hacienda-y-comercio-presupuesto-balance-y-cuenta-general-de-la-republica/"
)
PDF_1964_LOCAL = DATA_RAW / "hacienda_1964.pdf"

# ── Logging ───────────────────────────────────────────────────────────────────
def setup_logger(name: str, period: str = "general"):
    """Configura loguru con rotación diaria y formato estructurado."""
    log_path = LOGS_DIR / f"{name}_{period}.log"
    logger.remove()
    logger.add(
        log_path,
        rotation="1 day",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
        level="DEBUG",
    )
    logger.add(
        lambda msg: print(msg, end=""),
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
    )
    return logger


# ── Helpers de periodo ────────────────────────────────────────────────────────
def parse_period(period: str) -> dict:
    """
    Convierte strings de periodo a año/mes para queries.

    Ejemplos:
        '2025-12' -> {'year': 2025, 'month': 12, 'quarter': None}
        '2025-Q4' -> {'year': 2025, 'month': None, 'quarter': 4}
        '2025'    -> {'year': 2025, 'month': None, 'quarter': None}
    """
    period = period.strip().upper()
    result = {"year": None, "month": None, "quarter": None, "raw": period}

    if "-Q" in period:
        year, q = period.split("-Q")
        result["year"]    = int(year)
        result["quarter"] = int(q)
    elif "-" in period:
        year, month = period.split("-")
        result["year"]  = int(year)
        result["month"] = int(month)
    else:
        result["year"] = int(period)

    return result


def parquet_path(period: str) -> Path:
    """Devuelve la ruta del archivo Parquet procesado para un periodo."""
    safe = period.replace("-", "_").replace(" ", "_")
    return DATA_PROC / f"budget_2025_{safe}.parquet"


def snapshot_path(period: str) -> Path:
    """Devuelve la ruta del snapshot JSON para un periodo."""
    safe = period.replace("-", "_")
    return DATA_SNAP / f"schema_{safe}.json"