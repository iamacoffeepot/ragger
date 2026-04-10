"""Normalization pipeline for dialogue condition text.

Transforms raw wiki condition text into a canonical form suitable for
frame matching. The pipeline:

1. Typed wiki links → entity-type slots (``{item}``, ``{npc}``, etc.)
2. Lowercase + contraction expansion + second-person normalization
3. Currency names → ``{currency}`` (before entity AC to win priority)
4. Aho-Corasick entity matching → entity-type slots
5. Skill names → ``{skill}``
6. Whitespace cleanup

Also provides ``strip_subject``, ``strip_fillers``, and
``split_compound`` for the parser to use after normalization.
"""
from __future__ import annotations

import re
import sqlite3

import ahocorasick

from ragger.dialogue.condition_types import SKILL_PATTERN

# ---------------------------------------------------------------------------
# Link patterns
# ---------------------------------------------------------------------------

ENTITY_LINK_PATTERN = re.compile(
    r"\[[^\]]+\]\((item|quest|npc|monster|location|equipment|shop|activity):"
    r"(?:[^()]+|\([^)]*\))*\)"
)
WIKI_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(wiki:(?:[^()]+|\([^)]*\))*\)")

# ---------------------------------------------------------------------------
# Contraction expansion
# ---------------------------------------------------------------------------

CONTRACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdoesn't\b", re.IGNORECASE), "does not"),
    (re.compile(r"\bdon't\b", re.IGNORECASE), "do not"),
    (re.compile(r"\bdidn't\b", re.IGNORECASE), "did not"),
    (re.compile(r"\bhasn't\b", re.IGNORECASE), "has not"),
    (re.compile(r"\bhaven't\b", re.IGNORECASE), "have not"),
    (re.compile(r"\bisn't\b", re.IGNORECASE), "is not"),
    (re.compile(r"\baren't\b", re.IGNORECASE), "are not"),
    (re.compile(r"\bwon't\b", re.IGNORECASE), "will not"),
    (re.compile(r"\bcan't\b", re.IGNORECASE), "cannot"),
]

# ---------------------------------------------------------------------------
# Second-person → third-person normalization
# ---------------------------------------------------------------------------

SECOND_PERSON: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\byou're\b", re.IGNORECASE), "the player is"),
    (re.compile(r"\byou've\b", re.IGNORECASE), "the player has"),
    (re.compile(r"\byour\b", re.IGNORECASE), "the player's"),
    (re.compile(r"\byou\b", re.IGNORECASE), "the player"),
]

# ---------------------------------------------------------------------------
# Filler words stripped before frame matching
# ---------------------------------------------------------------------------

FILLER_PATTERN = re.compile(
    r"\b(?:still|already|now|yet|previously|once|just|ever|also|finally|then|currently)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Subject stripping
# ---------------------------------------------------------------------------

SUBJECT_PREFIX_PATTERN = re.compile(
    r"^(?:if|when|while|whenever)?\s*"
    r"(?:the\s+)?(?:player|you|they)(?:'s|'re)?\s+"
)
WITHOUT_PREFIX_PATTERN = re.compile(r"^without\s+")
WITH_PREFIX_PATTERN = re.compile(r"^with\s+(?:a\s+|an\s+|the\s+)?")
LEADING_IF_PATTERN = re.compile(r"^(?:if|when|while|whenever)\s+")

#: Detect whether a clause has its own subject (for compound inheritance).
HAS_OWN_SUBJECT = re.compile(
    r"^(?:if\s+|when\s+|while\s+|whenever\s+)?"
    r"(?:the\s+)?(?:player|you|they|\{npc\}|\{monster\})\b"
)

# ---------------------------------------------------------------------------
# Entity stoplist
# ---------------------------------------------------------------------------

ENTITY_STOPLIST: frozenset[str] = frozenset({
    # Pronouns / player references
    "player", "the player", "player character", "you", "me", "we",
    "they", "them", "he", "she", "it", "us", "myself", "yourself",
    "themselves", "i",
    # English function words that are wiki redirects
    "below", "while", "above", "after", "before", "between",
    "beyond", "within", "under", "until", "since", "about",
    "next", "another", "this", "that", "with", "from", "your",
    "have", "will", "what", "been", "were", "said", "each",
    "make", "like", "just", "over", "such", "take", "than",
    "some", "well", "also", "back", "then", "good", "look",
    "come", "could", "made", "find", "here", "know", "want",
    "give", "most", "only", "tell", "very", "when", "much",
    "need", "long", "time", "help", "left", "right",
    "home", "keep", "last", "name", "turn", "move",
    "live", "work", "read", "lost", "part", "talk", "sure",
    "down", "gone", "done", "rest",
})

MIN_ENTITY_LENGTH = 4

# ---------------------------------------------------------------------------
# Aho-Corasick automaton
# ---------------------------------------------------------------------------

def build_entity_automaton(
    conn: sqlite3.Connection,
) -> tuple[ahocorasick.Automaton, dict[str, str]]:
    """Build an Aho-Corasick automaton for entity normalization.

    Returns ``(automaton, type_map)`` where *type_map* maps lowercase
    entity text to its entity type string (``"item"``, ``"npc"``, etc.).
    First type seen wins for names shared across tables.
    """
    sources = [
        ("SELECT name FROM items WHERE name IS NOT NULL", "item"),
        ("SELECT alias FROM item_aliases", "item"),
        ("SELECT name FROM equipment WHERE name IS NOT NULL", "equipment"),
        ("SELECT alias FROM equipment_aliases", "equipment"),
        ("SELECT name FROM npcs WHERE name IS NOT NULL", "npc"),
        ("SELECT alias FROM npc_aliases", "npc"),
        ("SELECT name FROM monsters WHERE name IS NOT NULL", "monster"),
        ("SELECT alias FROM monster_aliases", "monster"),
        ("SELECT name FROM quests WHERE name IS NOT NULL", "quest"),
        ("SELECT alias FROM quest_aliases", "quest"),
        ("SELECT name FROM locations WHERE name IS NOT NULL", "location"),
        ("SELECT alias FROM location_aliases", "location"),
    ]
    type_map: dict[str, str] = {}
    auto = ahocorasick.Automaton()

    for query, kind in sources:
        try:
            for (name,) in conn.execute(query).fetchall():
                if not name or len(name) < MIN_ENTITY_LENGTH:
                    continue
                key = name.lower()
                if key in ENTITY_STOPLIST:
                    continue
                if key not in type_map:
                    type_map[key] = kind
                    auto.add_word(key, key)
        except Exception:
            pass  # alias tables may not exist yet

    auto.make_automaton()
    return auto, type_map


def _is_word_boundary(text: str, start: int, end: int) -> bool:
    if start > 0 and text[start - 1].isalnum():
        return False
    if end < len(text) and text[end].isalnum():
        return False
    return True


def _replace_entities_ac(
    text: str,
    auto: ahocorasick.Automaton,
    type_map: dict[str, str],
) -> str:
    """Replace entity mentions using the AC automaton (longest-match-wins)."""
    lower = text.lower()
    matches: list[tuple[int, int, str]] = []
    for end_idx, key in auto.iter(lower):
        start_idx = end_idx - len(key) + 1
        if _is_word_boundary(lower, start_idx, end_idx + 1):
            matches.append((start_idx, end_idx + 1, type_map[key]))

    if not matches:
        return text

    matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))

    selected: list[tuple[int, int, str]] = []
    last_end = 0
    for start, end, etype in matches:
        if start >= last_end:
            selected.append((start, end, etype))
            last_end = end

    for start, end, etype in reversed(selected):
        text = text[:start] + "{" + etype + "}" + text[end:]

    return text


