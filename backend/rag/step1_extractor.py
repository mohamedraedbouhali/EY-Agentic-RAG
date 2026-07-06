"""Extraction du texte des PDF (pymupdf4llm + pdfplumber).

Deux sorties complémentaires pour chaque TdR :
- markdown : texte structuré avec titres (#, ##, ###) via pymupdf4llm.
  Sert de base au chunking sémantique (les titres délimitent les sections).
- pages : liste du texte brut page par page (pdfplumber).
  Conservée pour la détection des en-têtes/pieds répétés et la numérotation.

Fallback OCR : si l'extraction native renvoie quasi rien (PDF scanné),
on bascule automatiquement sur EasyOCR (pdf2image + EasyOCR).
"""

from __future__ import annotations

import os
import re
import numpy as np
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pymupdf4llm

# Under this number of extracted characters, the PDF is considered
# scanned (image content) → OCR fallback.
OCR_MIN_CHARS   = 200
OCR_TIMEOUT_SEC = 90     # EasyOCR on CPU is slow; 30s caused cascading timeouts
OCR_MAX_PAGES   = 30     # was 5 — scanned PDFs lost every page beyond the 5th
OCR_DPI         = 150

_POPPLER_PATH = r"C:\Users\LENOVO\poppler\poppler-24.08.0\Library\bin"
_ocr_reader   = None


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class PdfDocument:
    """Résultat de l'extraction d'un PDF."""

    document_id: str                              # nom du fichier sans extension
    source_path: str
    markdown:    str                              # texte structuré (titres, tableaux Markdown)
    pages:       list[str] = field(default_factory=list)  # texte brut par page
    ocr_used:    bool      = False                # True si le texte vient de l'OCR

    @property
    def n_pages(self) -> int:
        return len(self.pages)


# ── OCR helpers ───────────────────────────────────────────────────────────────

def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("    Loading EasyOCR model (fr + en)...", flush=True)
        _ocr_reader = easyocr.Reader(['fr', 'en'], gpu=False)
        print("    EasyOCR ready.")
    return _ocr_reader


def _ocr_page_worker(pdf_path: str, page_num: int) -> str:
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num,
            dpi=OCR_DPI,
            poppler_path=_POPPLER_PATH,
        )
        if images:
            reader  = _get_ocr_reader()
            results = reader.readtext(np.array(images[0]), detail=0)
            return " ".join(results)
    except Exception as e:
        print(f"    [!] OCR error on page {page_num}: {e}")
    return ""


def _ocr_page(pdf_path: str, page_num: int) -> str:
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_ocr_page_worker, pdf_path, page_num)
        try:
            return future.result(timeout=OCR_TIMEOUT_SEC)
        except FuturesTimeout:
            print(f"    [!] OCR timeout ({OCR_TIMEOUT_SEC}s) on page {page_num}, skipping")
            return ""


def _ocr_pdf(path: Path) -> list[str]:
    """OCR all pages of a scanned PDF up to OCR_MAX_PAGES."""
    with pdfplumber.open(str(path)) as pdf:
        n = len(pdf.pages)
    pages = []
    for page_num in range(1, min(n, OCR_MAX_PAGES) + 1):
        print(f"    [OCR] Page {page_num}/{n}...", end=" ", flush=True)
        text = _ocr_page(str(path), page_num)
        pages.append(text)
        print("OK" if text.strip() else "empty")
    return pages


# ── Table serialiser (pymupdf — handles merged cells) ────────────────────────

