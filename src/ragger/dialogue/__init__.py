"""Dialogue package: tree models, instruction IR, flatten, passes.

The public API of ``ragger.dialogue`` is re-exported here so existing
callers can keep writing ``from ragger.dialogue import DialoguePage``.
"""
from ragger.dialogue.dialogue_instruction import Instruction
from ragger.dialogue.dialogue_node import DialogueNode
from ragger.dialogue.dialogue_page import DialoguePage
from ragger.dialogue.dialogue_tag import DialogueTag

__all__ = [
    "DialogueNode",
    "DialoguePage",
    "DialogueTag",
    "Instruction",
]
