"""Instruction-stream cleanup passes.

Each pass is a pure function ``list[Instruction] -> list[Instruction]``.
All passes operate on a per-page stream and are safe to reorder within
the constraints documented below. The canonical pipeline is ``PASSES``.

Passes may mark instructions ``dead``; the terminal ``compact`` pass
drops dead instructions and remaps addresses so addrs stay dense.
"""
from __future__ import annotations

from ragger.dialogue.dialogue_instruction import Instruction
from ragger.enums import InstructionOp


class UnreachableContentError(Exception):
    """Raised when ``sweep_unreachable`` finds content-bearing instructions
    with no incoming edge from any section entry.

    The presence of unreachable ``SPEAK``/``BOX``/``QUEST``/``MENU``/
    ``SELECT``/``SWITCH``/``JUMP_IF`` indicates either a flatten bug or a
    duplicated wiki transcript that needs investigation. The pass refuses
    to silently drop them — the caller must surface them and decide.
    """

    def __init__(self, page_id: int, items: list[tuple[int, InstructionOp]]):
        self.page_id = page_id
        self.items = items
        details = ", ".join(f"{op}@{addr:04d}" for addr, op in items)
        super().__init__(f"page {page_id}: unreachable content: {details}")


_REACHABILITY_CONTENT_OPS = frozenset({
    InstructionOp.SPEAK,
    InstructionOp.BOX,
    InstructionOp.QUEST,
    InstructionOp.MENU,
    InstructionOp.SELECT,
    InstructionOp.SWITCH,
    InstructionOp.JUMP_IF,
})


def lower_gotos(instructions: list[Instruction]) -> list[Instruction]:
    """Convert resolved GOTOs to JUMPs.

    A GOTO with a resolved target is semantically identical to a JUMP —
    the wiki distinction was only that GOTO came from an action node.
    After this pass, GOTO is reserved for genuinely unresolved targets
    (TODOs the later passes or a human can revisit) and JUMP is the
    canonical unconditional branch.
    """
    for instr in instructions:
        if instr.op == InstructionOp.GOTO and instr.targets:
            instr.op = InstructionOp.JUMP
    return instructions


def thread_jumps(instructions: list[Instruction]) -> list[Instruction]:
    """Thread jumps through trivial JUMP trampolines and nested MENUs.

    A trampoline is a single-instruction location whose only purpose is
    to JUMP somewhere else. Any jump to a trampoline can skip the
    indirection and go straight to the JUMP's target.

    Additionally, when a labeled MENU target lands on another MENU
    (after following JUMPs), the matching option label is looked up in
    the target MENU and its target followed instead. This collapses
    alias menus where each option is a back-reference to the
    corresponding option in another menu.
    """
    n = len(instructions)

    def follow(start: int, label: str | None) -> int:
        seen: set[int] = set()
        current = start
        for _ in range(32):  # bound chain length
            if not (0 <= current < n) or current in seen:
                return current
            seen.add(current)
            instr = instructions[current]

            if instr.op in (InstructionOp.JUMP, InstructionOp.GOTO):
                if instr.targets:
                    current = instr.targets[0]
                    continue
                return current

            if instr.op == InstructionOp.MENU and label is not None:
                matched = False
                for i, lbl in enumerate(instr.target_labels):
                    if lbl == label and i < len(instr.targets):
                        current = instr.targets[i]
                        matched = True
                        break
                if not matched:
                    return current
                continue

            return current
        return current

    for instr in instructions:
        if not instr.targets:
            continue
        if instr.op == InstructionOp.MENU:
            labels: list[str | None] = list(instr.target_labels)
            while len(labels) < len(instr.targets):
                labels.append(None)
        else:
            labels = [None] * len(instr.targets)
        instr.targets = [follow(t, lbl) for t, lbl in zip(instr.targets, labels)]
    return instructions


