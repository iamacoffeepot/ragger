"""Flatten a dialogue page tree into a linear instruction stream.

Produces a per-page stream: each Instruction carries the section it came
from as a column, not a partition. Addresses are global within the page
and cross-section references are just regular local addresses.

GOTOs are resolved via ``DialogueNode.continue_target_id``. Option
predicates (from the wiki ``cond=`` attribute, parsed as synthetic first-
child CONDITION nodes) are folded into the enclosing MENU's
``target_predicates`` metadata as a post-flatten step.
"""
from __future__ import annotations

import sqlite3

from ragger.dialogue.dialogue_instruction import Instruction
from ragger.dialogue.dialogue_node import DialogueNode
from ragger.dialogue.dialogue_page import DialoguePage
from ragger.enums import DialogueNodeType, InstructionOp


_OP_MAP = {
    DialogueNodeType.LINE: InstructionOp.SPEAK,
    DialogueNodeType.BOX: InstructionOp.BOX,
    DialogueNodeType.SELECT: InstructionOp.SELECT,
    DialogueNodeType.QUEST_ACTION: InstructionOp.QUEST,
}


def _section_of(node: DialogueNode) -> str:
    # Preserve the full section path. The wiki uses "/" to delimit
    # subsections (e.g. "Standard dialogue/Pre-quest"), and each one is
    # an independent dialogue branch the engine selects between based on
    # game state. Collapsing them merges entry points and makes
    # downstream branches structurally unreachable.
    return node.section or "main"