# ---------------------------------------------------------------------------
# Currency pattern
# ---------------------------------------------------------------------------

def build_currency_pattern(conn: sqlite3.Connection) -> re.Pattern[str] | None:
    """Build a longest-match-first regex over currency names."""
    names: list[str] = []
    for table in ("physical_currencies", "virtual_currencies"):
        try:
            for (name,) in conn.execute(f"SELECT name FROM {table}").fetchall():
                if name:
                    names.append(name)
        except sqlite3.OperationalError:
            pass
    if not names:
        return None
    names.sort(key=len, reverse=True)
    alternation = "|".join(re.escape(name) for name in names)
    return re.compile(r"\b(" + alternation + r")\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Main normalize function
# ---------------------------------------------------------------------------

def normalize(
    text: str,
    auto: ahocorasick.Automaton,
    type_map: dict[str, str],
    currency_pattern: re.Pattern[str] | None = None,
) -> str:
    """Normalize condition text for frame matching.

    Order matters — each step expects the output shape of the previous.
    """
    text = ENTITY_LINK_PATTERN.sub(lambda m: "{" + m.group(1) + "}", text)
    text = WIKI_LINK_PATTERN.sub("{wiki}", text)
    text = text.lower()
    for pattern, replacement in CONTRACTIONS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in SECOND_PERSON:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\bthey player\b", "the player", text)
    if currency_pattern is not None:
        text = currency_pattern.sub("{currency}", text)
    text = _replace_entities_ac(text, auto, type_map)
    text = SKILL_PATTERN.sub("{skill}", text)
    text = text.strip().rstrip(":.! ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


# ---------------------------------------------------------------------------
# Text transforms used by the parser
# ---------------------------------------------------------------------------

def strip_subject(text: str) -> str:
    """Remove the subject prefix (``the player``, ``if the player``, etc.)."""
    new = SUBJECT_PREFIX_PATTERN.sub("", text)
    if new != text:
        return new
    new = WITHOUT_PREFIX_PATTERN.sub("", text)
    if new != text:
        return "does not have " + new
    new = WITH_PREFIX_PATTERN.sub("", text)
    if new != text:
        return new
    return LEADING_IF_PATTERN.sub("", text)


def strip_fillers(text: str) -> str:
    """Remove filler/temporal words that don't affect frame matching."""
    text = FILLER_PATTERN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def split_compound(text: str) -> list[str]:
    """Split a condition on top-level conjunctions.

    Respects numeric quantifiers (``3 or more``, ``5 or fewer``).
    """
    parts = re.split(
        r"\s*,?\s+(?:and|but|or(?!\s+(?:more|fewer|above|higher|less|under|equal)))\s+",
        text,
    )
    return [p.strip() for p in parts if p.strip()]
