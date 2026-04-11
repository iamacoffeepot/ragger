### FacilityEntry (`src/ragger/facility.py`)

Raw facility coordinate data (banks, furnaces, anvils, altars, spinning wheels, looms).

```python
from ragger.facility import FacilityEntry
from ragger.enums import Facility

FacilityEntry.all(conn, facility_type?, region?) -> list[FacilityEntry]
FacilityEntry.nearest(conn, x, y, facility_type?, metric?) -> FacilityEntry | None
FacilityEntry.nearby(conn, x, y, max_distance, facility_type?, metric?) -> list[tuple[FacilityEntry, float]]
entry.type -> Facility
entry.x -> int
entry.y -> int
entry.name -> str | None
entry.region -> Region | None                          # derived from nearest location
```
