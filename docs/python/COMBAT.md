# Combat

`ragger.combat` exposes combat-level calculation.

## `combat_level(**kwargs) -> int`

Compute the OSRS combat level for a given set of skill levels. All skills are keyword-only and default to the fresh-account starting values (`1` everywhere except `hitpoints=10`).

```python
from ragger.combat import combat_level

combat_level()                                      # 3  (fresh account)
combat_level(attack=40, strength=40, defence=40)    # 32
combat_level(magic=72, prayer=43, hitpoints=40)     # 50 (pure mage)
```

### Formula

```
base  = (defence + hitpoints + floor(prayer / 2)) / 4
melee = 13/40 * (attack + strength)
range = 13/40 * floor(3 * ranged / 2)
magic = 13/40 * floor(3 * magic / 2)
combat = floor(base + max(melee, range, magic))
```

Ranged and Magic use `floor(3 * level / 2)`, so an odd level contributes the same attack score as the even level below it. This matches in-game behaviour (not a Python rounding artifact).