def collapse_trivial_branches(instructions: list[Instruction]) -> list[Instruction]:
    """Collapse branches that have become trivially unconditional.

    Targets the no-ops left behind by ``thread_jumps`` and earlier passes:

    - ``SWITCH`` whose targets all converge on the same addr becomes a
      ``JUMP``. The branch was real before threading; afterwards every
      arm goes to the same place and the labels/predicates are dead
      weight.
    - ``JUMP_IF`` with an empty predicate becomes a ``JUMP``. Defensive —
      it usually indicates an upstream parse miss, but the resulting
      JUMP is still well-formed.
    - ``JUMP_IF`` whose true target is the next live addr, or whose
      false-fallthrough is a ``JUMP`` to the same target, is marked
      dead — both branches converge so the predicate has no observable
      effect.
    - ``JUMP -> @next-live`` is marked dead, since jumping to the next
      live instruction is the same as falling through.

    Marked-dead instructions are dropped by the next ``compact`` pass.
    A SWITCH that's been rewritten to a JUMP in this same pass is
    re-checked for the next-live no-op rule, so a single walk handles
    chained collapses produced by threading.
    """
    n = len(instructions)

    def next_live(i: int) -> int:
        j = i + 1
        while j < n and instructions[j].dead:
            j += 1
        return j

    for i, instr in enumerate(instructions):
        if instr.dead:
            continue

        if (
            instr.op == InstructionOp.SWITCH
            and instr.targets
            and all(t == instr.targets[0] for t in instr.targets)
        ):
            instr.op = InstructionOp.JUMP
            instr.targets = [instr.targets[0]]
            instr.target_labels = []
            instr.target_predicates = []
            instr.text = ""
            instr.fallthrough = False

        if instr.op == InstructionOp.JUMP_IF and not instr.text.strip():
            instr.op = InstructionOp.JUMP
            instr.fallthrough = False

        if instr.op == InstructionOp.JUMP_IF and instr.targets:
            target = instr.targets[0]
            nl = next_live(i)
            if target == nl:
                instr.dead = True
            elif nl < n:
                nxt = instructions[nl]
                if (
                    nxt.op == InstructionOp.JUMP
                    and nxt.targets
                    and nxt.targets[0] == target
                ):
                    instr.dead = True

        if instr.op == InstructionOp.JUMP and instr.targets:
            if instr.targets[0] == next_live(i):
                instr.dead = True

    return instructions


def inline_player_echoes(instructions: list[Instruction]) -> list[Instruction]:
    """Inline ``SPEAK Player + JUMP -> MENU`` player-echo trampolines.

    Pattern::

        SPEAK Player "<text>"
        JUMP -> @<menu_addr>

    where the MENU at ``<menu_addr>`` contains an option labeled
    ``<text>``. The SPEAK Player line is the wiki author's shorthand for
    "the player picks this option from the menu above" — it isn't a
    fresh dialogue line. We rewrite the JUMP to point at the matching
    option's body and mark the SPEAK Player dead so the next compaction
    pass removes it.
    """
    n = len(instructions)
    for i in range(n - 1):
        cur = instructions[i]
        nxt = instructions[i + 1]
        if cur.dead or nxt.dead:
            continue
        if cur.op != InstructionOp.SPEAK or cur.speaker != "Player" or not cur.text:
            continue
        if nxt.op != InstructionOp.JUMP or not nxt.targets:
            continue
        target_addr = nxt.targets[0]
        if not (0 <= target_addr < n):
            continue
        target = instructions[target_addr]
        if target.op != InstructionOp.MENU:
            continue
        for j, lbl in enumerate(target.target_labels):
            if lbl == cur.text and j < len(target.targets):
                nxt.targets = [target.targets[j]]
                cur.dead = True
                break
    return instructions


def fold_select_menu(instructions: list[Instruction]) -> list[Instruction]:
    """Fold a ``SELECT`` into the ``MENU`` that immediately follows it.

    The wiki ``{{tselect}}`` template marks "an in-game selection dialog
    appears here" and is usually followed by ``{{topt}}`` options. In
    the flattened stream this shows up as ``SELECT "title" / MENU
    [opts...]`` back-to-back. The SELECT's text is just the menu's
    title (usually boilerplate "Select an Option", occasionally
    something like "Start the A Night at the Theatre quest?"). This
    pass lifts the SELECT text onto the MENU's ``text`` field and marks
    the SELECT dead so compact drops it.

    SELECTs that aren't immediately followed by a MENU are left alone —
    they're wiki annotations attached to linear dialogue where the
    "selection" has only one option inlined as plain narrative.
    """
    n = len(instructions)
    for i in range(n - 1):
        cur = instructions[i]
        if cur.dead or cur.op != InstructionOp.SELECT:
            continue
        j = i + 1
        while j < n and instructions[j].dead:
            j += 1
        if j >= n:
            continue
        nxt = instructions[j]
        if nxt.op != InstructionOp.MENU or nxt.text:
            continue
        nxt.text = cur.text
        cur.dead = True
    return instructions


