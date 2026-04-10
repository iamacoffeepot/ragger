"""Event, gerund trigger, and past-tense action frames."""
from __future__ import annotations

import re

from ragger.dialogue.condition_types import (
    FrameRule,
    ITEM_NOUN_NC,
    make_atom,
    pre_rule,
    rule,
)

# ---------------------------------------------------------------------------
# Present-tense event verbs
# ---------------------------------------------------------------------------

EVENT_VERBS = [
    "attempts to", "uses", "kills", "defeats", "talks to",
    "speaks to", "interacts with", "searches", "takes",
    "picks up", "drops", "gives", "shows", "examines",
    "chooses", "selects", "tries to", "asks", "loses",
    "burns", "grinds", "inserts",
]

_GERUND_VERBS = (
    "buying|adding|handing|inspecting|strapping|studying|"
    "searching|defeating|arriving|failing|choosing|distracting|"
    "enabling|disabling|entering|climbing|opening|crafting|"
    "pickpocketing|praying|mining|smelting|cutting|spinning|"
    "planting|harvesting|building|repairing|lighting"
)

# ---------------------------------------------------------------------------
# Past-tense verbs for has_event_action (catch-all — registered LAST)
# ---------------------------------------------------------------------------

EVENT_VERBS_PAST = [
    "enabled", "disabled", "given", "earned", "spent", "claimed",
    "destroyed", "filled", "subdued", "found", "discovered",
    "unlocked", "activated", "deactivated", "purchased", "bought",
    "solved", "defeated", "killed", "freed", "rescued", "saved",
    "started", "asked", "told", "handed", "shown", "delivered",
    "inserted", "placed", "collected", "retrieved", "obtained",
    "returned", "lost", "stolen", "traded", "questioned",
    "completed", "finished", "reached", "visited",
]

_EVENT_VERB_ALT = "|".join(EVENT_VERBS_PAST)

# ---------------------------------------------------------------------------
# Build rule list
# ---------------------------------------------------------------------------

RULES: list[FrameRule] = []

# Present-tense event verbs
for _verb in EVENT_VERBS:
    _pat = re.escape(_verb)
    RULES.append(rule("event", rf"^{_pat}\s+.*$", (lambda v: lambda m: make_atom("event", verb=v))(_verb)))

RULES += [
    rule("event", rf"^after\s+\w+ing\s+.*$", lambda m: make_atom("event", verb="after")),
    rule("event", rf"^when\s+\w+ing\s+.*$", lambda m: make_atom("event", verb="when")),
    rule("event", rf"^before\s+\w+ing\s+.*$", lambda m: make_atom("event", verb="before")),
    rule("event", rf"^using\s+.*$", lambda m: make_atom("event", verb="using")),

    # Passive event: "before/after the {item} has been inserted"
    pre_rule("event",
             rf"^(?:if\s+)?(?:before|after)\s+(?:the\s+)?{ITEM_NOUN_NC}\s+has\s+been\s+\w+(?:\s+.*)?$",
             lambda m: make_atom("event", verb="before" if "before" in m.string[:10] else "after")),

    # Gerund triggers
    rule("event", rf"^(?P<verb>{_GERUND_VERBS})\s+.*$",
         lambda m: make_atom("event", verb=m.group("verb").lower())),

    # event_past_tense
    rule("event_past_tense",
         rf"^(?:has|have)\s+(?:not\s+)?(?:trick-or-treated|filled|subdued|completed all|defeated all)\s+.*$",
         lambda m: make_atom("event_past_tense", neg="not " in m.string[:m.end()])),

    # outcome
    rule("outcome", rf"^(?:fails?|does not succeed)(?:\s+.*)?$", lambda m: make_atom("outcome", success=False)),
    rule("outcome", rf"^(?:succeeds?|successfully)(?:\s+.*)?$", lambda m: make_atom("outcome", success=True)),
    pre_rule("outcome", rf"^(?:if\s+)?(?:un)?successful(?:ly)?(?:\s+.*)?$",
             lambda m: make_atom("outcome", success="un" not in m.string[:15])),
]

# --- has_event_action (catch-all — must be registered after specific frames) ---
HAS_EVENT_ACTION_RULES: list[FrameRule] = [
    rule("has_event_action",
         rf"^(?:has|have)\s+(?:not\s+)?(?:already\s+)?(?P<verb>{_EVENT_VERB_ALT})\s+.*$",
         lambda m: make_atom("has_event_action", verb=m.group("verb"), neg="not " in m.string[:m.end()])),
    rule("has_event_action",
         rf"^(?:has|have)\s+(?:not\s+)?shown\s+.*(?:before|previously|already)(?:\s+.*)?$",
         lambda m: make_atom("has_event_action", verb="shown", neg="not " in m.string[:20])),
]
