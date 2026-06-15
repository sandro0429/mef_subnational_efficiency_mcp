"""
mcp_server.py — Servidor MCP local que expone herramientas al Claude Code CLI.
 
Implementa el Model Context Protocol (MCP) para que Claude Code CLI
pueda invocar herramientas de datos del portal MEF.
 
Principio CRÍTICO: Ninguna herramienta carga datasets completos en contexto.
Todas operan con snapshots mínimos o queries filtradas.
 
Herramientas expuestas:
    buscar_datasets             — Busca datasets por keyword en CKAN
    obtener_detalle_dataset     — Obtiene URLs de descarga por dataset ID
    inspeccionar_esquema_csv    — Lee 10 filas de un CSV remoto (snapshot)
    consultar_datastore_filtrado — Query SQL directa al datastore CKAN
    descargar_documento_1964    — Descarga el PDF histórico 1964
    procesar_ocr_paginas_1964   — Dispara el motor OCR sobre páginas seleccionadas
    ejecutar_pipeline_datos     — Corre data_pipeline.py con parámetros dados
    ejecutar_analytical_engine  — Corre analytical_engine.py con parámetros dados
 
Uso:
    python src/mcp_server.py
"""
 
import json
import subprocess
import sys
from pathlib import Path
 
import requests
 
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
 
from src.utils import (
    CKAN_API, CSV_2025_URL, PDF_1964_LOCAL,
    DATA_PROC, setup_logger
)
 
log = setup_logger("mcp_server")
 
# ── Herramientas MCP ──────────────────────────────────────────────────────────
 
def buscar_datasets(query: str, rows: int = 5) -> dict:
    """
    Busca datasets en el portal CKAN por keyword.
    Endpoint: /api/3/action/package_search?q={query}
    """
    url = f"{CKAN_API}/package_search"
    params = {"q": query, "rows": rows}
    log.info(f"[MCP] buscar_datasets: '{query}' (max {rows})")
 
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result", {}).get("results", [])
        return {
            "count": len(results),
            "datasets": [
                {
                    "id":    d.get("id"),
                    "name":  d.get("name"),
                    "title": d.get("title"),
                    "resources": [
                        {
                            "id":     r.get("id"),
                            "format": r.get("format"),
                            "url":    r.get("url"),
                        }
                        for r in d.get("resources", [])
                    ],
                }
                for d in results
            ],
        }
    except Exception as e:
        log.error(f"Error en buscar_datasets: {e}")
        return {"error": str(e)}
 
 
def obtener_detalle_dataset(dataset_id: str) -> dict:
    """Obtiene detalles y URLs de descarga de un dataset por su ID."""
    url = f"{CKAN_API}/package_show"
    params = {"id": dataset_id}
    log.info(f"[MCP] obtener_detalle_dataset: {dataset_id}")
 
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pkg  = data.get("result", {})
        return {
            "id":        pkg.get("id"),
            "title":     pkg.get("title"),
            "resources": [
                {"id": r.get("id"), "format": r.get("format"), "url": r.get("url")}
                for r in pkg.get("resources", [])
            ],
        }
    except Exception as e:
        log.error(f"Error en obtener_detalle_dataset: {e}")
        return {"error": str(e)}
 
 
