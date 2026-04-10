"""World state, location, account, membership, and proximity frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import FrameRule, NEG, make_atom, pre_rule, rule

WORLD_KIND = (
    r"(?P<wtype>"
    r"pvp|pking|members?'?|free.to.play|f2p|deadman|"
    r"quest speedrunning|speedrunning|soul wars|"
    r"\{wiki\}(?:-only)?"
    r")"
)

RULES: list[FrameRule] = [
    # location_at
    rule("location_at", rf"^{NEG}(?:is\s+)?(?:in|at|on|near)\s+(?:the\s+)?(?P<loc>\{{location\}})\s*.*$",
         lambda m: make_atom("location_at", neg=bool(m.groupdict().get("neg")))),
    rule("location_at", rf"^at\s+(?:the\s+)?(?P<loc>\{{location\}})$", lambda m: make_atom("location_at", neg=False)),
    rule("location_at", rf"^from\s+(?:the\s+)?(?P<loc>\{{location\}})$", lambda m: make_atom("location_at", neg=False)),

    # proximity_check
    pre_rule("proximity_check", rf"^(?:if\s+)?(?:the\s+)?player\s+is\s+(?:not\s+)?within\s+.*(?:of|from)\s+.*$",
             lambda m: make_atom("proximity_check", neg="not " in m.string)),
    pre_rule("proximity_check", rf"^(?:if\s+)?(?:the\s+)?player\s+is\s+(?:not\s+)?(?:near|close to|far from|at)\s+.*$",
             lambda m: make_atom("proximity_check", neg="not " in m.string)),

    # npc_at_location
    pre_rule("npc_at_location", rf"^(?:if\s+)?(?:\{{npc\}}|\{{monster\}})\s+is\s+(?:not\s+)?(?:at|in|near)\s+(?:the\s+)?\{{location\}}(?:\s+.*)?$",
             lambda m: make_atom("npc_at_location", neg="not " in m.string)),

    # member_only / ironman
    rule("member_only", rf"^{NEG}(?:is\s+)?(?:a\s+)?member$",
         lambda m: make_atom("member_only", neg=bool(m.groupdict().get("neg")))),
    rule("member_only", rf"^{NEG}(?:is\s+)?on\s+a (?:free.*to.*play|members?) world$",
         lambda m: make_atom("member_only", neg=bool(m.groupdict().get("neg")))),
    rule("member_only", rf"^(?:is\s+)?an? ironman$", lambda m: make_atom("ironman", neg=False)),
    rule("member_only", rf"^(?:is\s+)?an? ultimate ironman$", lambda m: make_atom("ironman_ultimate", neg=False)),

    # account_state
    rule("account_state", rf"^(?:has|have)\s+(?:set\s+up\s+|disabled\s+)?(?:a\s+)?(?:bank pin|authenticator|jagex account|combat checking)(?:\s+.*)?$",
         lambda m: make_atom("account_state")),
    rule("account_state", rf"^(?:is|are)\s+playing\s+on\s+(?:a\s+)?(?:jagex account|desktop|mobile)(?:\s+.*)?$",
         lambda m: make_atom("account_state")),
    pre_rule("account_state", rf"^if playing on (?:a\s+)?(?:jagex account|desktop|mobile)$", lambda m: make_atom("account_state")),
    pre_rule("account_state", rf"^(?:if\s+)?(?:not\s+)?restricted\s+from\s+trading(?:\s+.*)?$", lambda m: make_atom("account_state")),
    pre_rule("account_state", rf"^(?:if\s+)?plying\s+on\s+mobile$", lambda m: make_atom("account_state")),

    # world_type
    rule("world_type", rf"^{NEG}(?:is\s+)?on a {WORLD_KIND}\s+world(?:\s+.*)?$",
         lambda m: make_atom("world_type", wtype=m.group("wtype"), neg=bool(m.groupdict().get("neg")))),
    rule("world_type", rf"^{NEG}(?:is\s+)?on the {WORLD_KIND}\s+world(?:\s+.*)?$",
         lambda m: make_atom("world_type", wtype=m.group("wtype"), neg=bool(m.groupdict().get("neg")))),
    pre_rule("world_type", rf"^on (?:a|the) {WORLD_KIND}(?:\s+(?:or|and)\s+\w+)?\s+world(?:\s+.*)?$",
             lambda m: make_atom("world_type", wtype=m.group("wtype"), neg=False)),
    rule("world_type", rf"^(?:is\s+)?playing on (?:a|the) {WORLD_KIND}\s+world(?:\s+.*)?$",
         lambda m: make_atom("world_type", wtype=m.group("wtype"), neg=False)),

    # in_combat
    rule("in_combat", rf"^{NEG}(?:is\s+)?engaged$", lambda m: make_atom("in_combat", neg=bool(m.groupdict().get("neg")))),
    rule("in_combat", rf"^{NEG}(?:is\s+)?in combat$", lambda m: make_atom("in_combat", neg=bool(m.groupdict().get("neg")))),

    # world_state (opaque clusters)
    pre_rule("world_state", rf"^(?:if\s+)?(?:the\s+)?(?:player's\s+)?chosen boat .*$", lambda m: make_atom("world_state", kind="sailing_boat")),
    pre_rule("world_state", rf"^(?:if\s+)?sailing level is too low$", lambda m: make_atom("world_state", kind="sailing_level")),
    pre_rule("world_state", rf"^(?:if\s+)?(?:the\s+)?hat is attuned .*$", lambda m: make_atom("world_state", kind="skotizo_hat")),
    pre_rule("world_state", rf"^(?:if\s+)?(?:the\s+)?(?:player's\s+)?house is (?:decorated|currently located) .*$", lambda m: make_atom("world_state", kind="house_state")),
    pre_rule("world_state", rf"^(?:if\s+)?upon spawning .*$", lambda m: make_atom("world_state", kind="spawn_state")),
    pre_rule("world_state", rf"^(?:if\s+)?(?:while\s+)?waiting for a response .*$", lambda m: make_atom("world_state", kind="dialogue_wait")),
]
