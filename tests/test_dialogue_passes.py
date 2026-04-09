"""Unit tests for each dialogue pass.

Hand-crafted Instruction fixtures — no DB. The passes are pure
``list[Instruction] -> list[Instruction]`` so each one is easy to test in
isolation.
"""
from __future__ import annotations

import pytest

from ragger.dialogue import Instruction
from ragger.dialogue.dialogue_passes import (
    UnreachableContentError,
    collapse_trivial_branches,
    compact,
    fold_select_menu,
    inline_player_echoes,
    lower_gotos,
    sweep_unreachable,
    thread_jumps,
)
from ragger.enums import InstructionOp


def _instr(addr: int, op: InstructionOp, **kwargs) -> Instruction:
    """Convenience for building Instruction fixtures."""
    return Instruction(page_id=1, addr=addr, section="main", op=op, **kwargs)


def test_lower_gotos_converts_resolved() -> None:
    instrs = [
        _instr(0, InstructionOp.GOTO, text="above", targets=[2], fallthrough=False),
        _instr(1, InstructionOp.GOTO, text="unresolved", fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="hi", speaker="NPC"),
    ]
    out = lower_gotos(instrs)
    assert out[0].op == InstructionOp.JUMP  # resolved
    assert out[1].op == InstructionOp.GOTO  # still unresolved
    assert out[2].op == InstructionOp.SPEAK


def test_thread_jumps_follows_trampoline() -> None:
    instrs = [
        _instr(0, InstructionOp.JUMP, targets=[1], fallthrough=False),
        _instr(1, InstructionOp.JUMP, targets=[2], fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="dest", speaker="NPC"),
    ]
    thread_jumps(instrs)
    assert instrs[0].targets == [2]  # threaded past the middle JUMP


def test_thread_jumps_follows_labeled_menu() -> None:
    # JUMP -> MENU with label "foo" -> option body @3.
    # A MENU-level jump with label="foo" threads through the MENU.
    instrs = [
        _instr(0, InstructionOp.MENU, targets=[1], target_labels=["foo"], fallthrough=False),
        _instr(1, InstructionOp.MENU, targets=[2, 3], target_labels=["foo", "bar"], fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="foo body", speaker="NPC"),
        _instr(3, InstructionOp.SPEAK, text="bar body", speaker="NPC"),
    ]
    thread_jumps(instrs)
    assert instrs[0].targets == [2]  # threaded through MENU by matching label


def test_thread_jumps_stops_at_unresolved_goto() -> None:
    instrs = [
        _instr(0, InstructionOp.JUMP, targets=[1], fallthrough=False),
        _instr(1, InstructionOp.GOTO, text="unresolved", fallthrough=False),
    ]
    thread_jumps(instrs)
    assert instrs[0].targets == [1]  # can't follow an unresolved GOTO


