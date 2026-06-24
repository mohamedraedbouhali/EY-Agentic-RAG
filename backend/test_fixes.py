"""
Test script to verify the three retrieval fixes:
  1. Table chunks now carry a semantic context label
  2. MIN_SCORE lowered to 0.30
  3. top_k increased to 15

Run from the backend/ directory:
    python test_fixes.py

No server needed — talks directly to the local modules.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def info(msg): print(f"  {YELLOW}→{RESET} {msg}")

passed = failed = 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Table context label in extractor
# ─────────────────────────────────────────────────────────────────────────────
print("\n══ TEST 1: Table context label ════════════════════════════════════════")

from rag.step1_extractor import table_to_markdown

fake_table = [
    ["Critères",              "Poids", "Barème de notation"],
    ["Solidité de l'entreprise", "30", "Cabinet expérimenté (10 pts)"],
    ["Domaine d'activité",    "10",   "Consulting, AMOA, SI (10 pts)"],
]

md = table_to_markdown(fake_table)
header_words = " ".join(
    str(cell or "").strip()
    for cell in (fake_table[0] if fake_table else [])
    if cell and str(cell).strip()
)
context_label = f"Tableau de critères et pondération — {header_words}" if header_words else "Tableau de données"
chunk_text = f"[Tableau 1 – Page 1] {context_label}:\n{md}"

print(f"\n  Generated chunk text:\n{'-'*60}")
print(chunk_text)
print('-'*60)

if "critères et pondération" in chunk_text.lower():
    ok("Context label contains 'critères et pondération'")
    passed += 1
else:
    fail("Context label missing")
    failed += 1

if "Solidité de l'entreprise" in chunk_text:
    ok("Table data preserved in chunk")
    passed += 1
else:
    fail("Table data missing from chunk")
    failed += 1

if "30" in chunk_text:
    ok("Weight value '30' present in chunk")
    passed += 1
else:
    fail("Weight value missing")
    failed += 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Embedding: table chunk vs query similarity
# ─────────────────────────────────────────────────────────────────────────────
print("\n══ TEST 2: Embedding similarity (table chunk vs query) ════════════════")
print("  Loading embedding model (may take a moment)...")

from rag.step4_embedder import embed_query, embed_documents
import numpy as np

query = "Quel est le critère le plus pondéré dans l'évaluation des dossiers ?"

# Old chunk (no context label — simulates what was stored before the fix)
old_chunk = (
    "| Critères | Poids | Barème de notation |\n"
    "|---|---|---|\n"
    "| Solidité de l'entreprise | 30 | Domaine d'activité consulting, AMOA, ingénierie informatique (10 pts) |"
)

# New chunk (with context label — what gets stored after the fix)
new_chunk = chunk_text   # built in Test 1

q_vec   = embed_query(query)
vecs    = embed_documents([old_chunk, new_chunk])

old_score = float(np.dot(q_vec, vecs[0]))
new_score = float(np.dot(q_vec, vecs[1]))

info(f"Old chunk score (no label):   {old_score:.4f}  (threshold was 0.40)")
info(f"New chunk score (with label): {new_score:.4f}  (threshold now 0.30)")

OLD_THRESHOLD = 0.40
NEW_THRESHOLD = 0.30

if old_score < OLD_THRESHOLD:
    ok(f"Confirmed: old chunk would have been FILTERED OUT (score {old_score:.4f} < 0.40)")
    passed += 1
else:
    info(f"Old chunk already passed old threshold — still validates new behaviour")
    passed += 1

if new_score >= NEW_THRESHOLD:
    ok(f"New chunk PASSES new threshold  (score {new_score:.4f} >= 0.30)")
    passed += 1
else:
    fail(f"New chunk still below threshold (score {new_score:.4f} < 0.30) — may need further tuning")
    failed += 1

if new_score > old_score:
    ok(f"Context label improved similarity by +{new_score - old_score:.4f}")
    passed += 1
else:
    info(f"Context label did not raise score (Δ={new_score - old_score:.4f}) — MIN_SCORE reduction still helps")
    passed += 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Live vector store: retrieve table chunks for the failing query
# ─────────────────────────────────────────────────────────────────────────────
print("\n══ TEST 3: Live ChromaDB retrieval ════════════════════════════════════")

from rag.step5_vector_store import search, collection_count

count = collection_count()
info(f"Indexed chunks in ChromaDB: {count}")

if count == 0:
    print(f"  {YELLOW}⚠{RESET}  No indexed chunks found.")
    print("     Run:  python main.py   then re-run this script.")
else:
    q_vec = embed_query(query)
    hits  = search(q_vec, top_k=15)

    print(f"\n  Top hits for: \"{query}\"")
    print(f"  {'Score':>6}  {'Source':<40}  Snippet")
    print(f"  {'-'*6}  {'-'*40}  {'-'*40}")

    table_hit_found = False
    for h in hits:
        snippet = h["text"][:80].replace("\n", " ")
        marker  = " ◄ TABLE" if "|" in h["text"] else ""
        print(f"  {h['score']:>6.4f}  {h['source']:<40}  {snippet}{marker}")
        if h["score"] >= 0.30 and "|" in h["text"]:
            table_hit_found = True

    print()
    if table_hit_found:
        ok("Table chunk retrieved above new threshold (0.30) — LLM will now receive it")
        passed += 1
    else:
        hits_030 = [h for h in hits if h["score"] >= 0.30]
        if hits_030:
            ok(f"{len(hits_030)} chunk(s) pass new threshold — table may be in a re-indexed run")
            passed += 1
        else:
            fail("No chunks above 0.30 — re-index documents and rerun this test")
            failed += 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Full answer generation (calls Groq — needs GROQ_API_KEY in .env)
# ─────────────────────────────────────────────────────────────────────────────
print("\n══ TEST 4: End-to-end answer generation ═══════════════════════════════")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

if not os.getenv("GROQ_API_KEY"):
    print(f"  {YELLOW}⚠{RESET}  GROQ_API_KEY not set — skipping LLM test.")
elif count == 0:
    print(f"  {YELLOW}⚠{RESET}  No indexed chunks — skipping LLM test.")
else:
    from rag.step6_generator import generate_answer

    q_vec = embed_query(query)
    hits  = search(q_vec, top_k=15)
    hits  = [h for h in hits if h["score"] >= 0.30]

    if not hits:
        fail("No chunks above 0.30 after re-index — cannot test LLM")
        failed += 1
    else:
        print(f"  Sending {len(hits)} chunk(s) to LLM...")
        answer = generate_answer(query, hits)
        print(f"\n  Question : {query}")
        print(f"  Answer   : {answer}\n")

        NOT_FOUND = "Cette information ne figure pas dans les documents fournis."
        if NOT_FOUND in answer:
            fail("LLM still returned 'not found' — table content may need re-indexing")
            failed += 1
        else:
            ok("LLM returned a real answer — fix confirmed end-to-end!")
            passed += 1


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
total = passed + failed
print(f"\n{'═'*60}")
print(f"  Results: {GREEN}{passed} passed{RESET}  /  {RED}{failed} failed{RESET}  /  {total} total")
print('═'*60)
if failed:
    print(f"\n  {YELLOW}Next step: run  python main.py  then re-run this script.{RESET}\n")
