"""Wearing / equipment frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import (
    FrameRule,
    ITEM_NOUN,
    NEG,
    make_atom,
    pre_rule,
    rule,
)


def _wearing(m) -> "Atom":  # noqa: F821
    return make_atom("wearing", neg=bool(m.groupdict().get("neg")))


WEAR_NOUN = (
    r"(?P<item>"
    r"(?:full |broken |proper |chosen |selected )?"
    r"(?:\{item\}|\{equipment\}|\{monster\}(?:'s)?)"
    r"(?:\s+\w+)*"
    r")"
)

EQUIP_SLOT = (
    r"(?P<slot>head|helmet|cape|gloves|weapon|ammunition|shield|ring|"
    r"amulet|boots|legs|body|hands|feet|arrow|neck)"
)

RULES: list[FrameRule] = [
    # wearing_either
    rule("wearing_either", rf"^(?:is\s+)?(?:not\s+)?wearing\s+either$",
         lambda m: make_atom("wearing_either", neg="not " in m.string[:m.end()])),

    # Core wearing
    rule("wearing", rf"^{NEG}(?:is\s+)?wearing\s+(?:a |an |the )?{WEAR_NOUN}(?:\s+.*)?$", _wearing),
    rule("wearing", rf"^{NEG}(?:is\s+)?wielding\s+(?:a |an |the )?{WEAR_NOUN}(?:\s+.*)?$", _wearing),
    rule("wearing", rf"^{NEG}(?:have|has)\s+(?:a |an |the )?{WEAR_NOUN}\s+equipped(?:\s+.*)?$", _wearing),
    rule("wearing", rf"^(?:a |an |the )?{WEAR_NOUN}\s+equipped(?:\s+.*)?$", lambda m: make_atom("wearing", neg=False)),

    # Equipment slot
    rule("wearing",
         rf"^(?:is\s+)?{NEG}wearing\s+(?:an?\s+)?(?:item|something|anything|nothing)\s+"
         rf"(?:on\s+(?:their\s+)?|in\s+(?:the\s+)?){EQUIP_SLOT}(?:\s+slot)?(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=bool(m.groupdict().get("neg")) or "nothing" in m.string, slot=m.group("slot"))),
    rule("wearing",
         rf"^{NEG}(?:have|has)\s+(?:something|anything|nothing)\s+equipped\s+"
         rf"in\s+(?:the\s+)?{EQUIP_SLOT}(?:\s+(?:or\s+\w+\s+)?slot)?(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=bool(m.groupdict().get("neg")) or "nothing" in m.string, slot=m.group("slot"))),
    rule("wearing",
         rf"^{NEG}(?:have|has)\s+(?:anything|something|nothing)\s+equipped\s+"
         rf"in\s+(?:the\s+)?(?:\w+\s+or\s+)?{EQUIP_SLOT}(?:\s+slot)?(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=bool(m.groupdict().get("neg")), slot=m.group("slot"))),
    rule("wearing",
         rf"^{NEG}(?:have|has)\s+(?:anything|something)\s+equipped\s+"
         rf"in\s+(?:the\s+)?(?P<slot1>\w+)\s+or\s+(?P<slot2>\w+)\s+slot(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=bool(m.groupdict().get("neg")), slot=m.group("slot1"))),
    rule("wearing",
         rf"^(?:is\s+)?wearing\s+something\s+in\s+(?:the\s+)?{EQUIP_SLOT}(?:\s+slot)?(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=False, slot=m.group("slot"))),

    # Category/set
    rule("wearing",
         rf"^{NEG}(?:is\s+)?wearing\s+(?:a |an |the |full )?(?P<cat>\w+)\s+"
         rf"(?:\{{item\}}|\{{equipment\}}|robes|armour|armor|outfit|clothing|gloves|boots|items?)(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=bool(m.groupdict().get("neg")), category=m.group("cat"))),
    rule("wearing",
         rf"^{NEG}(?:is\s+)?wearing\s+equipment\s+aligned\s+with\s+(?P<cat>\w+)(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=bool(m.groupdict().get("neg")), category=m.group("cat"))),
    rule("wearing",
         rf"^{NEG}(?:is\s+)?wearing\s+(?:the\s+)?\{{npc\}}'?s?\s+"
         rf"(?:robes|armour|armor|outfit|clothing)(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg=bool(m.groupdict().get("neg")), category="npc_set")),
    rule("wearing",
         rf"^{NEG}(?:is\s+)?(?:not\s+)?wearing\s+(?:at\s+least\s+)?(?P<count>\d+)\s+"
         rf"(?P<cat>\w+(?:[- ]\w+)?)\s+items?(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg="not " in m.string[:m.end()], category=m.group("cat"))),

    # Passive
    rule("wearing",
         rf"^(?:a |an |the )?{ITEM_NOUN}\s+is\s+(?:not\s+)?(?:worn|equipped)(?:\s+.*)?$",
         lambda m: make_atom("wearing", neg="not " in m.string)),
    rule("wearing", rf"^(?:is\s+)?wearing\s+nothing(?:\s+.*)?$", lambda m: make_atom("wearing", neg=True)),

    # with/without equipped
    pre_rule("wearing", rf"^with (?:the |a |an )?(?:full |broken )?\w+(?:\s+\w+)*\s+equipped(?:\s+.*)?$", lambda m: make_atom("wearing", neg=False)),
    pre_rule("wearing", rf"^without (?:the |a |an )?(?:full |broken )?\w+(?:\s+\w+)*\s+equipped(?:\s+.*)?$", lambda m: make_atom("wearing", neg=True)),
]
