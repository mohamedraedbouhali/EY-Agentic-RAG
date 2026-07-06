"""Regression tests for the RAG ingestion pipeline (chunker + extractor).

Run after ANY change to rag/step1_extractor.py or rag/step3_chunker.py:

    cd backend
    python test_pipeline.py

Guards against the July 2026 table bug: markdown tables being flattened onto
one line by the chunker (unreadable for the LLM) and the extractor appending
a second, garbled serialized copy of tables the markdown pass already had.
"""
import sys
import os
import io
import re

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from rag.step3_chunker import (
    split_into_chunks, _split_table_block, _token_len, CHUNK_SIZE,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def test_chunker_basics():
    print("\n== Chunker basics ==")
    check("empty input", split_into_chunks("") == [])
    check("whitespace input", split_into_chunks("   \n\n  ") == [])
    c = split_into_chunks("Une seule phrase.", "x.pdf")
    check("single sentence", len(c) == 1 and c[0]["page"] == 1)

    text = "[Page 1]\n" + ("Phrase de test numero un. " * 100) \
         + "\n[Page 2]\n" + ("Autre phrase ici. " * 100)
    c = split_into_chunks(text, "x.pdf")
    check("page tracking", c[0]["page"] == 1 and c[-1]["page"] == 2,
          f"pages={[x['page'] for x in c]}")


def test_tables_stay_multiline():
    print("\n== Tables keep one row per line ==")
    text = ("[Page 1]\nIntro avant le tableau.\n"
            "|A|B|\n|---|---|\n|1|2|\n|3|4|\n"
            "Texte apres.")
    c = split_into_chunks(text, "x.pdf")
    check("small table atomic", len(c) == 1)
    check("rows on own lines", "|A|B|\n|---|---|\n|1|2|\n|3|4|" in c[0]["text"],
          repr(c[0]["text"]))


def test_bullets_and_headings_keep_lines():
    print("\n== Bullets & headings keep their own lines ==")
    text = ("[Page 1]\n###### 2.1 Conditions generales :\n"
            "- premier point.\n- deuxieme point.\n- troisieme point.\n"
            "###### 2.2 Conditions professionnelles :\nLe signataire.")
    c = split_into_chunks(text, "x.pdf")
    t = c[0]["text"]
    check("bullets on own lines",
          all(f"\n- {w} point." in t for w in ("premier", "deuxieme", "troisieme")), repr(t))
    check("next heading on own line", "\n###### 2.2" in t, repr(t))


def test_oversized_table_split_by_rows():
    print("\n== Oversized table split on row boundaries ==")
    rows = "\n".join(
        f"|ligne {i} avec du contenu assez long pour prendre des tokens {'x ' * 30}|{i}|"
        for i in range(60))
    table = "|Nom|Valeur|\n|---|---|\n" + rows
    pieces = _split_table_block(table)
    check("split into pieces", len(pieces) > 1)
    check("header repeated", all(p.startswith("|Nom|Valeur|") for p in pieces))
    joined = "\n".join(pieces)
    check("no row lost", all(f"|ligne {i} " in joined for i in range(60)))


def test_ocr_degluer():
    print("\n== OCR de-gluer ==")
    try:
        from rag.ocr_degluer import deglue_text
    except ImportError:
        print("  [SKIP] wordfreq not installed")
        return
    check("splits glued words",
          "conditions generales et professionnelles" in
          deglue_text("les conditionsgenerales etprofessionnelles suivantes"))
    check("fixes I' elision",
          deglue_text("I'accompagnement") == "l'accompagnement")
    check("keeps rare real words whole",
          deglue_text("AU NIVEAU DES COLLECTIVITES TERRITORIALES DECENTRALISEES")
          == "AU NIVEAU DES COLLECTIVITES TERRITORIALES DECENTRALISEES")
    check("keeps codes and names untouched",
          deglue_text("Projet WISEMED, A_T 2.3 0390 INTERREG NEXT MED")
          == "Projet WISEMED, A_T 2.3 0390 INTERREG NEXT MED")
    check("keeps clean French untouched",
          deglue_text("Recrutement d'un expert pour assurer des formations")
          == "Recrutement d'un expert pour assurer des formations")


def test_real_document():
    print("\n== Real document: formations-culture-entrepreneuriale ==")
    pdf = os.path.join(os.path.dirname(__file__), "..", "data",
                       "TDR-Recrutement-dun-expert-pour-assurer-des-formations-"
                       "en-culture-entrepreneuriale-.pdf")
    if not os.path.exists(pdf):
        print("  [SKIP] PDF not found")
        return
    from rag.step1_extractor import read_pdf
    doc = read_pdf(pdf)
    check("no garbled duplicate table block", "[Tableau p.6" not in doc.markdown)

    chunks = split_into_chunks(doc.markdown, os.path.basename(pdf))
    table_chunks = [c for c in chunks if "Formateur" in c["text"]]
    check("criteria table retrievable", len(table_chunks) >= 1)
    if table_chunks:
        t = table_chunks[0]["text"]
        # /40 must be in the same table ROW (same line) as the 4 diploma items
        row = next((ln for ln in t.split("\n")
                    if "Formateur" in ln and ln.strip().startswith("|")), "")
        check("table row intact", bool(row))
        check("/40 attached to diploma row", row.rstrip().endswith("|/40|"), repr(row[-60:]))
        check("all 4 diploma items in one row",
              all(kw in row for kw in ("Formateur", "Bac+5",
                                       "compl", "missions")), repr(row))


def test_no_flattened_tables_in_corpus():
    print("\n== Whole corpus: no flattened tables (slow, extraction of all PDFs) ==")
    if "--full" not in sys.argv:
        print("  [SKIP] pass --full to run (takes several minutes, includes OCR)")
        return
    from rag.step1_extractor import load_all_pdfs
    data = os.path.join(os.path.dirname(__file__), "..", "data")
    flat = 0
    for d in load_all_pdfs(data):
        for c in split_into_chunks(d["text"], d["filename"]):
            for line in c["text"].split("\n"):
                if line.strip().startswith("|") and "| |" in line:
                    flat += 1
                    print(f"  [FLAT] {d['filename']} chunk {c['chunk_index']}: {line[:100]}")
                    break
    check("zero flattened tables", flat == 0, f"{flat} found")


if __name__ == "__main__":
    test_chunker_basics()
    test_tables_stay_multiline()
    test_bullets_and_headings_keep_lines()
    test_oversized_table_split_by_rows()
    test_ocr_degluer()
    test_real_document()
    test_no_flattened_tables_in_corpus()
    print("\n" + "=" * 50)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} test(s): {FAILURES}")
        sys.exit(1)
    print("All tests passed.")