def inspeccionar_esquema_csv(resource_url: str, n_rows: int = 10) -> dict:
    """
    Lee solo las primeras n_rows filas de un CSV remoto.
    NUNCA descarga el archivo completo.
    Usa streaming HTTP chunk a chunk.
    """
    import csv as csv_mod
    log.info(f"[MCP] inspeccionar_esquema_csv: {resource_url} ({n_rows} filas)")
 
    headers_csv = None
    rows = []
 
    try:
        with requests.get(resource_url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            buffer = ""
            for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
                buffer += chunk
                lines = buffer.splitlines()
                buffer = lines[-1]
                for line in lines[:-1]:
                    parsed = next(csv_mod.reader([line]))
                    if headers_csv is None:
                        headers_csv = parsed
                    else:
                        rows.append(dict(zip(headers_csv, parsed)))
                    if len(rows) >= n_rows:
                        break
                if len(rows) >= n_rows:
                    break
 
        return {
            "columns":   headers_csv,
            "n_columns": len(headers_csv) if headers_csv else 0,
            "sample":    rows,
            "source":    resource_url,
        }
    except Exception as e:
        log.error(f"Error en inspeccionar_esquema_csv: {e}")
        return {"error": str(e)}
 
 
def consultar_datastore_filtrado(
    resource_id: str,
    filters: dict,
    limit: int = 100
) -> dict:
    """
    Query SQL directa al datastore nativo de CKAN.
    Siempre aplica filtros y límites — nunca devuelve el dataset completo.
    """
    sql = f'SELECT * FROM "{resource_id}" WHERE 1=1'
    for col, val in filters.items():
        if isinstance(val, str):
            sql += f" AND \"{col}\" LIKE '%{val}%'"
        else:
            sql += f" AND \"{col}\" = {val}"
    sql += f" LIMIT {limit}"
 
    log.info(f"[MCP] consultar_datastore_filtrado: {sql[:100]}...")
 
    try:
        resp = requests.get(
            f"{CKAN_API}/datastore_search_sql",
            params={"sql": sql},
            timeout=60
        )
        resp.raise_for_status()
        return resp.json().get("result", {})
    except Exception as e:
        log.error(f"Error en consultar_datastore_filtrado: {e}")
        return {"error": str(e)}
 
 
def descargar_documento_1964() -> str:
    """
    Verifica si el PDF 1964 existe localmente.
    Retorna la ruta local del archivo.
    """
    log.info(f"[MCP] descargar_documento_1964: verificando {PDF_1964_LOCAL}")
    if PDF_1964_LOCAL.exists():
        log.info(f"PDF 1964 disponible en: {PDF_1964_LOCAL}")
        return str(PDF_1964_LOCAL)
    else:
        return f"ERROR: PDF no encontrado en {PDF_1964_LOCAL}. Descárgalo manualmente."
 
 
def procesar_ocr_paginas_1964(pages: str = "1-15") -> dict:
    """
    Dispara el motor OCR sobre las páginas indicadas del PDF 1964.
    Llama a ocr_engine.py como proceso externo.
    """
    log.info(f"[MCP] procesar_ocr_paginas_1964: páginas={pages}")
    cmd = [
        sys.executable, "-m", "src.ocr_engine",
        "--pages", pages,
        "--pdf", str(PDF_1964_LOCAL),
    ]
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT),
            capture_output=True, text=True, timeout=600
        )
        output_path = DATA_PROC / "ocr_1964_extracted.parquet"
        return {
            "status":      "ok" if result.returncode == 0 else "error",
            "output_path": str(output_path) if output_path.exists() else None,
            "stdout":      result.stdout[-500:],
            "stderr":      result.stderr[-200:] if result.returncode != 0 else "",
        }
    except Exception as e:
        log.error(f"Error en procesar_ocr_paginas_1964: {e}")
        return {"error": str(e)}
 
 
def ejecutar_pipeline_datos(period: str, min_pim: float = 10_000_000) -> dict:
    """
    Ejecuta data_pipeline.py como proceso externo.
    Principio anti-flooding: el pipeline corre fuera del contexto del LLM.
    """
    log.info(f"[MCP] ejecutar_pipeline_datos: period={period} min_pim={min_pim}")
    cmd = [
        sys.executable, "-m", "src.data_pipeline",
        "--period", period,
        "--min-pim", str(min_pim),
    ]
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT),
            capture_output=True, text=True, timeout=1800
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-200:] if result.returncode != 0 else "",
        }
    except Exception as e:
        return {"error": str(e)}
 
 
def ejecutar_analytical_engine(period: str) -> dict:
    """
    Ejecuta analytical_engine.py como proceso externo.
    Lee los Parquets del pipeline y genera los reportes analíticos.
    """
    log.info(f"[MCP] ejecutar_analytical_engine: period={period}")
    cmd = [
        sys.executable, "-m", "src.analytical_engine",
        "--period", period,
    ]
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT),
            capture_output=True, text=True, timeout=300
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-200:] if result.returncode != 0 else "",
        }
    except Exception as e:
        return {"error": str(e)}
 
 
# ── Registro de herramientas MCP ──────────────────────────────────────────────
MCP_TOOLS = {
    "buscar_datasets":              buscar_datasets,
    "obtener_detalle_dataset":      obtener_detalle_dataset,
    "inspeccionar_esquema_csv":     inspeccionar_esquema_csv,
    "consultar_datastore_filtrado": consultar_datastore_filtrado,
    "descargar_documento_1964":     descargar_documento_1964,
    "procesar_ocr_paginas_1964":    procesar_ocr_paginas_1964,
    "ejecutar_pipeline_datos":      ejecutar_pipeline_datos,
    "ejecutar_analytical_engine":   ejecutar_analytical_engine,
}
 
 
if __name__ == "__main__":
    log.info("=== MCP Server MEF — Herramientas disponibles ===")
    for name in MCP_TOOLS:
        log.info(f"  - {name}")
    log.info("Servidor listo. Invoca las herramientas via Claude Code CLI.")