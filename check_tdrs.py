"""
TDR Classifier — uses the same scoring engine as the RAG pipeline (step2_metadata.py).
Scans every PDF in data/ and moves non-TDR files to data/not_tdrs/.

Usage:
  python check_tdrs.py           # interactive prompt before moving
  python check_tdrs.py --yes     # auto-confirm
  python check_tdrs.py --dry     # print results only, move nothing
  python check_tdrs.py --thresh 15   # change the is_tdr score threshold (default 10)
"""

import os
import sys
import shutil
import pdfplumber

# Add backend to path so we can import the shared engine
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from rag.step2_metadata import classify_tdr

DATA_FOLDER    = os.path.join(os.path.dirname(__file__), "data")
NOT_TDR_FOLDER = os.path.join(DATA_FOLDER, "not_tdrs")
DEFAULT_THRESH = 10   # same as RAG pipeline


def extract_text(path: str, max_pages: int = 5) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            text = ""
            for page in pdf.pages[:max_pages]:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            return text
    except Exception as e:
        return f"__ERROR__: {e}"


def move_file(src: str, dst_folder: str):
    os.makedirs(dst_folder, exist_ok=True)
    dst = os.path.join(dst_folder, os.path.basename(src))
    if os.path.exists(dst):
        base, ext = os.path.splitext(os.path.basename(src))
        dst = os.path.join(dst_folder, f"{base}_dup{ext}")
    shutil.move(src, dst)


def main(auto_yes: bool = False, dry_run: bool = False, threshold: int = DEFAULT_THRESH):
    if not os.path.isdir(DATA_FOLDER):
        print(f"ERROR: data folder not found at {DATA_FOLDER}")
        return

    pdf_files = sorted(
        f for f in os.listdir(DATA_FOLDER)
        if f.lower().endswith(".pdf")
        and os.path.isfile(os.path.join(DATA_FOLDER, f))
    )

    if not pdf_files:
        print("No PDF files found in data/")
        return

    print("=" * 80)
    print(f"  EY -- TDR Classifier v3   ({len(pdf_files)} files)   threshold={threshold}")
    print("=" * 80)
    print(f"  {'File':<52} {'Verdict':<10} {'Score':>6}  {'Confidence':>10}  Label")
    print(f"  {'-'*52} {'-'*10} {'-'*6}  {'-'*10}  {'-'*16}")

    tdr_files     = []
    non_tdr_files = []
    no_text_files = []
    error_files   = []

    for filename in pdf_files:
        path = os.path.join(DATA_FOLDER, filename)
        text = extract_text(path)

        if text.startswith("__ERROR__"):
            error_files.append((filename, text[9:].strip()))
            print(f"  [ERR]  {filename[:52]:<52} {'ERROR':<10} {'':>6}  {'':>10}")
            continue

        if not text.strip():
            no_text_files.append(filename)
            print(f"  [?? ]  {filename[:52]:<52} {'NO_TEXT':<10} {'':>6}  {'':>10}  scanned PDF")
            continue

        info    = classify_tdr(text, filename)
        score   = info["tdr_score"]
        conf    = info["tdr_confidence"]
        label   = info["tdr_label"]
        is_tdr  = score >= threshold

        tag     = "[OK ]" if is_tdr else "[NO ]"
        verdict = "TDR" if is_tdr else "NOT_TDR"
        conf_str = f"{conf*100:.0f}%"

        if is_tdr:
            tdr_files.append(filename)
        else:
            non_tdr_files.append((filename, label, score))

        print(f"  {tag}  {filename[:52]:<52} {verdict:<10} {score:>6.1f}  {conf_str:>10}  {label}")

    # Summary
    print("\n" + "=" * 80)
    print(f"  TDR confirmed : {len(tdr_files)}")
    print(f"  NOT TDR       : {len(non_tdr_files)}")
    print(f"  No text (OCR) : {len(no_text_files)}  (kept in data/, handled by OCR at indexing)")
    print(f"  Errors        : {len(error_files)}")
    print("=" * 80)

    if non_tdr_files:
        print("\n  Non-TDR files detail:")
        for fn, lbl, sc in sorted(non_tdr_files, key=lambda x: x[2]):
            print(f"    score={sc:>6.1f}  [{lbl:<14}]  {fn}")

    to_move = [(fn, lbl, sc) for fn, lbl, sc in non_tdr_files] + \
              [(fn, "ERROR", 0) for fn, _ in error_files]

    if not to_move:
        print("\n  All files are TDRs -- nothing to move.")
        return

    if dry_run:
        print(f"\n  [DRY RUN] {len(to_move)} file(s) would be moved to data/not_tdrs/ -- no changes made.")
        return

    print(f"\n  {len(to_move)} file(s) will be moved to data/not_tdrs/")
    if not auto_yes:
        print("  Continue? (y/n): ", end="", flush=True)
        answer = input().strip().lower()
        if answer != "y":
            print("  Aborted -- no files moved.")
            return

    moved = 0
    for fn, *_ in to_move:
        src = os.path.join(DATA_FOLDER, fn)
        if os.path.exists(src):
            move_file(src, NOT_TDR_FOLDER)
            print(f"    >> moved  {fn}")
            moved += 1

    print(f"\n  Done. {moved} file(s) moved to data/not_tdrs/")
    print(f"  {len(tdr_files)} TDR document(s) remain in data/")


if __name__ == "__main__":
    auto    = "--yes" in sys.argv or "-y" in sys.argv
    dry     = "--dry" in sys.argv
    thresh  = DEFAULT_THRESH
    if "--thresh" in sys.argv:
        idx = sys.argv.index("--thresh")
        try:
            thresh = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("ERROR: --thresh requires an integer value")
            sys.exit(1)
    main(auto_yes=auto, dry_run=dry, threshold=thresh)
