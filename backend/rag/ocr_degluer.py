"""Deterministic de-gluing of OCR'd French/English text.

RapidOCR (pymupdf4llm's integrated OCR) frequently joins adjacent words
("conditionsgenerales", "Termesdereferencepour"). This module splits such
tokens back into words with a frequency-dictionary segmentation.

Safety model — a token is ONLY modified when:
  1. it is at least MIN_TOKEN_LEN characters of pure letters/apostrophes,
  2. it is NOT itself a known word,
  3. it decomposes COMPLETELY into known words (French + English wordfreq
     lists + domain words harvested from the corpus's native documents).
Anything else (project codes, proper nouns, acronyms) passes through
unchanged, so real content can never be corrupted. Splitting only inserts
spaces — the original characters (case, accents) are preserved verbatim.
"""

from __future__ import annotations

import re
import unicodedata

MIN_TOKEN_LEN = 12     # shorter tokens are never touched
MIN_PART_LEN  = 2      # smallest inner word allowed in a decomposition
MIN_ZIPF      = 2.7    # wordfreq frequency floor for dictionary words

# French elision prefixes that attach to the next word with an apostrophe
_ELISIONS = {"c", "d", "j", "l", "m", "n", "s", "t", "qu"}

# The ONLY 2-3 letter parts allowed inside a decomposition. A frequency
# floor is not enough: "es"/"ee" are frequent tokens, and letting them in
# splits real-but-rare inflected words ("DECENTRALISEES" → "DECENTRALISE ES").
_SHORT_WHITELIST = {
    # French function words
    "de", "du", "le", "la", "les", "des", "un", "une", "au", "aux",
    "en", "et", "ou", "ne", "se", "ce", "ces", "ses", "son", "sa",
    "sur", "par", "que", "qui", "pas", "est", "ans",
    "vos", "nos", "eux", "ils",
    # English function words
    "of", "to", "in", "on", "at", "and", "the", "for", "are", "was",
}

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’]{11,}")

_vocab: dict[str, float] | None = None
_domain_words: set[str] = set()


def _fold(s: str) -> str:
    return (unicodedata.normalize("NFD", s)
            .encode("ascii", "ignore").decode("ascii").lower())


def _build_vocab() -> dict[str, float]:
    from wordfreq import top_n_list, zipf_frequency
    vocab: dict[str, float] = {}
    for lang in ("fr", "en"):
        for w in top_n_list(lang, 60_000):
            f = _fold(w)
            if len(f) >= MIN_PART_LEN and f.isalpha():
                z = zipf_frequency(w, lang)
                if z >= MIN_ZIPF and z > vocab.get(f, 0.0):
                    vocab[f] = z
    return vocab


def get_vocab() -> dict[str, float]:
    global _vocab
    if _vocab is None:
        _vocab = _build_vocab()
    return _vocab


def add_domain_words(texts: list[str]) -> int:
    """Harvest words from natively-extracted (non-OCR) documents so domain
    vocabulary ("transfrontaliere", "budgetisation") is recognised inside
    glued OCR tokens. Words must appear at least twice to count."""
    counts: dict[str, int] = {}
    for text in texts:
        for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{4,18}", text):
            f = _fold(w)
            if f.isalpha():
                counts[f] = counts.get(f, 0) + 1
    vocab = get_vocab()
    added = 0
    for f, n in counts.items():
        if n >= 2 and f not in vocab:
            vocab[f] = MIN_ZIPF          # modest score, real words outrank it
            _domain_words.add(f)
            added += 1
    return added


def _segment(token: str) -> list[str] | None:
    """Return the token's parts if it decomposes fully into known words.

    Unigram scoring: maximise the summed word frequency (zipf) minus a flat
    per-part penalty. Frequency beats greedy length — "ExperiencedansX"
    must split as "Experience dans X" (dans: zipf 6.6), not "Experienced
    ans X" (ans: zipf 5.5) — and the per-part penalty stops fragmentation
    into many tiny words. None when no full decomposition exists."""
    vocab = get_vocab()
    folded = _fold(token)
    n = len(token)
    # dp[i] = (score, parts) for token[:i]
    dp: list[tuple[float, list[str]] | None] = [None] * (n + 1)
    dp[0] = (0.0, [])
    for i in range(n):
        if dp[i] is None:
            continue
        base_score, base_parts = dp[i]
        # option A: dictionary word token[i:j] (no apostrophe inside)
        for j in range(i + MIN_PART_LEN, n + 1):
            piece = token[i:j]
            if "'" in piece or "’" in piece:
                break
            fp = _fold(piece)
            if len(fp) >= MIN_PART_LEN and fp in vocab:
                z = vocab[fp]
                # Junk-fragment guard: 2-3 letter parts must be whitelisted
                # function words — otherwise "REPUBLIQUE" fragments into
                # "RE PUB LI QUE" and rare inflections split off their tail.
                if len(fp) <= 3 and fp not in _SHORT_WHITELIST:
                    continue
                # log-probability: zipf-9 ≈ log10 P(word) — each extra part
                # costs, so whole words beat fragment chains.
                score = base_score + (z - 9.0)
                if dp[j] is None or score > dp[j][0]:
                    dp[j] = (score, base_parts + [piece])
        # option B: elision unit "d'" / "qu'" attached to what follows
        for e_len in (1, 2):
            k = i + e_len
            if (k < n and _fold(token[i:k]) in _ELISIONS
                    and token[k] in ("'", "’")):
                score = base_score - 2.0   # priced like a frequent function word
                if dp[k + 1] is None or score > dp[k + 1][0]:
                    dp[k + 1] = (score, base_parts + [token[i:k + 1]])
    if dp[n] is None:
        return None
    parts = dp[n][1]
    return parts if len(parts) >= 2 else None


def _rejoin(parts: list[str]) -> str:
    """Spaces between words; elision units ("d'") stay glued to the next."""
    out = ""
    for p in parts:
        if out and not out.endswith(("'", "’")):
            out += " "
        out += p
    return out


def _fix_token(m: re.Match) -> str:
    token = m.group(0)
    folded = _fold(token).replace("'", "")
    if folded in get_vocab():            # already a real word — never touch
        return token
    parts = _segment(token)
    return _rejoin(parts) if parts else token


# OCR misreads the French elision "l'" as a capital i ("I'elaboration",
# glued: "MinisteredeI'Enseignement"). "I" directly followed by
# apostrophe+vowel/h never occurs in real French or English text
# ("I'm"/"I've" have consonants after the apostrophe) — safe to rewrite
# anywhere, including inside glued tokens, BEFORE segmentation so the
# segmenter sees a normal "l'" elision.
_I_ELISION_RE = re.compile(r"I(['’])(?=[aeiouhàâäéèêëîïôöûüAEIOUH])")


def deglue_text(text: str) -> str:
    """Fix OCR word-gluing in a whole document (markdown preserved:
    only letters/apostrophe runs are examined, never punctuation/pipes)."""
    text = _I_ELISION_RE.sub(r"l\1", text)
    return _TOKEN_RE.sub(_fix_token, text)