def test_collapse_switch_with_all_targets_equal() -> None:
    # Two condition arms threaded down to the same destination after thread_jumps.
    instrs = [
        _instr(0, InstructionOp.SWITCH,
               targets=[2, 2],
               target_labels=["if completed", "otherwise"],
               target_predicates=["<COMPLETED> Quest", ""],
               fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="orphan", speaker="NPC"),
        _instr(2, InstructionOp.SPEAK, text="dest", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[0].op == InstructionOp.JUMP
    assert instrs[0].targets == [2]
    assert instrs[0].target_labels == []
    assert instrs[0].target_predicates == []
    assert instrs[0].fallthrough is False


def test_collapse_switch_with_distinct_targets_left_alone() -> None:
    instrs = [
        _instr(0, InstructionOp.SWITCH,
               targets=[2, 3],
               target_labels=["if a", "if b"],
               fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="orphan", speaker="NPC"),
        _instr(2, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(3, InstructionOp.SPEAK, text="b", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[0].op == InstructionOp.SWITCH
    assert instrs[0].targets == [2, 3]


def test_collapse_jump_if_with_empty_predicate() -> None:
    instrs = [
        _instr(0, InstructionOp.JUMP_IF, text="", targets=[2]),
        _instr(1, InstructionOp.SPEAK, text="false branch", speaker="NPC"),
        _instr(2, InstructionOp.SPEAK, text="true branch", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[0].op == InstructionOp.JUMP
    assert instrs[0].fallthrough is False
    assert instrs[0].targets == [2]


def test_collapse_jump_if_target_equals_next_live() -> None:
    instrs = [
        _instr(0, InstructionOp.JUMP_IF, text="cond", targets=[1]),
        _instr(1, InstructionOp.SPEAK, text="dest", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[0].dead  # both branches converge on @1


def test_collapse_jump_if_followed_by_jump_to_same_target() -> None:
    instrs = [
        _instr(0, InstructionOp.JUMP_IF, text="cond", targets=[3]),
        _instr(1, InstructionOp.JUMP, targets=[3], fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="orphan", speaker="NPC"),
        _instr(3, InstructionOp.SPEAK, text="dest", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[0].dead
    assert not instrs[1].dead  # JUMP survives — predecessor falls through to it


def test_collapse_jump_to_next_live() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.JUMP, targets=[2], fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="b", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[1].dead  # jumps to immediately following addr


def test_collapse_jump_skipping_dead_to_next_live() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.JUMP, targets=[3], fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="dead", speaker="Player", dead=True),
        _instr(3, InstructionOp.SPEAK, text="b", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[1].dead  # @3 is the next *live* addr after @1


def test_collapse_chained_switch_to_jump_to_next() -> None:
    # SWITCH → JUMP via the all-same rule, then the resulting JUMP gets
    # killed by the ->next rule in the same walk.
    instrs = [
        _instr(0, InstructionOp.SWITCH,
               targets=[1, 1],
               target_labels=["a", "b"],
               fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="dest", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert instrs[0].dead  # collapsed to JUMP -> @1, then killed as ->next-live


def test_collapse_jump_unrelated_target_left_alone() -> None:
    instrs = [
        _instr(0, InstructionOp.JUMP, targets=[2], fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="b", speaker="NPC"),
        _instr(2, InstructionOp.SPEAK, text="dest", speaker="NPC"),
    ]
    collapse_trivial_branches(instrs)
    assert not instrs[0].dead
    assert instrs[0].targets == [2]


def test_inline_player_echoes_kills_echo_trampoline() -> None:
    instrs = [
        _instr(0, InstructionOp.MENU, targets=[3, 4], target_labels=["Hi there", "Bye"], fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="Hi there", speaker="Player"),
        _instr(2, InstructionOp.JUMP, targets=[0], fallthrough=False),
        _instr(3, InstructionOp.SPEAK, text="hello", speaker="NPC"),
        _instr(4, InstructionOp.SPEAK, text="goodbye", speaker="NPC"),
    ]
    inline_player_echoes(instrs)
    assert instrs[1].dead  # player echo marked dead
    assert instrs[2].targets == [3]  # JUMP rewritten to matching option body


def test_inline_player_echoes_ignores_non_matching_labels() -> None:
    instrs = [
        _instr(0, InstructionOp.MENU, targets=[3], target_labels=["Completely different"], fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="Hi there", speaker="Player"),
        _instr(2, InstructionOp.JUMP, targets=[0], fallthrough=False),
        _instr(3, InstructionOp.SPEAK, text="hello", speaker="NPC"),
    ]
    inline_player_echoes(instrs)
    assert not instrs[1].dead
    assert instrs[2].targets == [0]  # unchanged


def test_fold_select_menu_lifts_title() -> None:
    instrs = [
        _instr(0, InstructionOp.SELECT, text="Start the quest?"),
        _instr(1, InstructionOp.MENU, targets=[2, 3], target_labels=["Yes", "No"], fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="yes", speaker="NPC"),
        _instr(3, InstructionOp.SPEAK, text="no", speaker="NPC"),
    ]
    fold_select_menu(instrs)
    assert instrs[0].dead
    assert instrs[1].text == "Start the quest?"


def test_fold_select_menu_skips_dead_between() -> None:
    # A dead instruction between SELECT and MENU (e.g. from an earlier
    # inline_player_echoes) should not block the fold.
    instrs = [
        _instr(0, InstructionOp.SELECT, text="Title"),
        _instr(1, InstructionOp.SPEAK, text="dead", speaker="Player", dead=True),
        _instr(2, InstructionOp.MENU, targets=[3], target_labels=["Yes"], fallthrough=False),
        _instr(3, InstructionOp.SPEAK, text="yes", speaker="NPC"),
    ]
    fold_select_menu(instrs)
    assert instrs[0].dead
    assert instrs[2].text == "Title"


def test_fold_select_menu_leaves_standalone_select_alone() -> None:
    instrs = [
        _instr(0, InstructionOp.SELECT, text="Select an Option"),
        _instr(1, InstructionOp.SPEAK, text="player line", speaker="Player"),
    ]
    fold_select_menu(instrs)
    assert not instrs[0].dead  # no adjacent MENU → untouched


def test_fold_select_menu_preserves_existing_title() -> None:
    instrs = [
        _instr(0, InstructionOp.SELECT, text="my title"),
        _instr(1, InstructionOp.MENU, text="already has a title", targets=[2], target_labels=["Yes"], fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="yes", speaker="NPC"),
    ]
    fold_select_menu(instrs)
    assert not instrs[0].dead
    assert instrs[1].text == "already has a title"


def test_sweep_unreachable_empty_stream_is_noop() -> None:
    out = sweep_unreachable([])
    assert out == []


def test_sweep_unreachable_linear_reachable_chain_unchanged() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.SPEAK, text="b", speaker="NPC"),
        _instr(2, InstructionOp.END, fallthrough=False),
    ]
    sweep_unreachable(instrs)
    assert all(not i.dead for i in instrs)


def test_sweep_unreachable_drops_orphan_jump() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.END, fallthrough=False),
        _instr(2, InstructionOp.JUMP, targets=[0], fallthrough=False),  # nothing points here
    ]
    sweep_unreachable(instrs)
    assert not instrs[0].dead
    assert not instrs[1].dead
    assert instrs[2].dead  # orphan JUMP, control flow only — safe to drop


def test_sweep_unreachable_drops_orphan_end_and_cond() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.END, fallthrough=False),
        _instr(2, InstructionOp.END, fallthrough=False),  # orphan
        _instr(3, InstructionOp.COND, text="annotation"),  # orphan
    ]
    sweep_unreachable(instrs)
    assert instrs[2].dead
    assert instrs[3].dead


def test_sweep_unreachable_raises_on_orphan_speak() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="reachable", speaker="NPC"),
        _instr(1, InstructionOp.END, fallthrough=False),
        _instr(2, InstructionOp.SPEAK, text="orphan!", speaker="NPC"),  # critical
    ]
    with pytest.raises(UnreachableContentError) as exc:
        sweep_unreachable(instrs)
    assert exc.value.page_id == 1
    assert exc.value.items == [(2, InstructionOp.SPEAK)]


def test_sweep_unreachable_raises_on_orphan_menu() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="reachable", speaker="NPC"),
        _instr(1, InstructionOp.END, fallthrough=False),
        _instr(2, InstructionOp.MENU, targets=[3], target_labels=["Yes"], fallthrough=False),
        _instr(3, InstructionOp.SPEAK, text="answer", speaker="NPC"),
    ]
    with pytest.raises(UnreachableContentError):
        sweep_unreachable(instrs)


def test_sweep_unreachable_follows_jump_target() -> None:
    instrs = [
        _instr(0, InstructionOp.JUMP, targets=[2], fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="skipped but no in-edge", speaker="NPC"),
        _instr(2, InstructionOp.SPEAK, text="reached", speaker="NPC"),
    ]
    # Note: instr 1 has no incoming edge so it's a critical unreachable
    with pytest.raises(UnreachableContentError) as exc:
        sweep_unreachable(instrs)
    assert exc.value.items == [(1, InstructionOp.SPEAK)]


def test_sweep_unreachable_follows_menu_targets() -> None:
    instrs = [
        _instr(0, InstructionOp.MENU,
               targets=[1, 2],
               target_labels=["a", "b"],
               fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="a body", speaker="NPC"),
        _instr(2, InstructionOp.SPEAK, text="b body", speaker="NPC"),
    ]
    sweep_unreachable(instrs)
    assert all(not i.dead for i in instrs)


def test_sweep_unreachable_multi_section_each_first_addr_is_entry() -> None:
    instrs = [
        Instruction(page_id=1, addr=0, section="main", op=InstructionOp.SPEAK,
                    text="main", speaker="NPC"),
        Instruction(page_id=1, addr=1, section="main", op=InstructionOp.END,
                    fallthrough=False),
        Instruction(page_id=1, addr=2, section="alt", op=InstructionOp.SPEAK,
                    text="alt", speaker="NPC"),
        Instruction(page_id=1, addr=3, section="alt", op=InstructionOp.END,
                    fallthrough=False),
    ]
    sweep_unreachable(instrs)
    assert all(not i.dead for i in instrs)  # both sections reachable from their entries


def test_sweep_unreachable_skips_dead_when_walking_fallthrough() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.SPEAK, text="dead", speaker="Player", dead=True),
        _instr(2, InstructionOp.SPEAK, text="b", speaker="NPC"),
        _instr(3, InstructionOp.END, fallthrough=False),
    ]
    sweep_unreachable(instrs)
    # @2 is reached by falling through past dead @1; no critical raise
    assert not instrs[0].dead
    assert not instrs[2].dead
    assert not instrs[3].dead


def test_sweep_unreachable_section_entry_starts_on_first_live_addr() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="dead start", speaker="Player", dead=True),
        _instr(1, InstructionOp.SPEAK, text="real entry", speaker="NPC"),
        _instr(2, InstructionOp.END, fallthrough=False),
    ]
    sweep_unreachable(instrs)
    assert not instrs[1].dead  # section entry walked past the dead first instr


