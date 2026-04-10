"""Task assignment, port task, rumour, and task progress frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import FrameRule, NEG, make_atom, pre_rule, rule

RULES: list[FrameRule] = [
    # has_assignment (slayer / skill tasks)
    rule("has_assignment", rf"^{NEG}(?:have|has)\s+an? assignment$",
         lambda m: make_atom("has_assignment", neg=bool(m.groupdict().get("neg")))),
    rule("has_assignment", rf"^{NEG}(?:have|has)\s+a current assignment$",
         lambda m: make_atom("has_assignment", neg=bool(m.groupdict().get("neg")))),
    rule("has_assignment", rf"^{NEG}(?:have|has)\s+(?:.*?)\s+as\s+a\s+\{{skill\}}\s+task(?:\s+.*)?$",
         lambda m: make_atom("has_assignment", neg=bool(m.groupdict().get("neg")))),
    rule("has_assignment", rf"^{NEG}(?:have|has)\s+a\s+\{{skill\}}\s+task(?:\s+.*)?$",
         lambda m: make_atom("has_assignment", neg=bool(m.groupdict().get("neg")))),
    rule("has_assignment", rf"^was\s+already\s+assigned\s+a\s+task(?:\s+.*)?$",
         lambda m: make_atom("has_assignment", neg=False)),
    rule("has_assignment", rf"^already\s+(?:has|have)\s+a\s+task(?:\s+.*)?$",
         lambda m: make_atom("has_assignment", neg=False)),
    rule("has_assignment", rf"^(?:has|have)\s+no\s+active\s+tasks?(?:\s+.*)?$",
         lambda m: make_atom("has_assignment", neg=True)),
    rule("has_assignment", rf"^(?:has|have)\s+one\s+or\s+more\s+active\s+tasks?(?:\s+.*)?$",
         lambda m: make_atom("has_assignment", neg=False)),
    rule("has_assignment", rf"^needs\s+to\s+be\s+reminded\s+of\s+the\s+task(?:\s+.*)?$",
         lambda m: make_atom("has_assignment", neg=False)),
    pre_rule("has_assignment", rf"^(?:if\s+)?the\s+assignment\s+is\s+(?:not\s+)?on\s+.*task\s+.*$",
             lambda m: make_atom("has_assignment", neg="not " in m.string)),

    # port_task
    rule("port_task", rf"^(?:has|have)\s+(?:not\s+)?(?:a\s+)?completed\s+port\s+tasks?(?:\s+.*)?$",
         lambda m: make_atom("port_task", state="completed", neg="not " in m.string[:20])),
    rule("port_task", rf"^(?:has|have)\s+no\s+completed\s+port\s+tasks?(?:\s+.*)?$",
         lambda m: make_atom("port_task", state="completed", neg=True)),
    rule("port_task", rf"^(?:has|have)\s+max\s+port\s+tasks?\s+taken(?:\s+.*)?$",
         lambda m: make_atom("port_task", state="max_taken", neg=False)),

    # task_progress
    rule("task_progress",
         rf"^(?:has|have)\s+(?:not\s+)?completed\s+(?:some|zero|few|many|enough|all|\d+)\s+tasks\s+for\s+(?:the\s+)?(?P<npc>\{{npc\}}|director)(?:\s+.*)?$",
         lambda m: make_atom("task_progress", neg="not " in m.string[:m.end()])),

    # has_rumour
    rule("has_rumour", rf"^{NEG}(?:have|has)\s+a rumour$",
         lambda m: make_atom("has_rumour", neg=bool(m.groupdict().get("neg")))),

    # all_completed
    rule("all_completed", rf"^(?:has|have)\s+(?:not\s+)?completed\s+(?:all|every)(?:\s+.*)?$",
         lambda m: make_atom("all_completed", neg="not " in m.string[:20])),
]
