"""Fetch NPC dialogue trees from Transcript: pages on the OSRS wiki.

Pulls from transcript subcategories (Quest transcript, NPC dialogue, etc.)
in namespace 120. Parses the *-indented wikitext into a tree stored in
dialogue_pages and dialogue_nodes. Action nodes that reference other nodes
(``-> above``, ``-> below``, ``-> other``, etc.) get their target resolved
into the ``continue_target_id`` column on the action node.
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.dialogue.dialogue_wikitext import normalize_dialogue_wikitext
from ragger.enums import DialogueNodeType
from ragger.wiki import (
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    record_attributions_batch,
    strip_wiki_links,
)

# Transcript subcategories → default page_type (overridden by {{Transcript|type}})
SUBCATEGORIES: list[str] = [
    "Quest transcript",
    "NPC dialogue",
    "Event transcript",
    "Miniquest transcript",
    "Item transcript",
    "Pet dialogue",
    "Scenery transcript",
    "Incomplete transcripts",
]

TRANSCRIPT_NS = 120

# '''Speaker:''' text
SPEAKER_RE = re.compile(r"^'''(.+?):'''\s*(.*)")

# {{template|...}} at the start of a line (after stripping *)
TEMPLATE_RE = re.compile(r"^\{\{(\w+)\|?(.*)\}\}$", re.DOTALL)

# Internal parser markers for quest=No / event=No (never stored in DB)
_SKIP_QUEST = "_skip_quest"
_SKIP_EVENT = "_skip_event"

NODE_TYPE_MAP = {
    "topt": DialogueNodeType.OPTION,
    "top": DialogueNodeType.OPTION,
    "tcond": DialogueNodeType.CONDITION,
    "tact": DialogueNodeType.ACTION,
    "tbox": DialogueNodeType.BOX,
    "tselect": DialogueNodeType.SELECT,
    "qact": DialogueNodeType.QUEST_ACTION,
}


def parse_transcript_type(wikitext: str) -> str | None:
    """Extract page type from {{Transcript|type}} or {{transcript|type}}."""
    block = extract_template(wikitext, "Transcript")
    if not block:
        block = extract_template(wikitext, "transcript")
    if not block:
        return None
    # block is like "|Quest" or "|npc"
    parts = block.strip().lstrip("|").split("|")
    if parts and parts[0]:
        return parts[0].strip().lower()
    return None


def _balanced_split(text: str, delimiter: str) -> list[str]:
    """Split ``text`` on ``delimiter``, respecting wiki nesting.

    Pipes (or other delimiters) inside ``{{...}}`` template groups or
    ``[[...]]`` link groups are preserved — only top-level delimiters
    cause a split. Without this, nested templates like
    ``{{tbox|20{{Colour|#hex|22}}}}`` get shredded into bogus param
    fragments by a naive ``str.split``.
    """
    parts: list[str] = []
    start = 0
    brace_depth = 0
    bracket_depth = 0
    i = 0
    n = len(text)
    while i < n:
        if i + 1 < n:
            pair = text[i:i + 2]
            if pair == "{{":
                brace_depth += 1
                i += 2
                continue
            if pair == "}}":
                brace_depth -= 1
                i += 2
                continue
            if pair == "[[":
                bracket_depth += 1
                i += 2
                continue
            if pair == "]]":
                bracket_depth -= 1
                i += 2
                continue
        if text[i] == delimiter and brace_depth == 0 and bracket_depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def _split_template_params(params_str: str) -> tuple[dict[str, str], list[str]]:
    """Split template params into named and positional.

    Splits on top-level ``|`` only — pipes inside nested ``{{...}}``
    templates or ``[[...]]`` wiki links are preserved so the contained
    payload reaches the normalizer intact.
    """
    named: dict[str, str] = {}
    positional: list[str] = []
    for p in _balanced_split(params_str, "|"):
        p = p.strip()
        if "=" in p:
            key, _, val = p.partition("=")
            named[key.strip().lower()] = val.strip()
        else:
            positional.append(p)
    return named, positional


def _check_skip_override(named: dict[str, str]) -> str | None:
    """Check for quest=No / event=No skip overrides.

    Returns a sentinel type string or None if no skip applies.
    """
    if named.get("quest", "").lower() == "no":
        return _SKIP_QUEST
    if named.get("event", "").lower() == "no":
        return _SKIP_EVENT
    return None


def extract_template_text(template_name: str, params_str: str) -> tuple[str, str, str]:
    """Extract human-readable text, type override, and visibility predicate.

    Returns ``(text, node_type_override, predicate)``.

    - ``node_type_override`` is non-empty when the template carries a named
      parameter that changes the semantics (e.g. ``{{topt|quest=No}}`` →
      skip_quest).
    - ``predicate`` is non-empty when the template carries ``cond=...``,
      which expresses a visibility predicate on the node (most commonly on
      ``{{topt|cond=...|Option text}}``).
    """
    if not params_str:
        return "", "", ""

    named, positional = _split_template_params(params_str)
    skip = _check_skip_override(named)
    text_first = normalize_dialogue_wikitext(positional[0].strip()) if positional else ""
    if skip is not None:
        return text_first, skip, ""

    predicate = normalize_dialogue_wikitext(named["cond"]) if "cond" in named else ""

    if template_name == "tbox":
        text_parts = [p.strip() for p in positional if p.strip()]
        raw = text_parts[-1] if text_parts else params_str
        return normalize_dialogue_wikitext(raw), "", predicate

    if template_name == "tact":
        raw = positional[0].strip() if positional else params_str.strip()
        return normalize_dialogue_wikitext(raw), "", predicate

    # topt/top, tcond, tselect, qact — first positional param
    first = positional[0].strip() if positional else params_str.split("|")[0].strip()
    return normalize_dialogue_wikitext(first), "", predicate


def parse_line_content(content: str) -> dict:
    """Parse the content of a single * line into node_type, speaker, text, predicate."""
    content = content.strip()

    # Check for known templates
    m = TEMPLATE_RE.match(content)
    if m:
        tname = m.group(1).lower()
        if tname in NODE_TYPE_MAP:
            text, type_override, predicate = extract_template_text(tname, m.group(2))
            node_type = type_override if type_override else NODE_TYPE_MAP[tname]
            return {"node_type": node_type, "speaker": None, "text": text, "predicate": predicate}

    # Speaker line: '''Name:''' text
    m = SPEAKER_RE.match(content)
    if m:
        speaker = strip_wiki_links(m.group(1).strip())
        text = normalize_dialogue_wikitext(m.group(2).strip())
        return {"node_type": DialogueNodeType.LINE, "speaker": speaker, "text": text, "predicate": ""}

    # Fallback: plain text node
    return {"node_type": DialogueNodeType.LINE, "speaker": None, "text": normalize_dialogue_wikitext(content), "predicate": ""}


def parse_section_depth(line: str) -> tuple[int, str] | None:
    """Parse a section heading. Returns (heading_level, title) or None."""
    stripped = line.strip()
    if not stripped.startswith("=="):
        return None
    # Count leading = signs
    level = 0
    for ch in stripped:
        if ch == "=":
            level += 1
        else:
            break
    title = stripped.strip("= ")
    # == is level 2 in wikitext, normalize to 0-based
    return (level - 2, title)


def parse_dialogue_tree(wikitext: str, skip_non_quest: bool = False) -> tuple[str | None, list[dict]]:
    """Parse transcript wikitext into (page_type, nodes).

    Each node dict has: parent_idx (index into the list or None),
    sort_order, depth, node_type, speaker, text, section.

    When *skip_non_quest* is True, ``quest=No`` and ``event=No`` option
    branches (and all their children) are pruned from the output.
    """
    page_type = parse_transcript_type(wikitext)
    nodes: list[dict] = []
    # depth → index of last node at that depth
    parent_at: dict[int, int] = {}
    sort_order = 0
    # Track current section heading path
    section_stack: list[str] = []
    # When set, skip all lines deeper than this depth (pruning a subtree)
    skip_depth: int | None = None

    for line in wikitext.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Section headings
        heading = parse_section_depth(stripped)
        if heading is not None:
            level, title = heading
            # Trim section stack to this level and push
            section_stack = section_stack[:level]
            section_stack.append(title)
            # Reset parent tracking for * lines under new section
            parent_at.clear()
            skip_depth = None
            continue

        # Dialogue lines (must start with *)
        if not stripped.startswith("*"):
            continue

        # Count * depth
        depth = 0
        for ch in stripped:
            if ch == "*":
                depth += 1
            else:
                break

        # If pruning a subtree, skip until we return to the same or shallower depth
        if skip_depth is not None:
            if depth > skip_depth:
                continue
            skip_depth = None

        content = stripped[depth:].strip()
        if not content:
            continue

        node = parse_line_content(content)

        # quest=No / event=No branches
        if node["node_type"] in (_SKIP_QUEST, _SKIP_EVENT):
            if skip_non_quest:
                skip_depth = depth
                continue
            # Normal ingestion: store as a regular option
            node["node_type"] = DialogueNodeType.OPTION

        # Find parent: last node at depth - 1
        parent_idx = parent_at.get(depth - 1) if depth > 1 else None

        section = "/".join(section_stack) if section_stack else None

        nodes.append({
            "parent_idx": parent_idx,
            "sort_order": sort_order,
            "depth": depth,
            "node_type": node["node_type"],
            "speaker": node["speaker"],
            "text": node["text"],
            "section": section,
        })

        idx = len(nodes) - 1
        parent_at[depth] = idx
        # Clear deeper entries (new branch at this depth invalidates children)
        for d in [k for k in parent_at if k > depth]:
            del parent_at[d]

        sort_order += 1

        # If this node carried a cond= visibility predicate, synthesize a
        # child CONDITION node so the predicate is preserved in the tree.
        # The synthetic child has no children of its own — downstream code
        # treats an OPTION whose first child is a childless CONDITION as
        # having a visibility predicate.
        predicate = node.get("predicate") or ""
        if predicate:
            child_depth = depth + 1
            nodes.append({
                "parent_idx": idx,
                "sort_order": sort_order,
                "depth": child_depth,
                "node_type": DialogueNodeType.CONDITION,
                "speaker": None,
                "text": predicate,
                "section": section,
            })
            parent_at[child_depth] = len(nodes) - 1
            for d in [k for k in parent_at if k > child_depth]:
                del parent_at[d]
            sort_order += 1

    return page_type, nodes


def insert_dialogue(conn, page_title: str, page_type: str | None, nodes: list[dict]) -> int:
    """Insert a dialogue page, nodes, and resolve continue targets. Returns node count."""
    cur = conn.execute(
        "INSERT INTO dialogue_pages (title, page_type) VALUES (?, ?)",
        (page_title, page_type),
    )
    page_id = cur.lastrowid

    if not nodes:
        return 0

    # Insert nodes, tracking index → row ID for parent references
    idx_to_id: dict[int, int] = {}

    for i, node in enumerate(nodes):
        parent_id = idx_to_id.get(node["parent_idx"]) if node["parent_idx"] is not None else None
        cur = conn.execute(
            """INSERT INTO dialogue_nodes
               (page_id, parent_id, sort_order, depth, node_type, speaker, text, section)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                page_id,
                parent_id,
                node["sort_order"],
                node["depth"],
                node["node_type"].value if isinstance(node["node_type"], DialogueNodeType) else node["node_type"],
                node["speaker"],
                node["text"],
                node["section"],
            ),
        )
        idx_to_id[i] = cur.lastrowid

    # Action node index -> resolved target node index. Populated by the
    # reference-resolution passes below; flushed into continue_target_id
    # on the action nodes at the end.
    continue_targets: list[tuple[int, int]] = []

    # Group nodes by parent to find siblings
    children_by_parent: dict[int | None, list[int]] = {}
    for i, node in enumerate(nodes):
        children_by_parent.setdefault(node["parent_idx"], []).append(i)

    def _is_alias_action(idx: int) -> bool:
        """True if this action is the sole child of an option (making it an alias)."""
        node = nodes[idx]
        if node["node_type"] != DialogueNodeType.ACTION:
            return False
        parent_idx = node["parent_idx"]
        if parent_idx is None:
            return False
        if nodes[parent_idx]["node_type"] != DialogueNodeType.OPTION:
            return False
        return children_by_parent.get(parent_idx, []) == [idx]

    def _advance_past_echo(action_idx: int, matched_idx: int) -> int:
        """If the action's preceding sibling already says the matched text, advance to the next sibling."""
        action = nodes[action_idx]
        parent_idx = action["parent_idx"]
        if parent_idx is None:
            return matched_idx
        siblings = children_by_parent.get(parent_idx, [])
        pos = siblings.index(action_idx)
        if pos == 0:
            return matched_idx
        prev_sibling = nodes[siblings[pos - 1]]
        if prev_sibling["text"] and prev_sibling["text"] == nodes[matched_idx].get("text"):
            match_parent = nodes[matched_idx]["parent_idx"]
            match_siblings = children_by_parent.get(match_parent, [])
            match_pos = match_siblings.index(matched_idx)
            if match_pos + 1 < len(match_siblings):
                return match_siblings[match_pos + 1]
        return matched_idx

    def _resolve_target(action_idx: int, matched_idx: int) -> int:
        """Resolve the edge target: advance past echoed text, promote to select unless alias."""
        target = _advance_past_echo(action_idx, matched_idx)
        if _is_alias_action(action_idx):
            return target
        return _promote_to_select(target)

    def _promote_to_select(idx: int) -> int:
        """If the target is an option that belongs to a select group, return the select.

        Checks both parent (select > option) and preceding sibling (select, option, option)
        since the wiki formats both ways.
        """
        node = nodes[idx]
        if node["node_type"] != DialogueNodeType.OPTION:
            return idx
        # Check parent
        if node["parent_idx"] is not None:
            parent = nodes[node["parent_idx"]]
            if parent["node_type"] == DialogueNodeType.SELECT:
                return node["parent_idx"]
        # Check preceding siblings for a select at the same level
        siblings = children_by_parent.get(node["parent_idx"], [])
        pos = siblings.index(idx)
        for k in range(pos - 1, -1, -1):
            sib = nodes[siblings[k]]
            if sib["node_type"] == DialogueNodeType.SELECT:
                return siblings[k]
            if sib["node_type"] != DialogueNodeType.OPTION:
                break
        return idx

    # Resolve "-> above" back references.
    # Strategy: find the text to match against by checking:
    #   1. The preceding sibling (e.g. "Player: What's wrong?" before "-> above")
    #   2. The parent node
    #   3. Walk up ancestors
    # Then search backwards for the first earlier node with matching text,
    # preferring option nodes (since "above" usually means a dialogue choice).
    _ABOVE_TEXTS = {"above", "same as above", "continues above",
                    "(continues above)", "(continues with above dialogue.)",
                    "(same as above)", "(same as above.)"}
    for i, node in enumerate(nodes):
        if node["node_type"] != DialogueNodeType.ACTION:
            continue
        if (node["text"] or "").strip().lower() not in _ABOVE_TEXTS:
            continue

        parent_idx = node["parent_idx"]
        if parent_idx is None:
            continue

        # Find preceding sibling
        siblings = children_by_parent.get(parent_idx, [])
        sib_pos = siblings.index(i)
        prev_sibling = nodes[siblings[sib_pos - 1]] if sib_pos > 0 else None

        # Build candidate texts to search for, in priority order
        search_targets: list[tuple[str, DialogueNodeType | None]] = []

        # Preceding sibling text → look for an option with that text
        if prev_sibling and prev_sibling["text"]:
            search_targets.append((prev_sibling["text"], DialogueNodeType.OPTION))

        # Parent text → look for same type
        parent = nodes[parent_idx]
        if parent["text"]:
            search_targets.append((parent["text"], parent["node_type"]))

        # Ancestor walk
        ancestor_idx = parent["parent_idx"]
        while ancestor_idx is not None:
            ancestor = nodes[ancestor_idx]
            if ancestor["text"]:
                search_targets.append((ancestor["text"], ancestor["node_type"]))
                break
            ancestor_idx = ancestor["parent_idx"]

        # Search backwards for each target
        resolved = False
        for target_text, preferred_type in search_targets:
            best = None
            for j in range(i - 1, -1, -1):
                candidate = nodes[j]
                if candidate["text"] != target_text:
                    continue
                # Skip the node itself and its direct ancestors
                if j == parent_idx:
                    continue
                if prev_sibling and j == siblings[sib_pos - 1]:
                    continue
                if preferred_type and candidate["node_type"] == preferred_type:
                    best = j
                    break
                if best is None:
                    best = j
            if best is not None:
                continue_targets.append((i, _resolve_target(i, best)))
                resolved = True
                break

    # Resolve "-> other" references: link to the nearest ancestor option/select
    # (the dialogue choice menu that contains the condition branches).
    # For condition-only groups (no option/select ancestor), link to the first
    # sibling of the outermost condition ancestor (re-evaluate from the top).
    for i, node in enumerate(nodes):
        if node["node_type"] != DialogueNodeType.ACTION:
            continue
        if (node["text"] or "").strip().lower() != "other":
            continue
        # Walk up ancestors to find an option/select
        target_idx = None
        outermost_condition_idx = None
        ancestor_idx = node["parent_idx"]
        while ancestor_idx is not None:
            ancestor = nodes[ancestor_idx]
            if ancestor["node_type"] in (DialogueNodeType.OPTION, DialogueNodeType.SELECT):
                target_idx = ancestor_idx
                break
            if ancestor["node_type"] == DialogueNodeType.CONDITION:
                outermost_condition_idx = ancestor_idx
            ancestor_idx = ancestor["parent_idx"]
        # Fallback: first condition in the contiguous block containing the
        # outermost condition ancestor. Walk backwards from the ancestor
        # through siblings to find where the block starts.
        if target_idx is None and outermost_condition_idx is not None:
            parent_of_group = nodes[outermost_condition_idx]["parent_idx"]
            siblings = children_by_parent.get(parent_of_group, [])
            ancestor_pos = siblings.index(outermost_condition_idx)
            block_start = ancestor_pos
            for k in range(ancestor_pos - 1, -1, -1):
                if nodes[siblings[k]]["node_type"] == DialogueNodeType.CONDITION:
                    block_start = k
                else:
                    break
            target_idx = siblings[block_start]
        if target_idx is not None:
            continue_targets.append((i, _resolve_target(i, target_idx)))

    # Resolve "-> continues" / "-> continue": break out of the current branch
    # and continue with the next sibling after the parent node.
    _CONTINUE_TEXTS = {"continues", "continue"}
    for i, node in enumerate(nodes):
        if node["node_type"] != DialogueNodeType.ACTION:
            continue
        if (node["text"] or "").strip().lower() not in _CONTINUE_TEXTS:
            continue
        # Walk up to find a parent that has a next sibling
        ancestor_idx = node["parent_idx"]
        while ancestor_idx is not None:
            grandparent_idx = nodes[ancestor_idx]["parent_idx"]
            gp_children = children_by_parent.get(grandparent_idx, [])
            pos = gp_children.index(ancestor_idx)
            if pos + 1 < len(gp_children):
                target_idx = gp_children[pos + 1]
                continue_targets.append((i, _resolve_target(i, target_idx)))
                break
            ancestor_idx = grandparent_idx

    # Resolve "-> below": same as "-> above" but search forward instead of backward.
    _BELOW_TEXTS = {"below", "same as below", "continues below"}
    for i, node in enumerate(nodes):
        if node["node_type"] != DialogueNodeType.ACTION:
            continue
        if (node["text"] or "").strip().lower() not in _BELOW_TEXTS:
            continue
        parent_idx = node["parent_idx"]
        if parent_idx is None:
            continue
        siblings = children_by_parent.get(parent_idx, [])
        sib_pos = siblings.index(i)
        prev_sibling = nodes[siblings[sib_pos - 1]] if sib_pos > 0 else None

        search_targets: list[tuple[str, DialogueNodeType | None]] = []
        if prev_sibling and prev_sibling["text"]:
            search_targets.append((prev_sibling["text"], DialogueNodeType.OPTION))
        parent = nodes[parent_idx]
        if parent["text"]:
            search_targets.append((parent["text"], parent["node_type"]))

        for target_text, preferred_type in search_targets:
            best = None
            for j in range(i + 1, len(nodes)):
                candidate = nodes[j]
                if candidate["text"] != target_text:
                    continue
                if j == parent_idx:
                    continue
                if preferred_type and candidate["node_type"] == preferred_type:
                    best = j
                    break
                if best is None:
                    best = j
            if best is not None:
                continue_targets.append((i, _resolve_target(i, best)))
                break

    # Resolve "-> initial": go to the first occurrence of the parent's text on the page.
    for i, node in enumerate(nodes):
        if node["node_type"] != DialogueNodeType.ACTION:
            continue
        if (node["text"] or "").strip().lower() != "initial":
            continue
        parent_idx = node["parent_idx"]
        if parent_idx is None:
            continue
        parent = nodes[parent_idx]
        if not parent["text"]:
            continue
        for j in range(len(nodes)):
            if j == parent_idx:
                continue
            if nodes[j]["text"] == parent["text"] and nodes[j]["node_type"] == parent["node_type"]:
                continue_targets.append((i, _resolve_target(i, j)))
                break

    # Resolve "-> previous": go to the nearest earlier occurrence of the parent's text.
    for i, node in enumerate(nodes):
        if node["node_type"] != DialogueNodeType.ACTION:
            continue
        if (node["text"] or "").strip().lower() not in ("previous", "previous2", "previous3"):
            continue
        parent_idx = node["parent_idx"]
        if parent_idx is None:
            continue
        parent = nodes[parent_idx]
        if not parent["text"]:
            continue
        for j in range(i - 1, -1, -1):
            if j == parent_idx:
                continue
            if nodes[j]["text"] == parent["text"] and nodes[j]["node_type"] == parent["node_type"]:
                continue_targets.append((i, _resolve_target(i, j)))
                break

    # Flush resolved continue targets onto the action nodes
    if continue_targets:
        conn.executemany(
            "UPDATE dialogue_nodes SET continue_target_id = ? WHERE id = ?",
            [(idx_to_id[t], idx_to_id[a]) for a, t in continue_targets],
        )

    return len(nodes)


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Clear previous run — order matters for FK constraints
    conn.execute("DELETE FROM dialogue_node_requirement_groups")
    conn.execute("DELETE FROM dialogue_tags")
    conn.execute("DELETE FROM dialogue_instructions")
    conn.execute("DELETE FROM npc_dialogues")
    conn.execute("DELETE FROM quest_dialogues")
    conn.execute("DELETE FROM dialogue_nodes")
    conn.execute("DELETE FROM dialogue_pages")

    # Collect all transcript pages from subcategories
    all_pages: set[str] = set()
    for subcat in SUBCATEGORIES:
        pages = fetch_category_members(subcat, namespace=TRANSCRIPT_NS)
        print(f"  {subcat}: {len(pages)} pages", flush=True)
        all_pages.update(pages)

    pages_list = sorted(all_pages)
    print(f"Found {len(pages_list)} transcript pages total", flush=True)

    node_count = 0
    page_count = 0

    for i in range(0, len(pages_list), 50):
        batch = pages_list[i : i + 50]
        wikitext_batch = fetch_pages_wikitext_batch(batch)

        for page_title, wikitext in wikitext_batch.items():
            if not wikitext:
                continue

            page_type, nodes = parse_dialogue_tree(wikitext)

            # Derive display title (strip Transcript: prefix)
            display_title = page_title
            if display_title.startswith("Transcript:"):
                display_title = display_title[len("Transcript:"):]

            node_count += insert_dialogue(conn, display_title, page_type, nodes)
            page_count += 1

        print(f"  Fetched {i + len(batch)}/{len(pages_list)} pages, {node_count} nodes so far...", flush=True)

    print(f"Recording attributions for {len(pages_list)} pages...", flush=True)
    record_attributions_batch(conn, "dialogue_pages", pages_list)

    conn.commit()
    print(f"Inserted {node_count} dialogue nodes across {page_count} pages into {db_path}", flush=True)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS dialogue trees")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
