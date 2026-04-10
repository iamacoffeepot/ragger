"""Condition frame definitions — explicit match order.

Each ``frames_*.py`` module exports a ``RULES`` list of ``FrameRule``
objects as plain data. This file assembles them into a single ordered
list. The parser tries rules top-to-bottom, so **specific frames must
come before catch-all frames** (e.g. ``quest_state`` before
``has_event_action``).

To add a new frame category, create a ``frames_foo.py`` with a
``RULES`` list, then insert it at the appropriate position below.
"""
from ragger.dialogue.condition_types import FrameRule

from ragger.dialogue.condition_frames.frames_quests import RULES as _quests
from ragger.dialogue.condition_frames.frames_skills import RULES as _skills
from ragger.dialogue.condition_frames.frames_items import RULES as _items
from ragger.dialogue.condition_frames.frames_equipment import RULES as _equipment
from ragger.dialogue.condition_frames.frames_inventory import RULES as _inventory
from ragger.dialogue.condition_frames.frames_farming import RULES as _farming
from ragger.dialogue.condition_frames.frames_tasks import RULES as _tasks
from ragger.dialogue.condition_frames.frames_dialogue import RULES as _dialogue
from ragger.dialogue.condition_frames.frames_world import RULES as _world
from ragger.dialogue.condition_frames.frames_misc import RULES as _misc
from ragger.dialogue.condition_frames.frames_events import RULES as _events
from ragger.dialogue.condition_frames.frames_events import HAS_EVENT_ACTION_RULES as _event_catchall

# ---------------------------------------------------------------------------
# Master rule list — ORDER MATTERS
#
# Specific, high-confidence frames first → broad catch-alls last.
# Within each category the internal ordering from the module is preserved.
# ---------------------------------------------------------------------------

ALL_RULES: list[FrameRule] = [
    # 1. Quest state — "has completed {quest}" must match before
    #    has_event_action's generic "has completed ..."
    *_quests,

    # 2. Skill checks
    *_skills,

    # 3. Item possession (has_item, has_coins, has_currency, etc.)
    *_items,

    # 4. Equipment / wearing
    *_equipment,

    # 5. Inventory space
    *_inventory,

    # 6. Farming
    *_farming,

    # 7. Task assignments (slayer, port, diary)
    *_tasks,

    # 8. Dialogue interaction (answered, puzzle, talked_to, npc_role, etc.)
    *_dialogue,

    # 9. World state, location, membership
    *_world,

    # 10. Misc (gender, follower, owns, build, cast)
    *_misc,

    # 11. Events (present-tense verbs, gerunds, outcome)
    *_events,

    # 12. LAST: has_event_action catch-all ("has VERBED ...")
    #     This is intentionally last because "has completed", "has started",
    #     etc. overlap with quest_state, task_progress, and other specific
    #     frames that must win.
    *_event_catchall,
]
