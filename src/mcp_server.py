"""
mcp_server.py — Servidor MCP local que expone herramientas al Claude Code CLI.

Principio CRÍTICO: Ninguna herramienta debe leer datasets CSV/JSON completos
en memoria. Todas operan con snapshots mínimos o queries filtradas en servidor.

Herramientas expuestas:
    buscar_datasets             — Busca datasets por keyword en CKAN
    obtener_detalle_dataset     — Obtiene URLs de descarga por dataset ID
    descargar_documento_1964    — Descarga el PDF histórico 1964 localmente
    listar_entidades_publicas   — Lista ministerios, regiones y municipios activos
    listar_categorias_tematicas — Mapea categorías del portal
    obtener_ultimas_actualizaciones — Cambios recientes en el portal
    inspeccionar_esquema_csv    — Abre un stream parcial (5-10 filas) de un CSV
    consultar_datastore_filtrado — SQL-like query directa al datastore del portal
    procesar_ocr_paginas_1964   — Dispara ocr_engine.py sobre páginas seleccionadas
    descargar_y_analizar_estadisticas — Agregaciones ligeras en servidor
"""

# TODO (Fase 2): Implementar cada herramienta con mcp.Server
# Placeholder hasta que construyamos el MCP Server completo

import json
import requests
from pathlib import Path
from src.utils import (
    CKAN_API, DATASTORE_API, PDF_1964_URL, PDF_1964_LOCAL,
    DATA_SNAP, setup_logger
)

log = setup_logger("mcp_server")


def buscar_datasets(query: str, rows: int = 5) -> dict:
    """Busca datasets en el portal CKAN por keyword."""
    url = f"{CKAN_API}/package_search"
    params = {"q": query, "rows": rows}
    log.info(f"Buscando datasets: '{query}' (max {rows} resultados)")
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("result", {}).get("results", [])
    return {
        "count": len(results),
        "datasets": [
            {
                "id": d.get("id"),
                "name": d.get("name"),
                "title": d.get("title"),
                "resources": [
                    {"id": r.get("id"), "format": r.get("format"), "url": r.get("url")}
                    for r in d.get("resources", [])
                ],
            }
            for d in results
        ],
    }


def inspeccionar_esquema_csv(resource_url: str, n_rows: int = 10) -> dict:
    """
    Lee solo las primeras n_rows filas de un CSV remoto sin descargar el archivo completo.
    Usa streaming HTTP con chunk_size para nunca saturar memoria.
    """
    log.info(f"Inspeccionando esquema de: {resource_url}")
    rows = []
    headers = []
    with requests.get(resource_url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        import io, csv
        buffer = ""
        for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
            buffer += chunk
            lines = buffer.splitlines()
            buffer = lines[-1]          # guarda línea incompleta
            for line in lines[:-1]:
                if not headers:
                    headers = next(csv.reader([line]))
                else:
                    row = next(csv.reader([line]))
                    rows.append(dict(zip(headers, row)))
                if len(rows) >= n_rows:
                    break
            if len(rows) >= n_rows:
                break

    snap = {"columns": headers, "sample": rows, "source": resource_url}
    return snap


def descargar_documento_1964(dest: Path = PDF_1964_LOCAL) -> str:
    """
    Descarga el PDF histórico 1964 al disco local.
    Retorna la ruta local del archivo.
    """
    if dest.exists():
        log.info(f"PDF 1964 ya existe localmente: {dest}")
        return str(dest)

    log.info(f"Descargando PDF 1964 desde: {PDF_1964_URL}")
    # La URL es la página del portal; aquí se implementará
    # la lógica de scraping para obtener el enlace directo al PDF.
    raise NotImplementedError(
        "Implementar en Fase 4: obtener URL directa del PDF desde la página del portal."
    )


def consultar_datastore_filtrado(resource_id: str, filters: dict, limit: int = 100) -> dict:
    """
    Realiza una query SQL-like al datastore nativo del portal CKAN.
    NUNCA devuelve el dataset completo; siempre aplica filtros y límites.
    """
    sql = f'SELECT * FROM "{resource_id}" WHERE 1=1'
    for col, val in filters.items():
        if isinstance(val, str):
            sql += f" AND \"{col}\" LIKE '%{val}%'"
        else:
            sql += f" AND \"{col}\" = {val}"
    sql += f" LIMIT {limit}"

    log.info(f"Consultando datastore: {sql[:120]}...")
    resp = requests.get(DATASTORE_API, params={"sql": sql}, timeout=60)
    resp.raise_for_status()
    return resp.json().get("result", {})