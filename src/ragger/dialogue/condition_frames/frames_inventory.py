"""Inventory space frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import COUNT, FrameRule, NEG, make_atom, pre_rule, rule

INV_COUNT = r"(?P<count>no|any|a|enough|one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
INV_CMP = r"(?:at least |at most |exactly |more than |less than |only )?"
INV_NOUN = r"inventory\s+(?:space|slots?|spaces?)"
ROOM_NOUN = r"(?:enough\s+)?(?:room|space)\s+in\s+(?:their\s+|the player's\s+)?inventory"


def _inv_space(m) -> "Atom":  # noqa: F821
    gd = m.groupdict()
    raw = gd.get("count")
    if raw in ("no", "any"):
        count = 0 if "neg" not in gd or not gd["neg"] else 1
    elif raw == "enough":
        count = 1
    elif raw and raw.isdigit():
        count = int(raw)
    else:
        count = 1
    return make_atom("inventory_space", count=count, neg=bool(gd.get("neg")))


RULES: list[FrameRule] = [
    rule("inventory_space", rf"^{NEG}(?:have|has)\s+{INV_CMP}{INV_COUNT}?\s*(?:free\s+)?{INV_NOUN}(?:\s+.*)?$", _inv_space),
    rule("inventory_space", rf"^{NEG}(?:have|has)\s+{ROOM_NOUN}(?:\s+.*)?$", _inv_space),
    rule("inventory_space", rf"^(?:'s\s+)?inventory\s+is\s+(?:not\s+)?full$",
         lambda m: make_atom("inventory_space", count=0, neg="not " in m.string)),
    rule("inventory_space", rf"^{NEG}(?:have|has)\s+no\s+(?:free\s+)?{INV_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("inventory_space", count=0, neg=False)),
    rule("inventory_space", rf"^{NEG}(?:have|has)\s+no\s+{ROOM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("inventory_space", count=0, neg=False)),
    rule("inventory_space", rf"^{NEG}(?:have|has)\s+(?:an?\s+)?open\s+{INV_NOUN}(?:\s+.*)?$", _inv_space),
    rule("inventory_space", rf"^{NEG}(?:have|has)\s+(?:no\s+)?room\s+in\s+(?:the\s+)?inventory(?:\s+.*)?$",
         lambda m: make_atom("inventory_space", count=0, neg="no " in m.string or bool(m.groupdict().get("neg")))),
    rule("inventory_space", rf"^{NEG}(?:have|has)\s+{COUNT}\s+(?:empty\s+|free\s+|open\s+)?{INV_NOUN}(?:\s+.*)?$", _inv_space),
    rule("inventory_space", rf"^(?P<count>\d+)\s+or\s+more\s+{INV_NOUN}\s+(?:open|free|available)(?:\s+.*)?$", _inv_space),
    rule("inventory_space", rf"^free\s+inventory\s+(?:space|slots?)$", lambda m: make_atom("inventory_space", count=1, neg=False)),
    rule("inventory_space", rf"^(?:has\s+|have\s+)?(?:a\s+)?full inventory$", lambda m: make_atom("inventory_space", count=0, neg=False)),
    rule("inventory_space", rf"^(?:has\s+|have\s+)?insufficient inventory (?:space|slots?)$", lambda m: make_atom("inventory_space", count=1, neg=True)),
    rule("inventory_space", rf"^(?:has\s+|have\s+)sufficient inventory (?:space|slots?)$", lambda m: make_atom("inventory_space", count=1, neg=False)),
    rule("inventory_space", rf"^(?:has\s+|have\s+)?open inventory (?:space|slots?)$", lambda m: make_atom("inventory_space", count=1, neg=False)),

    pre_rule("inventory_space", rf"^without free inventory (?:space|slots?)$", lambda m: make_atom("inventory_space", count=1, neg=True)),
    pre_rule("inventory_space", rf"^without enough inventory (?:space|slots?)$", lambda m: make_atom("inventory_space", count=1, neg=True)),
    pre_rule("inventory_space", rf"^with (?:a\s+)?full inventory$", lambda m: make_atom("inventory_space", count=0, neg=False)),
    pre_rule("inventory_space", rf"^with (?:open |free )?inventory (?:space|slots?)$", lambda m: make_atom("inventory_space", count=1, neg=False)),
    pre_rule("inventory_space", rf"^(?:if\s+)?the\s+inventory\s+is\s+(?:not\s+)?full(?:\s+.*)?$",
             lambda m: make_atom("inventory_space", count=0, neg="not " in m.string)),
    pre_rule("inventory_space", rf"^(?:if\s+)?there\s+is\s+(?:no\s+)?(?:free\s+|open\s+)?inventory\s+(?:space|slots?)(?:\s+.*)?$",
             lambda m: make_atom("inventory_space", count=0 if "no " in m.string else 1, neg="no " not in m.string)),
    pre_rule("inventory_space", rf"^(?:if\s+)?there\s+(?:are|is)\s+(?:no\s+|not\s+enough\s+)?(?:free\s+|open\s+)?inventory\s+(?:space|slots?)(?:\s+.*)?$",
             lambda m: make_atom("inventory_space", count=1, neg="no " in m.string or "not " in m.string)),
]
