import re
import pdfplumber
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

_POPPLER_PATH = r"C:\Users\LENOVO\poppler\poppler-24.08.0\Library\bin"

_ocr_reader = None

OCR_TIMEOUT_SEC  = 30   # seconds per page before giving up
OCR_MAX_PAGES    = 5    # max OCR pages per document
OCR_DPI          = 150  # lower than 300 → ~4× faster, still readable


def _get_ocr_reader():
    """Lazy-load EasyOCR reader — downloaded once, cached for the whole indexing run."""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("    Loading EasyOCR model (fr + en)...", flush=True)
        _ocr_reader = easyocr.Reader(['fr', 'en'], gpu=False)
        print("    EasyOCR ready.")
    return _ocr_reader


def _ocr_page_worker(pdf_path: str, page_num: int) -> str:
    """Blocking OCR call — run inside a thread so it can be timed out."""
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
    """OCR a single page with a hard timeout to avoid hanging on dense images."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_ocr_page_worker, pdf_path, page_num)
        try:
            return future.result(timeout=OCR_TIMEOUT_SEC)
        except FuturesTimeout:
            print(f"    [!] OCR timeout ({OCR_TIMEOUT_SEC}s) on page {page_num}, skipping")
            return ""


def table_to_natural(table: list) -> str:
    """Convert a table to natural language text for semantic embedding."""
    if not table:
        return ""

    def _cell(c) -> str:
        text = str(c or "").strip()
        if re.match(r'^[-–—\s]+$', text):
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    rows = []
    for r in table:
        if r:
            cleaned = [_cell(c) for c in r]
            if any(cleaned):
                rows.append(cleaned)

    if not rows:
        return ""

    # First row is a header when its cells don't start with "-" or "digit+%/€"
    def _is_header_row(row):
        non_empty = [c for c in row if c]
        if not non_empty:
            return False
        return all(
            not c.startswith('-') and not re.match(r'^\d+\s*[%€]', c)
            for c in non_empty
        )

    has_header = len(rows) > 1 and _is_header_row(rows[0])
    parts = []

    if has_header:
        headers = rows[0]
        for row in rows[1:]:
            row_parts = []
            for h, v in zip(headers, row):
                if h and v:
                    row_parts.append(f"{h} : {v}")
                elif v:
                    row_parts.append(v)
            if row_parts:
                parts.append(". ".join(row_parts))
    else:
        for row in rows:
            non_empty = [c for c in row if c]
            if len(non_empty) >= 2:
                parts.append(f"{non_empty[0]} : {'. '.join(non_empty[1:])}")
            elif non_empty:
                parts.append(non_empty[0])

    return " | ".join(parts)


def extract_text_from_pdf(pdf_path: str) -> str:
    full_text  = ""
    ocr_count  = 0
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables       = page.extract_tables()
                table_bboxes = [t.bbox for t in page.find_tables()] if tables else []

                if table_bboxes:
                    filtered = page.filter(
                        lambda obj, bboxes=table_bboxes: not any(
                            obj.get("x0", 0) >= bbox[0] - 1
                            and obj.get("top", 0) >= bbox[1] - 1
                            and obj.get("x1", 0) <= bbox[2] + 1
                            and obj.get("bottom", 0) <= bbox[3] + 1
                            for bbox in bboxes
                        )
                    )
                    page_text = filtered.extract_text() or ""
                else:
                    page_text = page.extract_text() or ""

                # Fall back to EasyOCR if pdfplumber found nothing on this page
                if not page_text.strip():
                    if ocr_count >= OCR_MAX_PAGES:
                        print(f"    [OCR] Page {page_num}: skipped (max {OCR_MAX_PAGES} OCR pages reached)")
                    else:
                        print(f"    [OCR] Page {page_num}: no text, trying OCR...", end=" ", flush=True)
                        page_text  = _ocr_page(pdf_path, page_num)
                        ocr_count += 1
                        print("OK" if page_text.strip() else "empty")

                full_text += f"\n[Page {page_num}]\n{page_text}\n"

                # Inject table content immediately after page text so it stays
                # near the section headings that precede it in the document.
                for table in tables:
                    natural = table_to_natural(table)
                    if natural:
                        full_text += f"{natural}\n"
    except Exception as e:
        print(f"  [!] Error reading {pdf_path}: {e}")
    return full_text


def load_all_pdfs(data_folder: str) -> list[dict]:
    documents = []
    pdf_files = [f for f in os.listdir(data_folder) if f.lower().endswith(".pdf")]
    print(f"Found {len(pdf_files)} PDF files in {data_folder}")
    for filename in sorted(pdf_files):
        path = os.path.join(data_folder, filename)
        print(f"  Reading: {filename} ...", end=" ", flush=True)
        text       = extract_text_from_pdf(path)
        word_count = len(text.split())
        print(f"{word_count} words")
        if word_count > 20:
            documents.append({"filename": filename, "text": text, "path": path})
        else:
            print(f"  [!] Skipped (too little text -- even after OCR)")
    return documents
