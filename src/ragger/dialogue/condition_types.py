"""Core types and shared regex fragments for condition parsing.

The ``Atom`` dataclass represents a single parsed predicate. The
``FrameRule`` type bundles a regex pattern with a builder function that
produces an ``Atom`` from a match.

Each ``frames_*.py`` module exports a ``RULES`` list of ``FrameRule``
objects. The ``condition_frames/__init__.py`` assembles them in explicit
match order — no import-order magic, no priority numbers.

Shared regex fragments (``NEG``, ``COUNT``, ``ITEM_NOUN``, etc.) are
defined here so every frame file uses the same vocabulary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ragger.enums import SKILL_LABELS


# ---------------------------------------------------------------------------
# Atom — the output of a successful frame match
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Atom:
    """A single parsed condition predicate.

    ``frame`` is the frame name (e.g. ``"has_item"``, ``"quest_state"``).
    ``args`` is a sorted tuple of ``(key, value)`` pairs holding the
    frame-specific arguments.
    """
    frame: str
    args: tuple[tuple[str, object], ...]

    def __str__(self) -> str:
        body = ", ".join(f"{k}={v}" for k, v in self.args)
        return f"{self.frame}({body})"

    def get(self, key: str, default: object = None) -> object:
        """Look up an argument by key."""
        for k, v in self.args:
            if k == key:
                return v
        return default


def make_atom(frame: str, **kwargs: object) -> Atom:
    """Convenience constructor — sorts kwargs into Atom.args."""
    return Atom(frame, tuple(sorted(kwargs.items())))


# ---------------------------------------------------------------------------
# FrameRule — a (name, compiled pattern, builder) triple
# ---------------------------------------------------------------------------

#: Builder signature: takes a regex Match, returns an Atom.
AtomBuilder = Callable[[re.Match[str]], Atom]


@dataclass(frozen=True)
class FrameRule:
    """One frame-matching rule.

    ``pre_strip`` rules are tried against the raw normalized text
    (with leading ``if``/``when`` intact). Post-strip rules (the
    default) are tried after subject removal.
    """
    name: str
    pattern: re.Pattern[str]
    builder: AtomBuilder
    pre_strip: bool = False


def rule(name: str, pattern: str, builder: AtomBuilder) -> FrameRule:
    """Create a post-strip frame rule (tried after subject removal)."""
    return FrameRule(name, re.compile(pattern), builder)


def pre_rule(name: str, pattern: str, builder: AtomBuilder) -> FrameRule:
    """Create a pre-strip frame rule (tried against raw normalized text)."""
    return FrameRule(name, re.compile(pattern), builder, pre_strip=True)


# ---------------------------------------------------------------------------
# Shared regex fragments
# ---------------------------------------------------------------------------

#: Optional negation prefix (captures into ``neg`` group).
NEG = r"(?P<neg>does not |do not |is not |are not |has not |have not |did not |not )?"

#: Numeric or word count (captures into ``count`` group).
COUNT = r"(?P<count>\d{1,3}(?:,\d{3})+|\d+|a|an|the|one|two|three|four|five|six|seven|eight|nine|ten)"

#: Verb forms for item possession.
HAS_VERB = (
    r"(?:does have|do have|have|has|owns|own|carries|carry"
    r"|carrying|brings|bring|holds|hold|holding)"
)

#: An "item-like" noun — typed entity slot or generic noun phrase.
ITEM_NOUN = (
    r"(?P<item>"
    r"(?:(?:premade|correct|required|right|wrong|another|any|"
    r"unclaimed|valid|proper|ground|full|broken|lost|sixth|"
    r"chosen|selected|above|previous|cleaned|other|lockbox|"
    r"first|second|third|fourth|all|some|new|old|"
    r"desiccated|halloween|halloween-themed)\s+){0,3}"
    r"(?:\{item\}|\{equipment\}"
    r"|item|items|materials|requirements|key|keys"
    r"|note|gift|answer|password|object|thing|finds|talisman|strand"
    r"|equipment|decorations|note|outfit|components|payment|gift)"
    r"(?:\([a-z]+\))?"
    r")"
)

#: Non-capturing version of ITEM_NOUN (for second slot in "both X and Y").
ITEM_NOUN_NC = ITEM_NOUN.replace("(?P<item>", "(?:")

#: Container qualifier (inventory/bank/possession).
CONTAINER = r"(?:the player's |their |the )?(?P<qual>inventory|bank|possession)"

#: Currency comparison prefix.
CUR_CMP = r"(?:at least |at most |more than |enough |exactly )?"

#: Currency count (digits).
CUR_COUNT = r"(?P<count>\d{1,3}(?:,\d{3})+|\d+)"


# ---------------------------------------------------------------------------
# Number word lookup
# ---------------------------------------------------------------------------

NUMBER_WORDS: dict[str, int] = {
    "a": 1, "an": 1, "the": 1, "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10,
}


def parse_count(token: str | None) -> int:
    """Convert a count token to an integer (defaults to 1)."""
    if token is None:
        return 1
    cleaned = token.replace(",", "")
    if cleaned.isdigit():
        return int(cleaned)
    return NUMBER_WORDS.get(token.lower(), 1)


# ---------------------------------------------------------------------------
# Skill names — derived from the Skill enum
# ---------------------------------------------------------------------------

#: Lowercase skill names plus common aliases.
SKILL_NAMES: set[str] = {label.lower() for label in SKILL_LABELS.values()}
SKILL_NAMES |= {"defense", "runecrafting"}  # common aliases

#: Longest-match-first regex for skill names.
SKILL_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(SKILL_NAMES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