def sweep_unreachable(instructions: list[Instruction]) -> list[Instruction]:
    """Mark instructions with no incoming edge as dead — or raise.

    BFS from each section's first live addr, following ``fallthrough``
    edges to the next live addr and explicit ``targets`` edges to their
    destinations. Anything not visited is unreachable.

    Cleanup is **classification-driven**, not blanket deletion:

    - Pure control flow (``JUMP``, ``GOTO``, ``END``) and inert
      annotations (``COND``, ``PRED``) are marked dead. ``compact``
      drops them next.
    - Content-bearing ops (``SPEAK``, ``BOX``, ``QUEST``, ``MENU``,
      ``SELECT``, ``SWITCH``, ``JUMP_IF``) are **never** silently
      dropped. If any are unreachable the pass raises
      ``UnreachableContentError`` so the caller can investigate
      whether the cause is a flatten bug or a duplicated wiki transcript.

    Section entries are defined as the first live addr in each distinct
    section, in stream order. A section with all-dead instructions has
    no entry and contributes nothing to the reachable set.
    """
    n = len(instructions)
    if n == 0:
        return instructions

    def next_live(i: int) -> int:
        j = i
        while j < n and instructions[j].dead:
            j += 1
        return j

    seen_sections: set[str] = set()
    entries: list[int] = []
    for i, instr in enumerate(instructions):
        if instr.dead:
            continue
        if instr.section not in seen_sections:
            seen_sections.add(instr.section)
            entries.append(i)

    reachable: set[int] = set()
    stack = list(entries)
    while stack:
        raw = stack.pop()
        if raw < 0 or raw >= n:
            continue
        i = next_live(raw)
        if i >= n or i in reachable:
            continue
        reachable.add(i)
        instr = instructions[i]
        if instr.fallthrough:
            stack.append(i + 1)
        for target in instr.targets:
            stack.append(target)

    critical: list[tuple[int, InstructionOp]] = []
    for i, instr in enumerate(instructions):
        if instr.dead or i in reachable:
            continue
        if instr.op in _REACHABILITY_CONTENT_OPS:
            critical.append((i, instr.op))
        else:
            instr.dead = True

    if critical:
        raise UnreachableContentError(instructions[critical[0][0]].page_id, critical)

    return instructions


def compact(instructions: list[Instruction]) -> list[Instruction]:
    """Remove dead instructions and rewrite addresses + targets.

    Targets that landed on a deleted instruction are forwarded to the
    next live instruction. MENU/SWITCH option labels stay aligned with
    their targets.
    """
    if not any(i.dead for i in instructions):
        return instructions

    n = len(instructions)
    old_to_new: dict[int, int] = {}
    new_addr = 0
    for old_addr, instr in enumerate(instructions):
        if instr.dead:
            continue
        old_to_new[old_addr] = new_addr
        new_addr += 1

    def remap(t: int) -> int | None:
        cur = t
        while 0 <= cur < n:
            if cur in old_to_new:
                return old_to_new[cur]
            cur += 1
        return None

    new_instrs: list[Instruction] = []
    for old_addr, instr in enumerate(instructions):
        if instr.dead:
            continue
        new_targets: list[int] = []
        for t in instr.targets:
            r = remap(t)
            if r is not None:
                new_targets.append(r)
        new_instrs.append(Instruction(
            page_id=instr.page_id,
            addr=old_to_new[old_addr],
            section=instr.section,
            op=instr.op,
            text=instr.text,
            speaker=instr.speaker,
            fallthrough=instr.fallthrough,
            targets=new_targets,
            target_labels=instr.target_labels.copy(),
            target_predicates=instr.target_predicates.copy(),
        ))
    return new_instrs


PASSES = [
    lower_gotos,
    thread_jumps,
    collapse_trivial_branches,
    inline_player_echoes,
    fold_select_menu,
    sweep_unreachable,
    compact,
]
