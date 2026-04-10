"""Condition predicate parser.

Parses normalized dialogue condition text into structured ``Atom``
predicates. Supports compound conditions (``X and Y``) with subject
inheritance across clauses.

Usage::

    from ragger.dialogue.condition_parser import parse_condition
    from ragger.dialogue.condition_normalize import (
        build_entity_automaton, build_currency_pattern, normalize,
    )

    auto, type_map = build_entity_automaton(conn)
    currency_pat = build_currency_pattern(conn)
    text = normalize(raw_text, auto, type_map, currency_pat)
    atoms = parse_condition(text)
"""
from __future__ import annotations

from ragger.dialogue.condition_frames import ALL_RULES
from ragger.dialogue.condition_normalize import (
    HAS_OWN_SUBJECT,
    split_compound,
    strip_fillers,
    strip_subject,
)
from ragger.dialogue.condition_types import Atom, FrameRule, make_atom

# Split once at import time so the parser doesn't filter every call.
_PRE_STRIP_RULES: list[FrameRule] = [r for r in ALL_RULES if r.pre_strip]
_POST_STRIP_RULES: list[FrameRule] = [r for r in ALL_RULES if not r.pre_strip]


def parse_atom(text: str, *, allow_unknown: bool = False) -> Atom | None:
    """Try to match *text* against all registered frame rules.

    Returns the first matching ``Atom``, or ``None`` if nothing matched
    (unless *allow_unknown* is True, in which case an ``unknown`` atom
    is returned with the normalized text preserved).
    """
    pre_stripped = strip_fillers(text)
    for r in _PRE_STRIP_RULES:
        m = r.pattern.match(pre_stripped)
        if m:
            return r.builder(m)

    body = strip_subject(text)
    body = strip_fillers(body)
    for r in _POST_STRIP_RULES:
        m = r.pattern.match(body)
        if m:
            return r.builder(m)

    if allow_unknown:
        return make_atom("unknown", text=body)
    return None


def parse_condition(
    text: str,
    *,
    allow_unknown: bool = False,
) -> list[Atom]:
    """Parse a (possibly compound) condition into one or more atoms.

    Strategy:

    1. Try to parse the whole text as a single atom.
    2. If that fails, split on top-level conjunctions, inherit the
       subject prefix from the first clause to subsequent clauses, and
       parse each clause independently.
    3. Lenient mode: if at least one clause parses, return whatever
       atoms succeeded.
    4. If *allow_unknown* is True and nothing matched, return a single
       ``unknown`` atom preserving the normalized text.
    """
    atom = parse_atom(text)
    if atom is not None:
        return [atom]

    parts = split_compound(text)
    if len(parts) <= 1:
        if allow_unknown:
            return [parse_atom(text, allow_unknown=True)]
        return []

    inherit = "the player " if HAS_OWN_SUBJECT.match(parts[0]) else None

    atoms: list[Atom] = []
    for i, part in enumerate(parts):
        if i > 0 and inherit and not HAS_OWN_SUBJECT.match(part):
            part = inherit + part
        atom = parse_atom(part)
        if atom is not None:
            atoms.append(atom)

    if not atoms and allow_unknown:
        return [parse_atom(text, allow_unknown=True)]
    return atoms
