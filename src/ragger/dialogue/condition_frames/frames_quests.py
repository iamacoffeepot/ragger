"""Quest state and quest decision frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import FrameRule, make_atom, pre_rule, rule


def _quest_state(state: str, neg: bool) -> "Atom":  # noqa: F821
    return make_atom("quest_state", state=state, neg=neg)


NEG = r"(?P<neg>does not |do not |is not |are not |has not |have not |did not |not )?"

RULES: list[FrameRule] = [
    rule("quest_state", rf"^(?:has|have)\s+(?:not\s+)?(?P<verb>completed|finished)\s+(?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("completed", "not" in m.string[:m.end("verb")])),
    rule("quest_state", rf"^(?:has|have)\s+(?:not\s+)?started\s+(?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("started", "not" in m.string[:m.end()])),
    rule("quest_state", rf"^{NEG}(?:completed|finished)\s+(?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("completed", bool(m.groupdict().get("neg")))),
    rule("quest_state", rf"^{NEG}started\s+(?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("started", bool(m.groupdict().get("neg")))),
    rule("quest_state", rf"^did not (?:complete|finish|start) (?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("completed", True)),
    rule("quest_state", rf"^(?P<quest>\{{quest\}})\s+quest\s+has\s+(?:not\s+)?been\s+(?P<state>completed|started)$",
         lambda m: _quest_state(m.group("state"), False)),
    rule("quest_state", rf"^(?P<quest>\{{quest\}})\s+is\s+started(?:\s+and\s+in\s+progress)?$",
         lambda m: _quest_state("started", False)),
    rule("quest_state", rf"^(?:has\s+|have\s+)?(?:not\s+)?completed (?:the\s+)?(?P<quest>\{{quest\}})\s+quest$",
         lambda m: _quest_state("completed", "not " in m.string[:m.end()])),
    rule("quest_state", rf"^(?P<quest>\{{quest\}})\s+(?:is\s+|has\s+been\s+)?completed$",
         lambda m: _quest_state("completed", False)),
    rule("quest_state", rf"^(?P<quest>\{{quest\}})\s+has\s+(?:not\s+)?been\s+(?P<state>started|completed)$",
         lambda m: _quest_state(m.group("state"), True)),
    rule("quest_state", rf"^(?P<quest>\{{quest\}})\s+is\s+not\s+completed$",
         lambda m: _quest_state("completed", True)),
    rule("quest_state", rf"^before\s+(?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("completed", True)),
    rule("quest_state", rf"^after\s+(?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("completed", False)),
    rule("quest_state", rf"^during\s+(?:the\s+)?(?P<quest>\{{quest\}})$",
         lambda m: _quest_state("in_progress", False)),

    # quest_decision
    rule("quest_decision", rf"^(?:has\s+)?helped\s+.*$", lambda m: make_atom("quest_decision", action="helped")),
    rule("quest_decision", rf"^(?:has\s+)?sided\s+with\s+.*$", lambda m: make_atom("quest_decision", action="sided")),
    rule("quest_decision", rf"^(?:has\s+)?opposed\s+.*$", lambda m: make_atom("quest_decision", action="opposed")),

    # diary_completed
    pre_rule("diary_completed",
             rf"^(?:if\s+)?(?:the\s+)?player\s+has\s+(?:not\s+)?completed\s+the\s+.*task\s+set(?:\s+.*)?$",
             lambda m: make_atom("diary_completed", neg="not " in m.string)),
]
