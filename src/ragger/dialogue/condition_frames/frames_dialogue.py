"""Dialogue interaction frames: answered, talked_to, npc_role, puzzle, etc."""
from __future__ import annotations

from ragger.dialogue.condition_types import (
    FrameRule,
    ITEM_NOUN,
    NEG,
    make_atom,
    pre_rule,
    rule,
)

CORRECT_WORDS = "correct|correctly|right"
WRONG_WORDS = "incorrect|incorrectly|wrong"
ANSWER_OUTCOME = rf"(?P<which>{CORRECT_WORDS}|{WRONG_WORDS})"

_NPC_ROLES = "murderer|traitor|spy|killer|correct one|right one|wrong one|thief|guilty|innocent"


def _is_correct(m) -> bool:
    return m.group("which") in ("correct", "correctly", "right")


RULES: list[FrameRule] = [
    # --- answered ---
    rule("answered", rf"^(?:has\s+|have\s+)?(?:not\s+)?answered\s+(?:this\s+)?(?:\{{item\}}\s+)?{ANSWER_OUTCOME}(?:\s+.*)?$",
         lambda m: make_atom("answered", correct=_is_correct(m))),
    pre_rule("answered", rf"^when given the (?P<which>correct|right|wrong|incorrect) answer$",
             lambda m: make_atom("answered", correct=m.group("which") in ("correct", "right"))),
    pre_rule("answered", rf"^(?:if\s+)?(?:the\s+)?answer\s+is\s+{ANSWER_OUTCOME}(?:\s+.*)?$",
             lambda m: make_atom("answered", correct=_is_correct(m))),
    pre_rule("answered", rf"^giving the {ANSWER_OUTCOME} answer$",
             lambda m: make_atom("answered", correct=_is_correct(m))),
    pre_rule("answered", rf"^if (?:the\s+)?(?:player|you)\s+gives?\s+(?:the\s+)?{ANSWER_OUTCOME} answer$",
             lambda m: make_atom("answered", correct=_is_correct(m))),
    pre_rule("answered", rf"^if (?:the\s+)?player\s+answers?\s+{ANSWER_OUTCOME}(?:\s+.*)?$",
             lambda m: make_atom("answered", correct=_is_correct(m))),

    # answered_item
    rule("answered_item",
         rf"^(?:has|have)\s+(?:not\s+)?answered (?:this\s+)?{ITEM_NOUN}\s+(?P<which>correctly|incorrectly|wrong|right)(?:\s+.*)?$",
         lambda m: make_atom("answered_item", correct=m.group("which") in ("correctly", "right"), neg="not " in m.string[:m.end()])),

    # password_check
    rule("password_check", rf"^(?:the\s+)?password is {ANSWER_OUTCOME}(?:\s+.*)?$",
         lambda m: make_atom("password_check", correct=_is_correct(m))),

    # --- puzzle_answer / puzzle_solved ---
    pre_rule("puzzle_answer", rf"^(?:if\s+)?the\s+answer\s+is\s+(?:word\s+)?\w+(?:\s+.*)?$", lambda m: make_atom("puzzle_answer")),
    pre_rule("puzzle_answer", rf"^(?:if\s+)?(?:the\s+)?correct\s+(?:name|answer|code|word)\s+is\s+(?:chosen|selected|given|entered)(?:\s+.*)?$", lambda m: make_atom("puzzle_answer")),
    pre_rule("puzzle_answer", rf"^(?:if\s+)?after\s+(?:one|two|three|four|five|\d+)\s+out\s+of\s+(?:one|two|three|four|five|\d+)\s+correct\s+(?:moves?|answers?)(?:\s+.*)?$", lambda m: make_atom("puzzle_answer")),

    rule("puzzle_solved", rf"^(?:the\s+)?puzzle is solved$", lambda m: make_atom("puzzle_solved", neg=False)),
    rule("puzzle_solved", rf"^(?:the\s+)?puzzle is not solved$", lambda m: make_atom("puzzle_solved", neg=True)),
    pre_rule("puzzle_solved", rf"^if (?:the\s+)?puzzle is (?:not\s+)?solved$", lambda m: make_atom("puzzle_solved", neg="not " in m.string)),
    pre_rule("puzzle_solved", rf"^if the \{{item\}} is (?:not\s+)?solved$", lambda m: make_atom("puzzle_solved", neg="not " in m.string)),
    pre_rule("puzzle_solved", rf"^if the \{{wiki\}} is (?:not\s+)?solved$", lambda m: make_atom("puzzle_solved", neg="not " in m.string)),

    # --- dialogue_state ---
    pre_rule("dialogue_state", rf"^(?:if\s+)?(?:not\s+)?all\s+(?:options|questions|topics|dialogue options)\s+have\s+been\s+(?:asked|chosen|selected|exhausted|discussed)(?:\s+.*)?$",
             lambda m: make_atom("dialogue_state", neg="not " in m.string[:10])),
    pre_rule("dialogue_state", rf"^(?:if\s+)?(?:the\s+)?player\s+has\s+(?:not\s+)?(?:asked|answered|chosen|exhausted)\s+all\s+(?:options|questions|topics)(?:\s+.*)?$",
             lambda m: make_atom("dialogue_state", neg="not " in m.string)),
    rule("dialogue_state", rf"^(?:has|have)\s+(?:not\s+)?completed\s+this\s+dialogue\s+option(?:\s+.*)?$",
         lambda m: make_atom("dialogue_state", neg="not " in m.string[:20])),
    pre_rule("dialogue_state", rf"^(?:if\s+)?asking\s+for\s+the\s+first\s+time(?:\s+.*)?$",
             lambda m: make_atom("dialogue_state", neg=False)),

    # dialogue_input
    rule("dialogue_input", rf"^inputs\s+.*$", lambda m: make_atom("dialogue_input")),
    pre_rule("dialogue_input", rf"^inputting .*$", lambda m: make_atom("dialogue_input")),

    # --- has_talked_to ---
    rule("has_talked_to", rf"^{NEG}(?:have|has)\s+(?:talked|spoken)\s+to\s+.*$",
         lambda m: make_atom("has_talked_to", neg=bool(m.groupdict().get("neg")))),
    rule("has_talked_to", rf"^(?:has|have)\s+not\s+yet\s+(?:talked|spoken)\s+to\s+.*$",
         lambda m: make_atom("has_talked_to", neg=True)),
    rule("has_talked_to", rf"^(?:has|have)\s+already\s+(?:talked|spoken)\s+to\s+.*$",
         lambda m: make_atom("has_talked_to", neg=False)),

    # talking_to
    pre_rule("talking_to", rf"^if (?:speaking|talking)\s+to\s+.*$", lambda m: make_atom("talking_to")),
    pre_rule("talking_to", rf"^(?:if\s+)?speaking again$", lambda m: make_atom("talking_to")),

    # --- npc_role / npc_thought ---
    pre_rule("npc_role", rf"^if (?:\w+|\{{npc\}}|\{{monster\}}) is (?:not\s+)?(?:the\s+)?(?P<role>{_NPC_ROLES})(?:\s+.*)?$",
             lambda m: make_atom("npc_role", neg="not " in m.string)),
    rule("npc_role", rf"^(?:\w+|\{{npc\}}|\{{monster\}}) is (?:not\s+)?(?:the\s+)?(?P<role>{_NPC_ROLES})(?:\s+.*)?$",
         lambda m: make_atom("npc_role", neg="not " in m.string[:m.end()])),
    rule("npc_thought", rf"^(?:previously\s+)?thought the player was .*$", lambda m: make_atom("npc_thought")),

    # --- non_predicate ---
    rule("non_predicate", r"^(?:dialogue\s+\d+|otherwise|else|first time(?:\s+dialogue)?|continued|cont\.|laugh|blow kiss|alternative.*)$",
         lambda m: make_atom("non_predicate", kind="marker")),
    rule("non_predicate", r"^\{npc\}$", lambda m: make_atom("non_predicate", kind="speaker")),
    pre_rule("non_predicate", r"^(?:dialogue\s+\d+|otherwise|else|first time(?:\s+dialogue)?|continued|cont\.|laugh|blow kiss|bar item request)$",
             lambda m: make_atom("non_predicate", kind="marker")),
    pre_rule("non_predicate", r"^(?:if\s+)?(?:first\s+time\s+speaking|subsequent\s+times?|not\s+selected|if\s+selected)$",
             lambda m: make_atom("non_predicate", kind="marker")),
    pre_rule("non_predicate", r"^(?:beckon|bow|clap|cry|dance|wave|think|shrug|cheer|laugh|yes|no|angry|salute|jig|spin|headbang|yawn|panic|raspberry|blow kiss)$",
             lambda m: make_atom("non_predicate", kind="emote")),
    pre_rule("non_predicate", r"^sometimes (?:the following )?dialogue is (?:also )?added$", lambda m: make_atom("non_predicate", kind="marker")),
    pre_rule("non_predicate", r"^after a full proper greeting$", lambda m: make_atom("non_predicate", kind="marker")),

    # meta_predicate
    rule("meta_predicate", rf"^(?:does not |do not |has not |have not )?(?:satisfy|meet)\s+.*$", lambda m: make_atom("meta_predicate")),
    rule("meta_predicate", rf"^meets?\s+the\s+(?:quest\s+)?requirements(?:\s+.*)?$", lambda m: make_atom("meta_predicate")),

    # time_out
    rule("time_out", rf"^ran out of time$", lambda m: make_atom("time_out")),
    rule("time_out", rf"^does not respond in time$", lambda m: make_atom("time_out")),
    rule("time_out", rf"^do not respond in time$", lambda m: make_atom("time_out")),
]
