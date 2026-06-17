import pdfplumber
import os


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
                tables = page.extract_tables()
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

                full_text += f"\n[Page {page_num}]\n{page_text}\n"

                for i, table in enumerate(tables, start=1):
                    md = table_to_markdown(table)
                    if md:
                        full_text += f"\n[Tableau {i} – Page {page_num}]\n{md}\n"
    except Exception as e:
        print(f"  ⚠ Error reading {pdf_path}: {e}")
    return full_text


def load_all_pdfs(data_folder: str) -> list[dict]:
    documents = []
    pdf_files = [f for f in os.listdir(data_folder) if f.lower().endswith(".pdf")]
    print(f"Found {len(pdf_files)} PDF files in {data_folder}")
    for filename in sorted(pdf_files):
        path = os.path.join(data_folder, filename)
        print(f"  Reading: {filename} ...", end=" ", flush=True)
        text = extract_text_from_pdf(path)
        word_count = len(text.split())
        print(f"{word_count} words")
        if word_count > 20:
            documents.append({"filename": filename, "text": text, "path": path})
        else:
            print(f"  ⚠ Skipped (too little text — may be scanned)")
    return documents
