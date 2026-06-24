import pdfplumber
import os
import numpy as np

_POPPLER_PATH = r"C:\Users\LENOVO\poppler\poppler-24.08.0\Library\bin"

_ocr_reader = None


def _get_ocr_reader():
    """Lazy-load EasyOCR reader — downloaded once, cached for the whole indexing run."""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("    Loading EasyOCR model (fr + en)...", flush=True)
        _ocr_reader = easyocr.Reader(['fr', 'en'], gpu=False)
        print("    EasyOCR ready.")
    return _ocr_reader


def _ocr_page(pdf_path: str, page_num: int) -> str:
    """Convert a single PDF page to image and run EasyOCR (deep learning CNN+LSTM)."""
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num,
            dpi=300,
            poppler_path=_POPPLER_PATH,
        )
        if images:
            reader  = _get_ocr_reader()
            results = reader.readtext(np.array(images[0]), detail=0)
            return " ".join(results)
    except Exception as e:
        print(f"    [!] OCR failed on page {page_num}: {e}")
    return ""


def table_to_markdown(table: list) -> str:
    if not table or not table[0]:
        return ""
    rows = []
    header = [str(cell or "").strip() for cell in table[0]]
    rows.append("| " + " | ".join(header) + " |")
    rows.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in table[1:]:
        cells = [str(cell or "").strip() for cell in row]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def extract_text_from_pdf(pdf_path: str) -> str:
    full_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables      = page.extract_tables()
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
                    print(f"    [OCR] Page {page_num}: no text, trying OCR...", end=" ", flush=True)
                    page_text = _ocr_page(pdf_path, page_num)
                    print("OK" if page_text.strip() else "empty")

                full_text += f"\n[Page {page_num}]\n{page_text}\n"

                for i, table in enumerate(tables, start=1):
                    md = table_to_markdown(table)
                    if md:
                        # Extract header row words to build a semantic context label
                        header_words = " ".join(
                            str(cell or "").strip()
                            for cell in (table[0] if table else [])
                            if cell and str(cell).strip()
                        )
                        context_label = f"Tableau de critères et pondération — {header_words}" if header_words else "Tableau de données"
                        full_text += f"\n[Tableau {i} – Page {page_num}] {context_label}:\n{md}\n"
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
        text      = extract_text_from_pdf(path)
        word_count = len(text.split())
        print(f"{word_count} words")
        if word_count > 20:
            documents.append({"filename": filename, "text": text, "path": path})
        else:
            print(f"  [!] Skipped (too little text -- even after OCR)")
    return documents
