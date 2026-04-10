"""Refine generic ``wiki:`` markdown links to typed entity prefixes.

After ``normalize_dialogue_wikitext`` runs, every wiki link is shaped
``[display](wiki:Page_Slug)``. The ``wiki:`` prefix is a fallback —
parser-time we don't know whether ``Page_Slug`` is an item, NPC, quest,
or something else. This module looks each slug up against the entity
tables and rewrites the prefix accordingly:

- ``[Cook](wiki:Cook)`` → ``[Cook](npc:Cook)``
- ``[Hard hat](wiki:Hard_hat)`` → ``[Hard hat](item:Hard_hat)``
- ``[Cook's Assistant](wiki:Cook's_Assistant)`` → ``[Cook's Assistant](quest:Cook's_Assistant)``

Anything not found in any entity table stays as ``wiki:`` so consumers
can fall back to a generic wiki page resolver.

The module is pure: ``build_entity_lookup`` builds the dict once,
``refine_entity_links`` is a string-in/string-out transform. The
pipeline script calls them in turn during a one-pass UPDATE over
``dialogue_nodes``.
"""
from __future__ import annotations

import re
import sqlite3

# Markdown wiki link: [display](wiki:slug) where slug may include #anchor
# and parenthetical variant suffixes like Clue_scroll_(easy).
# The slug group uses (?:[^()]+|\([^)]*\))* to allow balanced inner parens.
_WIKI_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(wiki:((?:[^()]+|\([^)]*\))*)\)")

# Priority order for resolving name conflicts. Lower-priority sources are
# loaded first so higher-priority sources overwrite their entries in the
# dict — the final lookup yields the most specific type for each name.
_ENTITY_SOURCES: list[tuple[str, str]] = [
    ("SELECT id, name FROM equipment", "equipment"),
    ("SELECT id, name FROM items", "item"),
    ("SELECT id, name FROM locations", "location"),
    ("SELECT id, name FROM shops", "shop"),
    ("SELECT id, name FROM activities", "activity"),
    ("SELECT id, name FROM monsters", "monster"),
    ("SELECT id, name FROM npcs", "npc"),
    ("SELECT id, name FROM quests", "quest"),
]

# Alias tables loaded at the SAME priority as their parent entity type.
# Loaded before canonical sources so canonical names win on conflicts.
_ALIAS_SOURCES: list[tuple[str, str]] = [
    # (alias_query returning (alias, entity_id), entity_type)
    ("SELECT alias, item_id FROM item_aliases", "item"),
    ("SELECT ea.alias, MIN(e.id) FROM equipment_aliases ea JOIN equipment e ON e.name = ea.equipment_name GROUP BY ea.alias", "equipment"),
    ("SELECT na.alias, MIN(n.id) FROM npc_aliases na JOIN npcs n ON n.name = na.npc_name GROUP BY na.alias", "npc"),
    ("SELECT ma.alias, MIN(m.id) FROM monster_aliases ma JOIN monsters m ON m.name = ma.monster_name GROUP BY ma.alias", "monster"),
    ("SELECT alias, quest_id FROM quest_aliases", "quest"),
    ("SELECT alias, location_id FROM location_aliases", "location"),
]


def build_entity_lookup(conn: sqlite3.Connection) -> dict[str, tuple[str, int]]:
    """Build ``{lowercase_name: (entity_type, entity_id)}`` from entity tables.

    Loads both canonical names and wiki-redirect aliases. Sources are
    loaded in priority order (lowest first), so a name that appears in
    multiple tables ends up classified as the most specific type —
    quests beat npcs beat monsters beat activities beat shops beat
    locations beat items beat equipment. Aliases are loaded before
    canonical names so canonical names always win on conflicts.
    """
    lookup: dict[str, tuple[str, int]] = {}
    # Load aliases first (lower priority than canonical names)
    for query, entity_type in _ALIAS_SOURCES:
        try:
            for alias, entity_id in conn.execute(query).fetchall():
                if not alias:
                    continue
                lookup[alias.lower()] = (entity_type, entity_id)
        except Exception:
            pass  # alias tables may not exist yet
    # Load canonical names (overwrite aliases on conflict)
    for query, entity_type in _ENTITY_SOURCES:
        for entity_id, name in conn.execute(query).fetchall():
            if not name:
                continue
            lookup[name.lower()] = (entity_type, entity_id)
    return lookup


def refine_entity_links(text: str, lookup: dict[str, tuple[str, int]]) -> str:
    """Rewrite ``wiki:`` markdown links to typed entity prefixes.

    For each ``[display](wiki:Page_Slug)`` match, look up
    ``Page Slug`` (un-slugged, lowercased, anchor stripped) in the
    lookup. If found, replace ``wiki:`` with the matching entity type;
    otherwise leave the link as-is.

    Idempotent: typed links don't match the ``wiki:`` pattern and pass
    through unchanged.
    """
    if not text:
        return text

    def replace(match: re.Match[str]) -> str:
        display = match.group(1)
        slug = match.group(2)
        # Strip anchor for lookup; preserve it in the output URL.
        slug_no_anchor = slug.split("#", 1)[0]
        name = slug_no_anchor.replace("_", " ").lower()
        result = lookup.get(name)
        if result is None:
            return match.group(0)
        entity_type, _ = result
        return f"[{display}]({entity_type}:{slug})"

    return _WIKI_LINK_PATTERN.sub(replace, text)
