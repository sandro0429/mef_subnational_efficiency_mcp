"""
utils.py — Configuración central, constantes y helpers del sistema.

Contiene:
- Rutas del proyecto
- URLs del portal de datos abiertos
- Configuración de logging
- Helpers de periodo
"""

from pathlib import Path
from loguru import logger

# ── Rutas base ────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
DATA_RAW     = ROOT / "data" / "raw_pdfs"
DATA_SNAP    = ROOT / "data" / "snapshots"
DATA_PROC    = ROOT / "data" / "processed"
LOGS_DIR     = ROOT / "logs"

for _dir in (DATA_RAW, DATA_SNAP, DATA_PROC, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Portal CKAN ───────────────────────────────────────────────────────────────
PORTAL_BASE   = "https://datosabiertos.gob.pe"
CKAN_API      = f"{PORTAL_BASE}/api/3/action"

# URL directa del CSV de Gasto Mensual 2025
CSV_2025_URL  = "https://fs.datosabiertos.mef.gob.pe/datastorefiles/2025-Gasto-Mensual.csv"

# URL del PDF histórico 1964
PDF_1964_URL  = (
    "https://fuenteshistoricasdelperu.com/2021/08/12/"
    "ministerio-de-hacienda-y-comercio-presupuesto-balance-y-cuenta-general-de-la-republica/"
)
PDF_1964_LOCAL = DATA_RAW / "hacienda_1964.pdf"

# ── Logging ───────────────────────────────────────────────────────────────────
def setup_logger(name: str, period: str = "general"):
    log_path = LOGS_DIR / f"{name}_{period}.log"
    logger.remove()
    logger.add(
        log_path,
        rotation="1 day",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
        level="DEBUG",
        encoding="utf-8",
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
    Convierte strings de periodo a año/mes.
    '2025'    → {'year': 2025, 'month': None, 'quarter': None}
    '2025-9'  → {'year': 2025, 'month': 9, 'quarter': None}
    '2025-Q3' → {'year': 2025, 'month': None, 'quarter': 3}
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


# ── Rutas de archivos procesados ──────────────────────────────────────────────
def parquet_regionales(period: str) -> Path:
    safe = period.replace("-", "_")
    return DATA_PROC / f"regionales_{safe}.parquet"

def parquet_locales(period: str) -> Path:
    safe = period.replace("-", "_")
    return DATA_PROC / f"locales_{safe}.parquet"

def snapshot_path(period: str) -> Path:
    safe = period.replace("-", "_")
    return DATA_SNAP / f"schema_{safe}.json"