def flatten(conn: sqlite3.Connection, page: DialoguePage) -> list[Instruction]:
    """Flatten a dialogue page into a linear per-page instruction stream.

    OPTION nodes do not emit their own instruction — they resolve to the
    address of their first body instruction (or an END placeholder if the
    body is empty). A MENU instruction is injected before each option
    group with each option's body address as a target, labeled with the
    option text. Condition groups similarly lift to SWITCH (2+) or
    JUMP_IF (solo) structures.

    Synthetic predicate CONDITION nodes (first child of an OPTION,
    generated from the wiki ``cond=`` attribute) are emitted as ``PRED``
    and then folded onto the enclosing MENU's target_predicates metadata
    in a post-emit step.
    """
    nodes = page.nodes(conn)
    if not nodes:
        return []

    children_by_parent: dict[int | None, list[DialogueNode]] = {}
    for node in nodes:
        children_by_parent.setdefault(node.parent_id, []).append(node)

    # Sibling groups for cond/option classification are scoped by section
    # as well as parent. Two top-level CONDs (parent_id None) belonging to
    # different wiki subsections are NOT semantic siblings — each is the
    # entry of its own dialogue branch — and merging them collapses
    # independent JUMP_IFs into one bogus SWITCH.
    siblings_by_parent_and_section: dict[
        tuple[int | None, str], list[DialogueNode]
    ] = {}
    for node in nodes:
        key = (node.parent_id, _section_of(node))
        siblings_by_parent_and_section.setdefault(key, []).append(node)

    node_by_id = {n.id: n for n in nodes}

    # Synthetic option predicate CONDs: childless CONDITION nodes that are
    # the first child of an OPTION. These carry the wiki ``cond=`` attribute
    # and encode menu visibility (not body control flow).
    predicate_cond_ids: set[int] = set()
    for node in nodes:
        if node.node_type != DialogueNodeType.CONDITION:
            continue
        if children_by_parent.get(node.id):
            continue
        if node.parent_id is None:
            continue
        parent = node_by_id.get(node.parent_id)
        if parent is None or parent.node_type != DialogueNodeType.OPTION:
            continue
        parent_children = children_by_parent.get(node.parent_id, [])
        if parent_children and parent_children[0].id == node.id:
            predicate_cond_ids.add(node.id)

    # Option groups form a MENU at any size (player must interact).
    # Condition groups form a SWITCH (size 2+) or a JUMP_IF (size 1).
    # A solo COND with no children but with following same-depth siblings
    # is "sibling-bodied" — its body is the following siblings until the
    # parent's body ends. We lift those into JUMP_IF too. Predicate CONDs
    # are excluded from sibling classification — they're metadata.
    option_group_at: dict[int, list[int]] = {}
    cond_group_at: dict[int, list[int]] = {}
    cond_in_group: set[int] = set()
    sibling_bodied_conds: set[int] = set()
    for siblings in siblings_by_parent_and_section.values():
        option_sibs = [s.id for s in siblings if s.node_type == DialogueNodeType.OPTION]
        if option_sibs:
            option_group_at[option_sibs[0]] = option_sibs
        cond_sibs = [
            s
            for s in siblings
            if s.node_type == DialogueNodeType.CONDITION
            and s.id not in predicate_cond_ids
        ]
        if len(cond_sibs) >= 2:
            cond_group_at[cond_sibs[0].id] = [s.id for s in cond_sibs]
            cond_in_group.update(s.id for s in cond_sibs)
        elif len(cond_sibs) == 1:
            cond = cond_sibs[0]
            if children_by_parent.get(cond.id):
                cond_group_at[cond.id] = [cond.id]
                cond_in_group.add(cond.id)
            else:
                cond_pos = next(i for i, s in enumerate(siblings) if s.id == cond.id)
                if cond_pos + 1 < len(siblings):
                    cond_group_at[cond.id] = [cond.id]
                    cond_in_group.add(cond.id)
                    sibling_bodied_conds.add(cond.id)

    # Any option id -> the first option in its sibling group
    option_to_first: dict[int, int] = {}
    for first, group in option_group_at.items():
        for oid in group:
            option_to_first[oid] = first

    # Label id -> first label id of its group, plus group size/op
    label_to_group: dict[int, int] = {}
    group_kind: dict[int, str] = {}
    for first, group in option_group_at.items():
        for lid in group:
            label_to_group[lid] = first
        group_kind[first] = "menu"
    for first, group in cond_group_at.items():
        for lid in group:
            label_to_group[lid] = first
        group_kind[first] = "switch" if len(group) >= 2 else "jump_if"

    node_id_to_addr: dict[int, int] = {}
    label_addr: dict[int, int] = {}
    label_text: dict[int, str] = {}
    pending_branches: list[tuple[int, list[int]]] = []
    pending_gotos: list[tuple[int, DialogueNode]] = []
    menu_addr_by_first: dict[int, int] = {}
    instructions: list[Instruction] = []
    addr = 0

    open_bodies: list[tuple[int, int, str]] = []
    group_remaining: dict[int, int] = {}
    group_placeholders: dict[int, list[int]] = {}
    group_jump_if_addr: dict[int, int] = {}
    deferred_by_outer_group: dict[int, list[int]] = {}
    for first, group in option_group_at.items():
        group_remaining[first] = len(group)
    for first, group in cond_group_at.items():
        group_remaining[first] = len(group)

    def _new_instr(op: InstructionOp, text: str = "", *, section: str,
                   speaker: str | None = None, fallthrough: bool = True) -> Instruction:
        return Instruction(
            page_id=page.id,
            addr=addr,
            section=section,
            op=op,
            text=text,
            speaker=speaker,
            fallthrough=fallthrough,
        )

    def close_body(
        label_id: int,
        body_section: str,
        at_end_of_stream: bool = False,
        outer_in_cascade: int | None = None,
    ) -> None:
        nonlocal addr
        group_id = label_to_group.get(label_id)
        if group_id is None:
            return
        is_sibling_bodied = label_id in sibling_bodied_conds
        if not at_end_of_stream and instructions and instructions[-1].fallthrough:
            ph_addr = addr
            instructions.append(_new_instr(InstructionOp.JUMP, section=body_section, fallthrough=False))
            addr += 1
            group_placeholders.setdefault(group_id, []).append(ph_addr)
        group_remaining[group_id] -= 1
        if group_remaining[group_id] == 0:
            join_addr = addr
            join_valid = join_addr < len(instructions) or not at_end_of_stream
            for ph in group_placeholders.get(group_id, []):
                if join_valid:
                    instructions[ph].targets = [join_addr]
                else:
                    instructions[ph].op = InstructionOp.END
                    instructions[ph].text = ""
            for ji_addr in deferred_by_outer_group.get(group_id, []):
                if join_valid:
                    instructions[ji_addr].targets = [join_addr]
            deferred_by_outer_group.pop(group_id, None)
            group_placeholders.pop(group_id, None)
            if group_id in group_jump_if_addr:
                ji_addr = group_jump_if_addr.pop(group_id)
                if is_sibling_bodied and outer_in_cascade is not None:
                    outer_group_id = label_to_group.get(outer_in_cascade)
                    if outer_group_id is not None:
                        deferred_by_outer_group.setdefault(outer_group_id, []).append(ji_addr)
                    elif join_valid:
                        instructions[ji_addr].targets = [join_addr]
                elif join_valid:
                    instructions[ji_addr].targets = [join_addr]

    for node in nodes:
        section = _section_of(node)

        while open_bodies and open_bodies[-1][1] >= node.depth:
            closed_id, _, closed_section = open_bodies.pop()
            outer_id = (
                open_bodies[-1][0]
                if open_bodies and open_bodies[-1][1] >= node.depth
                else None
            )
            close_body(closed_id, closed_section, outer_in_cascade=outer_id)

        if node.id in option_group_at:
            instructions.append(_new_instr(InstructionOp.MENU, section=section, fallthrough=False))
            pending_branches.append((addr, option_group_at[node.id]))
            menu_addr_by_first[node.id] = addr
            addr += 1

        if node.id in cond_group_at:
            kind = group_kind[node.id]
            if kind == "switch":
                instructions.append(_new_instr(InstructionOp.SWITCH, section=section, fallthrough=False))
                pending_branches.append((addr, cond_group_at[node.id]))
            else:
                cond_text = node_by_id[cond_group_at[node.id][0]].text or ""
                instructions.append(_new_instr(InstructionOp.JUMP_IF, cond_text, section=section))
                group_jump_if_addr[node.id] = addr
            addr += 1

        is_label = (
            node.node_type == DialogueNodeType.OPTION
            or (node.node_type == DialogueNodeType.CONDITION and node.id in cond_in_group)
        )
        if is_label:
            label_text[node.id] = node.text or ""
            children = children_by_parent.get(node.id, [])
            if node.id in sibling_bodied_conds:
                label_addr[node.id] = addr
                open_bodies.append((node.id, node.depth - 1, section))
            elif not children:
                label_addr[node.id] = addr
                instructions.append(_new_instr(InstructionOp.END, section=section, fallthrough=False))
                addr += 1
                close_body(node.id, section)
            else:
                label_addr[node.id] = addr
                open_bodies.append((node.id, node.depth, section))
            continue

        if node.node_type == DialogueNodeType.CONDITION:
            node_id_to_addr[node.id] = addr
            op = InstructionOp.PRED if node.id in predicate_cond_ids else InstructionOp.COND
            instructions.append(_new_instr(op, node.text or "", section=section))
            addr += 1
            continue

        node_id_to_addr[node.id] = addr
        text = node.text or ""

        if node.node_type == DialogueNodeType.ACTION:
            if text.strip().lower() == "end":
                instructions.append(_new_instr(InstructionOp.END, text, section=section, fallthrough=False))
            elif node.continue_target_id is not None:
                # Resolved reference (above/below/other) — real branch.
                instructions.append(_new_instr(InstructionOp.GOTO, text, section=section, fallthrough=False))
                pending_gotos.append((addr, node))
            else:
                # Narrative stage direction (e.g. "receives=X", "[NPC]
                # continues counting"). Not a control transfer — control
                # continues to the next sibling, the action text is just
                # description that downstream renderers can show inline.
                instructions.append(_new_instr(InstructionOp.GOTO, text, section=section, fallthrough=True))
        else:
            op = _OP_MAP.get(node.node_type, InstructionOp.SPEAK)
            instructions.append(_new_instr(op, text, section=section, speaker=node.speaker))

        addr += 1

    while open_bodies:
        closed_id, _, closed_section = open_bodies.pop()
        close_body(closed_id, closed_section, at_end_of_stream=True)

    for branch_addr, label_node_ids in pending_branches:
        branch = instructions[branch_addr]
        for nid in label_node_ids:
            body_addr = label_addr.get(nid)
            if body_addr is not None:
                branch.targets.append(body_addr)
                branch.target_labels.append(label_text.get(nid, ""))

    def _resolve_target(target_node_id: int) -> int | None:
        if target_node_id in option_to_first:
            first = option_to_first[target_node_id]
            menu_addr = menu_addr_by_first.get(first)
            if menu_addr is not None:
                return menu_addr
        if target_node_id in node_id_to_addr:
            return node_id_to_addr[target_node_id]
        if target_node_id in label_addr:
            return label_addr[target_node_id]
        return None

    for goto_addr, source_node in pending_gotos:
        if source_node.continue_target_id is None:
            continue
        target_addr = _resolve_target(source_node.continue_target_id)
        if target_addr is not None:
            instructions[goto_addr].targets = [target_addr]

    _attach_option_predicates(instructions)

    return instructions


def _attach_option_predicates(instructions: list[Instruction]) -> None:
    """Fold ``PRED`` instructions onto their MENU's per-option metadata.

    A PRED at the head of an option body carries a wiki ``cond=`` visibility
    predicate. We lift the text onto ``target_predicates[i]`` of the matching
    MENU option, mark the PRED dead, and advance the MENU target past the
    PRED so later passes can thread through it cleanly.
    """
    n = len(instructions)
    for instr in instructions:
        if instr.op != InstructionOp.MENU or not instr.target_labels:
            continue
        label_count = len(instr.target_labels)
        new_preds = list(instr.target_predicates) if instr.target_predicates else []
        if len(new_preds) < label_count:
            new_preds = new_preds + [""] * (label_count - len(new_preds))
        attached = False
        for i, t in enumerate(instr.targets[:label_count]):
            if not (0 <= t < n):
                continue
            target = instructions[t]
            if target.op == InstructionOp.PRED and not target.dead:
                new_preds[i] = target.text
                target.dead = True
                if t + 1 < n:
                    instr.targets[i] = t + 1
                attached = True
        if attached:
            instr.target_predicates = new_preds
