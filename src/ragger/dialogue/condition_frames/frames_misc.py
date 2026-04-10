"""Miscellaneous frames: gender, ownership, follower, build, etc."""
from __future__ import annotations

from ragger.dialogue.condition_types import FrameRule, NEG, make_atom, pre_rule, rule

RULES: list[FrameRule] = [
    # gender
    rule("gender", rf"^(?:gender|character)\s+is\s+(?P<gender>male|female)$",
         lambda m: make_atom("gender", gender=m.group("gender"))),
    rule("gender", rf"^is\s+(?P<gender>male|female)$",
         lambda m: make_atom("gender", gender=m.group("gender"))),
    rule("gender", rf"^changed their gender from (?:male|female) to (?P<gender>male|female)$",
         lambda m: make_atom("gender", gender=m.group("gender"))),

    # owns
    rule("owns", rf"^{NEG}(?:does\s+)?own(?:s)?\s+(?:a |an |any )?(?P<thing>\w+(?:\s+\w+)*)(?:\s+.*)?$",
         lambda m: make_atom("owns", neg=bool(m.groupdict().get("neg")) or "not " in m.string[:m.end()])),

    # has_follower (generic)
    rule("has_follower", rf"^{NEG}(?:have|has)\s+(?:a |no )?(?:different\s+)?(?:pet\s+)?follower(?:\s+.*)?$",
         lambda m: make_atom("has_follower", neg=bool(m.groupdict().get("neg")) or "no " in m.string[:m.end()])),
    rule("has_follower", rf"^{NEG}(?:have|has)\s+a\s+(?:pet\s+)?(?:following\s+them|follower)(?:\s+.*)?$",
         lambda m: make_atom("has_follower", neg=bool(m.groupdict().get("neg")))),
    rule("has_follower", rf"^{NEG}(?:have|has)\s+(?:a |the )?pet\s+following\s+them(?:\s+.*)?$",
         lambda m: make_atom("has_follower", neg=bool(m.groupdict().get("neg")))),
    # has_follower (NPC/monster specific)
    rule("has_follower", rf"^{NEG}(?:have|has)\s+(?:a |the )?(?P<npc>\{{npc\}}|\{{monster\}})\s+(?:following|with)\s+(?:them|him|her)?\s*(?:\s+.*)?$",
         lambda m: make_atom("has_follower", neg=bool(m.groupdict().get("neg")))),
    rule("has_follower", rf"^(?P<npc>\{{npc\}}|\{{monster\}})\s+is\s+(?:not\s+)?(?:with|following)\s+(?:the\s+)?player(?:\s+.*)?$",
         lambda m: make_atom("has_follower", neg="not " in m.string[:m.end()])),
    rule("has_follower", rf"^{NEG}(?:have|has)\s+a\s+cat\s+following\s+them$",
         lambda m: make_atom("has_follower", neg=bool(m.groupdict().get("neg")))),
    pre_rule("has_follower", rf"^if (?P<npc>\{{npc\}}|\{{monster\}}) is (?:not\s+)?(?:with|following) (?:the\s+)?player(?:\s+.*)?$",
             lambda m: make_atom("has_follower", neg="not " in m.string)),
    pre_rule("has_follower", rf"^(?:if\s+)?(?:the\s+)?(?:\{{item\}}|\{{monster\}}|\{{npc\}}|\w+)\s+is\s+(?:not\s+)?following\s+the\s+player(?:\s+.*)?$",
             lambda m: make_atom("has_follower", neg="not " in m.string)),
    pre_rule("has_follower", rf"^(?:if\s+)?(?:the\s+)?(?:\{{item\}}|\{{monster\}}|\{{npc\}}|\w+)\s+was\s+(?:not\s+)?following\s+the\s+player(?:\s+.*)?$",
             lambda m: make_atom("has_follower", neg="not " in m.string)),

    # has_chosen
    rule("has_chosen", rf"^(?:has|have)\s+(?:not\s+)?chosen\s+.*$",
         lambda m: make_atom("has_chosen", neg="not " in m.string[:m.end()])),

    # needs_to_build (POH)
    rule("needs_to_build", rf"^(?:has|have|needs|need)\s+to build (?:a |an |the )?\w+(?:\s+\w+)*$",
         lambda m: make_atom("needs_to_build", neg=False)),
    rule("needs_to_build", rf"^(?:has|have|needs|need)\s+to build (?:a |an |the )?\w+(?:\s+\w+)*\s+.*$",
         lambda m: make_atom("needs_to_build", neg=False)),

    # cast_count
    rule("cast_count", rf"^(?:has|have)\s+cast\s+.*\s+times$", lambda m: make_atom("cast_count")),
    rule("cast_count", rf"^(?:has|have)\s+cast\s+\{{wiki\}}.*$", lambda m: make_atom("cast_count")),
]
