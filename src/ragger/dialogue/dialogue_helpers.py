"""Shared column lists for dialogue model queries.

Keeping these in one place stops near-duplicate SELECT statements from
drifting out of sync when columns are added or renamed.
"""
from __future__ import annotations

PAGE_COLUMNS = "id, title, page_type"

NODE_COLUMNS = (
    "id, page_id, parent_id, sort_order, depth, node_type, "
    "speaker, text, section, continue_target_id"
)

TAG_COLUMNS = "id, node_id, entity_type, entity_name, entity_id"

INSTR_COLUMNS = (
    "page_id, addr, section, op, text, speaker, fallthrough, "
    "targets, target_labels, target_predicates"
)