def test_compact_removes_dead_and_remaps_targets() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.SPEAK, text="dead", speaker="Player", dead=True),
        _instr(2, InstructionOp.JUMP, targets=[0], fallthrough=False),
        _instr(3, InstructionOp.SPEAK, text="b", speaker="NPC"),
    ]
    out = compact(instrs)
    assert len(out) == 3
    assert out[0].text == "a"
    assert out[0].addr == 0
    assert out[1].op == InstructionOp.JUMP
    assert out[1].addr == 1  # was 2, remapped
    assert out[1].targets == [0]  # target unchanged, still points at "a"
    assert out[2].text == "b"
    assert out[2].addr == 2


def test_compact_forwards_target_landing_on_dead() -> None:
    # A target pointing at a dead instruction should forward to the next live one.
    instrs = [
        _instr(0, InstructionOp.JUMP, targets=[1], fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="dead", speaker="Player", dead=True),
        _instr(2, InstructionOp.SPEAK, text="alive", speaker="NPC"),
    ]
    out = compact(instrs)
    assert out[0].targets == [1]  # forwarded past the dead instruction


def test_compact_is_noop_when_nothing_dead() -> None:
    instrs = [
        _instr(0, InstructionOp.SPEAK, text="a", speaker="NPC"),
        _instr(1, InstructionOp.SPEAK, text="b", speaker="NPC"),
    ]
    out = compact(instrs)
    assert out is instrs  # same object — fast path


def test_compact_preserves_menu_labels_and_predicates() -> None:
    instrs = [
        _instr(0, InstructionOp.MENU, text="title",
               targets=[2, 3],
               target_labels=["Yes", "No"],
               target_predicates=["if awake", ""],
               fallthrough=False),
        _instr(1, InstructionOp.SPEAK, text="dead", speaker="Player", dead=True),
        _instr(2, InstructionOp.SPEAK, text="yes", speaker="NPC"),
        _instr(3, InstructionOp.SPEAK, text="no", speaker="NPC"),
    ]
    out = compact(instrs)
    menu = out[0]
    assert menu.target_labels == ["Yes", "No"]
    assert menu.target_predicates == ["if awake", ""]
    assert menu.text == "title"
    assert menu.targets == [1, 2]  # addrs remapped after dropping dead