def _serialize_pymupdf_table(data: list[list], page_num: int, table_idx: int) -> str:
    """Convert pymupdf table data to key:value text.

    Handles two PDF table patterns that break simpler extractors:
    - Merged / spanned cells (None in subsequent rows) → carry-forward the value.
    - Wrapped cell text split across multiple rows → join into one logical row.
    """
    if not data or len(data) < 2:
        return ""

    n_cols = max(len(r) for r in data)

    # Normalise: pad to equal width, replace None/newlines
    rows = []
    for row in data:
        r = [str(c).replace("\n", " ").strip() if c is not None else ""
             for c in row]
        r += [""] * (n_cols - len(r))
        rows.append(r)

    # Build header — merge first two rows when row[1] is a sparse CONTINUATION
    # of the header (wrapped header text). A row with content in the first
    # column is a data row, never a header continuation: merging it used to
    # swallow the first criteria row of scoring tables into the header, which
    # then prefixed every emitted line with the wrong criterion.
    headers = rows[0][:]
    data_start = 1
    if (len(rows) > 1 and not rows[1][0]
            and sum(1 for c in rows[1] if c) <= max(1, n_cols // 2)):
        for i, cell in enumerate(rows[1]):
            if cell:
                headers[i] = (headers[i] + " " + cell).strip() if headers[i] else cell
        data_start = 2
    if not any(headers):
        headers = [f"Col{i}" for i in range(n_cols)]

    lines = [f"[Tableau p.{page_num} #{table_idx + 1}]"]
    current: list[str] = [""] * n_cols
    last_key = ""
    has_current = False

    def _emit():
        parts = []
        for h, cell in zip(headers, current):
            h_c = h.strip()
            c_c = cell.strip()
            if not c_c or c_c.upper() == h_c.upper():
                continue
            parts.append(f"{h_c}: {c_c}" if h_c else c_c)
        if parts:
            lines.append(", ".join(parts))

    for row in rows[data_start:]:
        if not any(row):
            continue

        non_empty_count = sum(1 for c in row if c)

        if row[0]:                              # new logical row
            if has_current:
                _emit()
            current = row[:]
            last_key = row[0]
            has_current = True
        elif non_empty_count >= 2:              # new sub-row (inherited key)
            if has_current:
                _emit()
            current = row[:]
            current[0] = last_key
            has_current = True
        else:                                   # wrapped text — append to current
            if not has_current:
                current = row[:]
                has_current = True
            else:
                for i, cell in enumerate(row):
                    if cell:
                        current[i] = (current[i] + " " + cell).strip() if current[i] else cell

    if has_current:
        _emit()

    return "\n".join(lines) if len(lines) > 1 else ""


def _cell_text(page, cell_rect) -> str:
    """Extract properly spaced text from a table cell using its bounding box."""
    try:
        return page.get_text("text", clip=cell_rect).replace("\n", " ").strip()
    except Exception:
        return ""


def _extract_tables_pymupdf(path: str) -> list[str]:
    """Extract all tables from a PDF using pymupdf's native table detector.

    Uses page.get_text("text", clip=cell_rect) per cell to get properly
    spaced text — avoids the word-concatenation bug in tab.extract().
    """
    try:
        import fitz
        blocks: list[str] = []
        doc = fitz.open(path)
        for page_num, page in enumerate(doc, start=1):
            try:
                tabs = page.find_tables()
                for t_idx, tab in enumerate(tabs.tables):
                    raw = tab.extract()       # shape rows×cols, None = merged cell
                    try:
                        # tab.rows[r].cells[c] is the bbox of cell (r,c) or
                        # None for merged cells — aligned 1:1 with extract().
                        # (tab.cells is a flat list that EXCLUDES merged
                        # cells, so positional math over it maps to wrong
                        # cells; verified empirically.)
                        data = []
                        for r_idx, trow in enumerate(tab.rows):
                            data_row = []
                            for c_idx, rect in enumerate(trow.cells):
                                val = raw[r_idx][c_idx] if r_idx < len(raw) and c_idx < len(raw[r_idx]) else None
                                if rect is None:
                                    data_row.append(val)
                                else:
                                    text = _cell_text(page, rect)
                                    data_row.append(text if text else val)
                            data.append(data_row)
                    except (AttributeError, IndexError, TypeError):
                        data = raw   # fallback: tab.rows not available
                    block = _serialize_pymupdf_table(data, page_num, t_idx)
                    if block:
                        blocks.append(block)
            except Exception:
                pass
        doc.close()
        return blocks
    except Exception:
        return []


def _pages_with_markdown_tables(markdown: str) -> set[int]:
    """Page numbers whose Markdown segment already contains a table row."""
    pages: set[int] = set()
    current: int | None = None
    for line in markdown.split("\n"):
        m = re.match(r'\[Page (\d+)\]', line.strip())
        if m:
            current = int(m.group(1))
        elif line.lstrip().startswith("|") and current is not None:
            pages.add(current)
    return pages


# ── Core extraction ───────────────────────────────────────────────────────────

def _pages_to_markdown(page_dicts: list[dict]) -> str:
    """Join per-page markdown with [Page N] markers so the chunker can
    assign each chunk its real page number (downstream cleaning strips
    the markers before embedding/generation)."""
    parts = []
    for d in page_dicts:
        text = d.get("text", "").strip()
        if not text:
            continue
        page_num = d.get("metadata", {}).get("page_number") or len(parts) + 1
        parts.append(f"[Page {page_num}]\n{text}")
    return "\n\n".join(parts)


def read_pdf(path: str | Path) -> PdfDocument:
    """Extrait un PDF en Markdown structuré + texte brut page par page.

    Trois passes, de la plus fidèle à la plus tolérante :
    1. Extraction native (use_ocr=False) — PDF avec couche texte.
    2. OCR intégré pymupdf4llm/RapidOCR — PDF scannés (rapide sur CPU,
       traite toutes les pages).
    3. EasyOCR legacy — dernier recours si RapidOCR échoue.

    Args:
        path: chemin du fichier PDF.

    Returns:
        PdfDocument avec markdown (pymupdf4llm) et pages (pdfplumber).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF introuvable : {path}")

    # Pass 1 — native text layer, page by page (for [Page N] markers).
    try:
        page_dicts = pymupdf4llm.to_markdown(
            str(path), show_progress=False, use_ocr=False, page_chunks=True)
    except Exception:
        page_dicts = []
    markdown = _pages_to_markdown(page_dicts)
    ocr_used = False

    # Pass 2 — integrated OCR (RapidOCR): fast on CPU, covers ALL pages.
    if len(markdown.strip()) < OCR_MIN_CHARS:
        try:
            page_dicts = pymupdf4llm.to_markdown(
                str(path), show_progress=False, page_chunks=True)
            markdown = _pages_to_markdown(page_dicts)
            ocr_used = True
        except Exception as e:
            print(f"    [!] integrated OCR failed: {e}")

    # Pass 3 — legacy EasyOCR fallback (last resort).
    if len(markdown.strip()) < OCR_MIN_CHARS:
        ocr_pages = _ocr_pdf(path)
        markdown  = "\n\n".join(
            f"[Page {i}]\n{p}" for i, p in enumerate(ocr_pages, start=1) if p.strip())
        ocr_used  = True
        pages     = ocr_pages
    else:
        # Texte brut par page (pdfplumber) — en-têtes répétés / numérotation.
        pages = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    pages.append(page.extract_text() or "")
        except Exception:
            pages = [d.get("text", "") for d in page_dicts]

    # Structured table blocks (pymupdf) — FALLBACK ONLY, for pages where the
    # pymupdf4llm pass produced no Markdown table. On pages that already have
    # one, appending the serialized version stored a second, differently
    # worded copy of the same table — and when the serializer misread the
    # layout, retrieval could feed the LLM the garbled copy instead of the
    # good one.
    table_blocks = _extract_tables_pymupdf(str(path))
    if table_blocks:
        covered = _pages_with_markdown_tables(markdown)
        kept = []
        for block in table_blocks:
            m = re.match(r'\[Tableau p\.(\d+)', block)
            if m and int(m.group(1)) in covered:
                continue
            kept.append(block)
        if kept:
            markdown += "\n\n" + "\n\n".join(kept)

    return PdfDocument(
        document_id=path.stem,
        source_path=str(path),
        markdown=markdown,
        pages=pages,
        ocr_used=ocr_used,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def load_all_pdfs(data_folder: str) -> list[dict]:
    """Charge tous les PDFs d'un dossier et retourne des dicts compatibles pipeline.

    Each dict contains:
        filename  : basename of the PDF file
        text      : structured Markdown (pymupdf4llm) — used by chunker & metadata
        path      : absolute file path
        pages     : raw text per page (pdfplumber)
        ocr_used  : True if OCR fallback was triggered
    """
    documents = []
    pdf_files = [f for f in os.listdir(data_folder) if f.lower().endswith(".pdf")]
    print(f"Found {len(pdf_files)} PDF files in {data_folder}")

    for filename in sorted(pdf_files):
        path = Path(data_folder) / filename
        print(f"  Reading: {filename} ...", end=" ", flush=True)
        try:
            doc = read_pdf(path)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        word_count = len(doc.markdown.split())
        ocr_tag    = " [OCR]" if doc.ocr_used else ""
        print(f"{word_count} words{ocr_tag}")

        if word_count > 20:
            documents.append({
                "filename": filename,
                "text":     doc.markdown,   # structured Markdown → richer chunking
                "path":     str(path),
                "pages":    doc.pages,
                "ocr_used": doc.ocr_used,
            })
        else:
            print(f"  [!] Skipped (too little text even after OCR)")

    # De-glue OCR output ("conditionsgenerales" → "conditions generales").
    # Domain vocabulary is harvested from the natively-extracted documents
    # first, so corpus-specific words are recognised inside glued tokens.
    ocr_docs = [d for d in documents if d["ocr_used"]]
    if ocr_docs:
        try:
            from rag.ocr_degluer import add_domain_words, deglue_text
            native_texts = [d["text"] for d in documents if not d["ocr_used"]]
            added = add_domain_words(native_texts)
            print(f"  De-gluing {len(ocr_docs)} OCR documents "
                  f"(+{added} domain words in lexicon)...")
            for d in ocr_docs:
                d["text"] = deglue_text(d["text"])
        except ImportError as e:
            print(f"  [!] wordfreq not installed — OCR de-gluing skipped ({e})")

    return documents


def list_pdfs(directory: str | Path) -> list[Path]:
    """Liste les PDF d'un dossier, triés par nom."""
    return sorted(Path(directory).glob("*.pdf"))
