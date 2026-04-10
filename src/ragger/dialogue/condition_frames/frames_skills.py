"""Skill level, combat level, and monster skill check frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import FrameRule, NEG, make_atom, rule


def _skill_ge(m) -> "Atom":  # noqa: F821
    return make_atom("skill_ge", level=int(m.group("level")), neg=bool(m.groupdict().get("neg")))


RULES: list[FrameRule] = [
    rule("skill_ge", rf"^{NEG}(?:have|has)\s+(?:at least |level )?(?P<level>\d+)\s+\{{skill\}}$", _skill_ge),
    rule("skill_ge", rf"^{NEG}(?:have|has)\s+at least level (?P<level>\d+)\s+\{{skill\}}$", _skill_ge),
    rule("skill_ge", rf"^\{{skill\}}\s+level\s+(?:is\s+)?(?P<level>\d+)\s+(?:or\s+)?(?:higher|above|more)$", _skill_ge),
    rule("skill_ge", rf"^\{{skill\}}\s+level\s+is\s+(?P<level>\d+)$", _skill_ge),
    rule("skill_ge", rf"^lacks the required \{{skill\}} level$", lambda m: make_atom("skill_ge", level=0, neg=True)),
    rule("skill_ge", rf"^is\s+level\s+(?P<level>\d+)\s+or\s+(?:above|higher|more)\s+in\s+\{{skill\}}$", _skill_ge),
    rule("skill_ge", rf"^is\s+below\s+level\s+(?P<level>\d+)\s+in\s+\{{skill\}}$",
         lambda m: make_atom("skill_ge", level=int(m.group("level")), neg=True)),
    rule("skill_ge", rf"^\{{skill\}}\s+level\s+is\s+at\s+least\s+(?P<level>\d+)(?:\s+.*)?$", _skill_ge),
    rule("skill_ge", rf"^\{{skill\}}\s+level\s+is\s+too\s+low(?:\s+.*)?$", lambda m: make_atom("skill_ge", level=0, neg=True)),

    rule("combat_level", rf"^(?:has\s+a\s+)?combat\s+level\s+(?:is\s+)?(?:less|lower)\s+than\s+(?P<level>\d+)(?:\s+.*)?$",
         lambda m: make_atom("combat_level", level=int(m.group("level")), cmp="lt")),
    rule("combat_level", rf"^(?:has\s+a\s+)?combat\s+level\s+(?:is\s+)?(?:at\s+least|above|higher\s+than)\s+(?P<level>\d+)(?:\s+.*)?$",
         lambda m: make_atom("combat_level", level=int(m.group("level")), cmp="ge")),
    rule("combat_level", rf"^(?:has\s+a\s+)?combat\s+level\s+(?:of\s+)?(?P<level>\d+)\s+or\s+(?:above|higher|more)(?:\s+.*)?$",
         lambda m: make_atom("combat_level", level=int(m.group("level")), cmp="ge")),

    rule("monster_skill_check", rf"^\{{monster\}}\s+has\s+a\s+\{{skill\}}\s+level\s+of\s+(?P<level>\d+)(?:\s+.*)?$",
         lambda m: make_atom("monster_skill_check")),
]
