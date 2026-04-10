"""Farming patch state, planting, and growth frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import FrameRule, ITEM_NOUN, make_atom, pre_rule, rule

RULES: list[FrameRule] = [
    # patch_state
    pre_rule("patch_state",
             rf"^(?:if\s+)?the\s+patch\s+(?:is|has)\s+(?P<state>fully\s+grown|empty|"
             rf"being\s+looked\s+after|dead\s+crops?\s+in\s+it|diseased\s+crops?\s+in\s+it|"
             rf"a\s+dead\s+plant|a\s+diseased\s+plant|a\s+fully\s+grown\s+plant|"
             rf"something\s+growing\s+in\s+it)(?:,\s+(?:un)?protected)?(?:\s+.*)?$",
             lambda m: make_atom("patch_state", state=m.group("state").strip())),
    pre_rule("patch_state", rf"^(?:if\s+)?the\s+patch\s+has\s+.*\s+planted\s+in\s+it(?:\s+.*)?$",
             lambda m: make_atom("patch_state", state="planted")),
    pre_rule("patch_state", rf"^(?:if\s+)?the\s+patch\s+protection\s+fee\s+has\s+(?:not\s+)?been\s+paid(?:\s+.*)?$",
             lambda m: make_atom("patch_state", state="protection_paid")),
    pre_rule("patch_state", rf"^(?:if\s+)?(?:\w+)\s+patches?\s+have?\s+(?:not\s+)?finished\s+growing(?:\s+.*)?$",
             lambda m: make_atom("patch_state", state="growing")),
    pre_rule("patch_state", rf"^(?:if\s+)?a\s+patch\s+has\s+not\s+finished\s+growing(?:\s+.*)?$",
             lambda m: make_atom("patch_state", state="growing")),
    pre_rule("patch_state", rf"^(?:if\s+)?\{{npc\}}\s+is\s+(?:not\s+)?looking\s+after\s+(?:that|the|this)\s+patch(?:\s+.*)?$",
             lambda m: make_atom("patch_state", state="protected")),

    # patch_planted
    rule("patch_planted", rf"^(?:has|have)\s+(?:not\s+)?planted\s+.*(?:in\s+the\s+patch|on\s+.*)?(?:\s+.*)?$",
         lambda m: make_atom("patch_planted", neg="not " in m.string[:m.end()])),
    pre_rule("patch_planted",
             rf"^(?:if\s+)?(?:a |an |no |any )?(?:\{{item\}}\s+)?(?:sapling|bush|tree|seedling)?\s*(?:is\s+)?planted\s+in\s+the\s+(?:patch|redwood\s+patch)(?:\s+.*)?$",
             lambda m: make_atom("patch_planted", neg="no " in m.string[:20])),
    pre_rule("patch_planted", rf"^(?:if\s+)?no\s+(?:sapling|tree|bush|crop)\s+is\s+planted\s+in\s+the\s+patch(?:\s+.*)?$",
             lambda m: make_atom("patch_planted", neg=True)),
    pre_rule("patch_planted", rf"^(?:if\s+)?(?:a |an )\{{item\}}\s+is\s+(?:planted|growing)\s+in\s+the\s+patch(?:\s+.*)?$",
             lambda m: make_atom("patch_planted", neg=False)),
    rule("patch_planted", rf"^(?:has|have)\s+(?:not\s+)?(?:something|anything|no\s+crops?)\s+planted(?:\s+.*)?$",
         lambda m: make_atom("patch_planted", neg="not " in m.string[:m.end()] or "no " in m.string[:m.end()])),
    rule("patch_planted", rf"^(?:has|have)\s+(?:not\s+)?planted\s+(?:a |an |the )?(?:\{{item\}}|seedling|sapling)(?:\s+.*)?$",
         lambda m: make_atom("patch_planted", neg="not " in m.string[:m.end()])),

    # patch_grown
    rule("patch_grown", rf"^(?:has|have)\s+(?:not\s+)?(?:fully\s+)?grown\s+.*$",
         lambda m: make_atom("patch_grown", neg="not " in m.string[:m.end()])),
    rule("patch_grown", rf"^fully\s+grown\s+.*$", lambda m: make_atom("patch_grown", neg=False)),
    pre_rule("patch_grown",
             rf"^(?:if\s+)?the\s+(?:crop|planted\s+crop|{ITEM_NOUN})\s+has\s+(?:completed\s+growing|died|finished\s+growing)(?:\s+.*)?$",
             lambda m: make_atom("patch_grown", state="completed" if "died" not in m.string else "died")),
    pre_rule("patch_grown", rf"^(?:if\s+)?the\s+planted\s+crop\s+is\s+diseased(?:\s+.*)?$",
             lambda m: make_atom("patch_grown", state="diseased")),
    pre_rule("patch_grown",
             rf"^(?:if\s+)?(?:a |the )?sapling\s+planted\s+in\s+the\s+patch\s+has\s+(?P<state>matured|died|become\s+diseased)(?:\s+.*)?$",
             lambda m: make_atom("patch_grown", state=m.group("state").strip())),
]
