"""
ocr_engine.py — Motor PaddleOCR para extracción del archivo histórico 1964.

Procesa mínimo 15 páginas del PDF de Hacienda 1964 y guarda los resultados
en data/processed/ocr_1964_extracted.parquet.

Uso:
    python -m src.ocr_engine --pages 1-15
    python -m src.ocr_engine --pages 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29
"""

import argparse
import json
from pathlib import Path
from typing import Union

import pandas as pd

from src.utils import DATA_PROC, PDF_1964_LOCAL, setup_logger

log = setup_logger("ocr_engine")

OCR_OUTPUT = DATA_PROC / "ocr_1964_extracted.parquet"
OCR_JSON   = DATA_PROC / "ocr_1964_raw.json"


def parse_page_range(pages_str: str) -> list[int]:
    """
    Convierte '1-15' o '1,3,5,7,9,11,13,15,17,19,21,23,25,27,29' a lista de enteros.
    """
    pages = []
    for part in pages_str.split(","):
        if "-" in part:
            start, end = part.split("-")
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part.strip()))
    return sorted(set(pages))


def rasterize_pdf_pages(pdf_path: Path, page_indices: list[int]) -> list:
    """
    Convierte páginas del PDF a imágenes PIL para PaddleOCR.
    Usa pdf2image con DPI=200 para balance calidad/velocidad.
    """
    from pdf2image import convert_from_path
    log.info(f"Rasterizando {len(page_indices)} páginas del PDF: {pdf_path}")

    # pdf2image usa índices 1-based en 'first_page'/'last_page'
    # Procesamos página a página para control de memoria
    images = {}
    for page_num in page_indices:
        try:
            imgs = convert_from_path(
                pdf_path,
                dpi=200,
                first_page=page_num,
                last_page=page_num,
                fmt="RGB",
            )
            if imgs:
                images[page_num] = imgs[0]
                log.info(f"  Página {page_num} rasterizada ({imgs[0].size})")
        except Exception as e:
            log.warning(f"  No se pudo rasterizar página {page_num}: {e}")

    return images


def run_paddleocr(images: dict) -> list[dict]:
    """
    Corre PaddleOCR sobre cada imagen y extrae bloques de texto.
    Retorna lista de registros con: page_number, block_idx, text, confidence, bbox.
    """
    from paddleocr import PaddleOCR
    import numpy as np

    log.info("Inicializando PaddleOCR (lang=es, use_gpu=False)...")
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="es",
        use_gpu=False,
        show_log=False,
    )

    records = []
    for page_num, img in images.items():
        log.info(f"  Procesando OCR en página {page_num}...")
        img_array = np.array(img)
        result = ocr.ocr(img_array, cls=True)

        if not result or not result[0]:
            log.warning(f"  Página {page_num}: sin resultados OCR")
            continue

        for block_idx, line in enumerate(result[0]):
            bbox, (text, confidence) = line
            records.append({
                "page_number":  page_num,
                "block_idx":    block_idx,
                "text":         text.strip(),
                "confidence":   round(float(confidence), 4),
                "bbox_x1":      int(bbox[0][0]),
                "bbox_y1":      int(bbox[0][1]),
                "bbox_x2":      int(bbox[2][0]),
                "bbox_y2":      int(bbox[2][1]),
            })

        log.info(f"  Página {page_num}: {len([r for r in records if r['page_number']==page_num])} bloques extraídos")

    return records


def extract_numerical_blocks(records: list[dict]) -> pd.DataFrame:
    """
    Filtra bloques de texto que contienen cifras numéricas (presupuesto, montos).
    Útil para aislar tablas financieras del texto narrativo.
    """
    import re
    pattern = re.compile(r'\b\d[\d,.\s]{2,}\b')
    numerical = [r for r in records if pattern.search(r.get("text", ""))]
    log.info(f"Bloques numéricos identificados: {len(numerical)} de {len(records)}")
    return pd.DataFrame(numerical)


def run_ocr_pipeline(pdf_path: Path, pages: list[int]) -> Path:
    """
    Pipeline completo OCR:
        1. Rasteriza páginas del PDF.
        2. Corre PaddleOCR sobre cada imagen.
        3. Guarda resultados completos en JSON (para auditoría).
        4. Guarda DataFrame filtrado en Parquet.
    Retorna la ruta del Parquet.
    """
    assert len(pages) >= 15, f"Se requieren al menos 15 páginas; se proporcionaron {len(pages)}"

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF no encontrado: {pdf_path}\n"
            "Ejecuta primero: python -c \"from src.mcp_server import descargar_documento_1964; descargar_documento_1964()\""
        )

    log.info(f"=== OCR Pipeline 1964 | Páginas: {pages} ===")

    images  = rasterize_pdf_pages(pdf_path, pages)
    records = run_paddleocr(images)

    # Guardar JSON completo (para trazabilidad)
    OCR_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    log.info(f"JSON completo guardado: {OCR_JSON} ({len(records)} bloques)")

    # DataFrame y Parquet
    df = pd.DataFrame(records)
    df.to_parquet(OCR_OUTPUT, index=False, compression="zstd")
    log.info(f"Parquet guardado: {OCR_OUTPUT} ({OCR_OUTPUT.stat().st_size / 1024:.1f} KB)")

    # Verificar cobertura de páginas
    unique_pages = df["page_number"].nunique()
    log.info(f"Páginas únicas con OCR exitoso: {unique_pages}")
    assert unique_pages >= 15, f"FALLO: solo {unique_pages} páginas procesadas (mínimo 15)"

    return OCR_OUTPUT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCR Engine 1964 — PaddleOCR")
    parser.add_argument(
        "--pages",
        default="1-15",
        help="Rango o lista de páginas. Ej: '1-15' o '1,3,5,7,9,11,13,15,17,19,21,23,25,27,29'",
    )
    parser.add_argument(
        "--pdf",
        default=str(PDF_1964_LOCAL),
        help="Ruta local al PDF 1964",
    )
    args = parser.parse_args()

    pages = parse_page_range(args.pages)
    log.info(f"Páginas a procesar: {pages}")

    result = run_ocr_pipeline(Path(args.pdf), pages)
    print(f"OK: {result}")