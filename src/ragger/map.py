from __future__ import annotations

import heapq
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from ragger.enums import MAP_LINK_ANYWHERE, MapLinkType, MapSquareType
from ragger.location import DistanceMetric

GAME_TILES_PER_REGION = 64
PIXELS_PER_REGION = 256


@dataclass
class MapSquare:
    id: int
    plane: int
    region_x: int
    region_y: int
    type: MapSquareType
    image: bytes

    @property
    def game_x(self) -> int:
        return self.region_x * GAME_TILES_PER_REGION

    @property
    def game_y(self) -> int:
        return self.region_y * GAME_TILES_PER_REGION

    @classmethod
    def _from_row(cls, row: tuple) -> MapSquare:
        return cls(
            id=row[0],
            plane=row[1],
            region_x=row[2],
            region_y=row[3],
            type=MapSquareType(row[4]),
            image=row[5],
        )

    @classmethod
    def get(
        cls, conn: sqlite3.Connection, plane: int, region_x: int, region_y: int,
        type: MapSquareType = MapSquareType.COLOR,
    ) -> MapSquare | None:
        row = conn.execute(
            "SELECT id, plane, region_x, region_y, type, image FROM map_squares"
            " WHERE plane = ? AND region_x = ? AND region_y = ? AND type = ?",
            (plane, region_x, region_y, type.value),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def all(
        cls, conn: sqlite3.Connection, plane: int = 0,
        type: MapSquareType = MapSquareType.COLOR,
    ) -> list[MapSquare]:
        rows = conn.execute(
            "SELECT id, plane, region_x, region_y, type, image FROM map_squares"
            " WHERE plane = ? AND type = ? ORDER BY region_x, region_y",
            (plane, type.value),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def at_game_coord(
        cls, conn: sqlite3.Connection, x: int, y: int, plane: int = 0,
        type: MapSquareType = MapSquareType.COLOR,
    ) -> MapSquare | None:
        rx = x // GAME_TILES_PER_REGION
        ry = y // GAME_TILES_PER_REGION
        return cls.get(conn, plane, rx, ry, type)

    @classmethod
    def count(cls, conn: sqlite3.Connection, plane: int = 0, type: MapSquareType | None = None) -> int:
        if type is not None:
            return conn.execute(
                "SELECT COUNT(*) FROM map_squares WHERE plane = ? AND type = ?",
                (plane, type.value),
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM map_squares WHERE plane = ?", (plane,)).fetchone()[0]

    @classmethod
    def stitch(
        cls, conn: sqlite3.Connection,
        x_min: int, x_max: int, y_min: int, y_max: int,
        plane: int = 0,
        type: MapSquareType = MapSquareType.COLOR,
        region_padding: int = 1,
        pixels_per_tile: int | None = None,
    ) -> tuple:
        """Stitch map tiles for a game coordinate bounding box.

        Returns (numpy.ndarray, extent) where extent is [x_min, x_max, y_min, y_max]
        in game coordinates, suitable for matplotlib imshow.

        region_padding adds extra regions around the bounding box (default 1).
        pixels_per_tile overrides the output resolution. Native is 4 for color
        tiles, 1 for collision. Pass 1 for a compact 1px-per-game-tile canvas.
        """
        import io

        import numpy as np
        from PIL import Image

        rx_min = max(0, x_min // GAME_TILES_PER_REGION - region_padding)
        rx_max = (x_max - 1) // GAME_TILES_PER_REGION + region_padding
        ry_min = max(0, y_min // GAME_TILES_PER_REGION - region_padding)
        ry_max = (y_max - 1) // GAME_TILES_PER_REGION + region_padding

        native_per = PIXELS_PER_REGION if type == MapSquareType.COLOR else GAME_TILES_PER_REGION
        target_per = pixels_per_tile * GAME_TILES_PER_REGION if pixels_per_tile is not None else native_per
        canvas_w = (rx_max - rx_min + 1) * target_per
        canvas_h = (ry_max - ry_min + 1) * target_per
        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

        need_resize = target_per != native_per

        rows = conn.execute(
            "SELECT region_x, region_y, image FROM map_squares WHERE plane = ? AND type = ? "
            "AND region_x >= ? AND region_x <= ? AND region_y >= ? AND region_y <= ?",
            (plane, type.value, rx_min, rx_max, ry_min, ry_max),
        ).fetchall()
        for rx, ry, img_data in rows:
            try:
                tile = Image.open(io.BytesIO(img_data)).convert("RGB")
                if need_resize:
                    tile = tile.resize((target_per, target_per), Image.LANCZOS)
                px = (rx - rx_min) * target_per
                py = (ry_max - ry) * target_per
                canvas[py:py + target_per, px:px + target_per] = np.array(tile)
            except Exception:
                pass

        extent = [
            rx_min * GAME_TILES_PER_REGION,
            (rx_max + 1) * GAME_TILES_PER_REGION,
            ry_min * GAME_TILES_PER_REGION,
            (ry_max + 1) * GAME_TILES_PER_REGION,
        ]
        return canvas, extent

    @classmethod
    def stitch_blobs(
        cls, conn: sqlite3.Connection,
        x_min: int, x_max: int, y_min: int, y_max: int,
        plane: int = 0,
    ) -> tuple:
        """Stitch BLOB map squares into a uint16 grid at 1 px per tile.

        Unlike `stitch`, this preserves the 16-bit blob IDs instead of
        converting to RGB. Returns (grid, extent) where `grid[py, px]` is the
        blob ID at `px = gx - extent[0]`, `py = extent[3] - 1 - gy`. 0 = blocked.
        """
        import io

        import numpy as np
        from PIL import Image

        rx_min = max(0, x_min // GAME_TILES_PER_REGION)
        rx_max = (x_max - 1) // GAME_TILES_PER_REGION
        ry_min = max(0, y_min // GAME_TILES_PER_REGION)
        ry_max = (y_max - 1) // GAME_TILES_PER_REGION

        W = (rx_max - rx_min + 1) * GAME_TILES_PER_REGION
        H = (ry_max - ry_min + 1) * GAME_TILES_PER_REGION
        grid = np.zeros((H, W), dtype=np.uint16)

        rows = conn.execute(
            "SELECT region_x, region_y, image FROM map_squares "
            "WHERE plane = ? AND type = ? "
            "AND region_x >= ? AND region_x <= ? AND region_y >= ? AND region_y <= ?",
            (plane, MapSquareType.BLOB.value, rx_min, rx_max, ry_min, ry_max),
        ).fetchall()
        for rx, ry, img_data in rows:
            tile = np.asarray(Image.open(io.BytesIO(img_data)), dtype=np.uint16)
            px = (rx - rx_min) * GAME_TILES_PER_REGION
            py = (ry_max - ry) * GAME_TILES_PER_REGION
            grid[py:py + GAME_TILES_PER_REGION, px:px + GAME_TILES_PER_REGION] = tile

        extent = [
            rx_min * GAME_TILES_PER_REGION,
            (rx_max + 1) * GAME_TILES_PER_REGION,
            ry_min * GAME_TILES_PER_REGION,
            (ry_max + 1) * GAME_TILES_PER_REGION,
        ]
        return grid, extent


@dataclass
class MapLink:
    id: int
    src_location: str
    dst_location: str
    src_x: int
    src_y: int
    dst_x: int
    dst_y: int
    link_type: MapLinkType
    description: str | None

    @classmethod
    def all(cls, conn: sqlite3.Connection, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links"
        params: list = []
        if link_type is not None:
            query += " WHERE type = ?"
            params.append(link_type.value)
        query += " ORDER BY src_location, dst_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def departing(cls, conn: sqlite3.Connection, location: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = (
            "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description"
            " FROM map_links WHERE src_location = ?"
        )
        params: list = [location]
        if link_type is not None:
            query += " AND type = ?"
            params.append(link_type.value)
        query += " ORDER BY type, dst_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def arriving(cls, conn: sqlite3.Connection, location: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = (
            "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description"
            " FROM map_links WHERE dst_location = ?"
        )
        params: list = [location]
        if link_type is not None:
            query += " AND type = ?"
            params.append(link_type.value)
        query += " ORDER BY type, src_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def between(
        cls, conn: sqlite3.Connection, location_a: str, location_b: str,
        link_type: MapLinkType | None = None,
    ) -> list[MapLink]:
        if link_type is not None:
            query = """SELECT id, src_location, dst_location, src_x, src_y,
                               dst_x, dst_y, type, description FROM map_links
                        WHERE ((src_location = ? AND dst_location = ?)
                            OR (src_location = ? AND dst_location = ?))
                          AND type = ?
                        ORDER BY type"""
            params = [location_a, location_b, location_b, location_a, link_type.value]
        else:
            query = """SELECT id, src_location, dst_location, src_x, src_y,
                               dst_x, dst_y, type, description FROM map_links
                        WHERE (src_location = ? AND dst_location = ?)
                           OR (src_location = ? AND dst_location = ?)
                        ORDER BY type"""
            params = [location_a, location_b, location_b, location_a]
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def reachable_from(cls, conn: sqlite3.Connection, location: str) -> dict[str, list[MapLink]]:
        links = cls.departing(conn, location)
        result = {}
        for link in links:
            result.setdefault(link.dst_location, []).append(link)
        return result

    @classmethod
    def _from_row(cls, row: tuple):
        return cls(
            id=row[0],
            src_location=row[1],
            dst_location=row[2],
            src_x=row[3],
            src_y=row[4],
            dst_x=row[5],
            dst_y=row[6],
            link_type=MapLinkType(row[7]),
            description=row[8],
        )


# Zero-cost link types (instant transitions)
_ZERO_COST_TYPES = {
    MapLinkType.ENTRANCE,
    MapLinkType.EXIT,
    MapLinkType.FAIRY_RING,
    MapLinkType.CHARTER_SHIP,
    MapLinkType.SPIRIT_TREE,
    MapLinkType.GNOME_GLIDER,
    MapLinkType.CANOE,
    MapLinkType.TELEPORT,
    MapLinkType.MINECART,
    MapLinkType.SHIP,
    MapLinkType.QUETZAL,
    MapLinkType.NPC_TRANSPORT,
}


@dataclass
class PathStep:
    """One segment of a computed path. `link is None` means a walking segment
    between two tile coords; otherwise it's the traversal of that portal."""
    src_x: int
    src_y: int
    dst_x: int
    dst_y: int
    link: MapLink | None = None

    @property
    def link_type(self) -> MapLinkType:
        return self.link.link_type if self.link is not None else MapLinkType.WALKABLE

    @property
    def description(self) -> str | None:
        return self.link.description if self.link is not None else None

    @property
    def src_location(self) -> str:
        return self.link.src_location if self.link is not None else ""

    @property
    def dst_location(self) -> str:
        return self.link.dst_location if self.link is not None else ""


def _chebyshev(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(abs(x1 - x2), abs(y1 - y2))


def find_path(
    conn: sqlite3.Connection,
    src_x: int, src_y: int,
    dst_x: int, dst_y: int,
    allowed_types: set[MapLinkType] | None = None,
) -> list[PathStep] | None:
    """A* from (src_x, src_y) to (dst_x, dst_y) through the port graph.

    Nodes are ports, portal endpoints, and explicit start/goal markers.
    Walking edges come from port_transits (intra-blob BFS distances) and
    port_crossings (paired ports across a ridge). Portals come from
    `map_links` filtered by `allowed_types` — non-ANYWHERE links are
    reachable from/to any port in their src_blob_id / dst_blob_id; ANYWHERE
    teleports are seeded directly from the source with their activation cost.

    Returns a list of PathStep entries, or None if no path exists. Walking
    segments have `link is None`; portal traversals carry the `MapLink` used.
    """
    src_blob = blob_at(conn, src_x, src_y)
    dst_blob = blob_at(conn, dst_x, dst_y)
    if src_blob == 0 or dst_blob == 0:
        return None

    if src_blob == dst_blob:
        return [PathStep(src_x, src_y, dst_x, dst_y, None)]

    port_rows = conn.execute(
        "SELECT id, blob_id, rep_x, rep_y FROM ports"
    ).fetchall()
    port_coords: dict[int, tuple[int, int]] = {r[0]: (r[2], r[3]) for r in port_rows}
    ports_by_blob: dict[int, list[int]] = defaultdict(list)
    for pid, bid, _rx, _ry in port_rows:
        ports_by_blob[bid].append(pid)

    # Portal rows, filtered
    type_params: list = []
    type_clause = ""
    if allowed_types is not None:
        type_params = [t.value for t in allowed_types]
        type_clause = f" AND type IN ({','.join('?' * len(type_params))})"

    coord_rows = conn.execute(
        f"""SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description,
                   src_blob_id, dst_blob_id
            FROM map_links
            WHERE src_location != ?
              AND src_x IS NOT NULL AND src_y IS NOT NULL
              AND dst_x IS NOT NULL AND dst_y IS NOT NULL
              {type_clause}""",
        [MAP_LINK_ANYWHERE, *type_params],
    ).fetchall()

    anywhere_rows: list = []
    if allowed_types is None or MapLinkType.TELEPORT in allowed_types:
        anywhere_rows = conn.execute(
            """SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description,
                      src_blob_id, dst_blob_id
                FROM map_links
                WHERE src_location = ?
                  AND dst_x IS NOT NULL AND dst_y IS NOT NULL""",
            [MAP_LINK_ANYWHERE],
        ).fetchall()

    links_by_id: dict[int, MapLink] = {}
    adj: dict[tuple, list[tuple[tuple, int, MapLink | None]]] = defaultdict(list)

    for s, d, dist in conn.execute("SELECT src_port_id, dst_port_id, distance FROM port_transits"):
        adj[("port", s)].append((("port", d), dist, None))
    for s, d, dist in conn.execute("SELECT src_port_id, dst_port_id, distance FROM port_crossings"):
        adj[("port", s)].append((("port", d), dist, None))

    # Blob adjacencies patch narrow-passage connections the Voronoi sampling
    # missed. Each row is a directed "step into this blob at (a_x, a_y), land
    # in the neighbor blob at (b_x, b_y)" pair.
    adj_rows = conn.execute(
        "SELECT id, blob_a_id, blob_b_id, a_x, a_y, b_x, b_y, distance FROM blob_adjacencies"
    ).fetchall()
    adj_coords: dict[int, tuple[int, int, int, int]] = {}
    for row_id, _ba, _bb, ax, ay, bx, by, _dist in adj_rows:
        adj_coords[row_id] = (ax, ay, bx, by)
    for row_id, ba, bb, ax, ay, bx, by, dist in adj_rows:
        na = ("adj_a", row_id)
        nb = ("adj_b", row_id)
        adj[na].append((nb, dist, None))
        for pid in ports_by_blob.get(ba, []):
            px, py = port_coords[pid]
            adj[("port", pid)].append((na, _chebyshev(px, py, ax, ay), None))
        for pid in ports_by_blob.get(bb, []):
            px, py = port_coords[pid]
            adj[nb].append((("port", pid), _chebyshev(bx, by, px, py), None))

    SRC = ("src", 0)
    DST = ("dst", 0)

    for row in coord_rows:
        lid, sl, dl, sx, sy, dx, dy, ts, desc, sbid, dbid = row
        link = MapLink(
            id=lid, src_location=sl, dst_location=dl, src_x=sx, src_y=sy,
            dst_x=dx, dst_y=dy, link_type=MapLinkType(ts), description=desc,
        )
        links_by_id[lid] = link
        trav_cost = 0 if link.link_type in _ZERO_COST_TYPES else _chebyshev(sx, sy, dx, dy)
        adj[("p_src", lid)].append((("p_dst", lid), trav_cost, link))

        if sbid is not None:
            for pid in ports_by_blob.get(sbid, []):
                px, py = port_coords[pid]
                adj[("port", pid)].append((("p_src", lid), _chebyshev(px, py, sx, sy), None))
            if sbid == src_blob:
                adj[SRC].append((("p_src", lid), _chebyshev(src_x, src_y, sx, sy), None))

        if dbid is not None:
            for pid in ports_by_blob.get(dbid, []):
                px, py = port_coords[pid]
                adj[("p_dst", lid)].append((("port", pid), _chebyshev(dx, dy, px, py), None))
            if dbid == dst_blob:
                adj[("p_dst", lid)].append((DST, _chebyshev(dx, dy, dst_x, dst_y), None))

    for row in anywhere_rows:
        lid, sl, dl, sx, sy, dx, dy, ts, desc, _sbid, dbid = row
        link = MapLink(
            id=lid, src_location=sl, dst_location=dl, src_x=sx, src_y=sy,
            dst_x=dx, dst_y=dy, link_type=MapLinkType(ts), description=desc,
        )
        links_by_id[lid] = link
        adj[SRC].append((("p_dst", lid), 0, link))

        if dbid is not None:
            for pid in ports_by_blob.get(dbid, []):
                px, py = port_coords[pid]
                adj[("p_dst", lid)].append((("port", pid), _chebyshev(dx, dy, px, py), None))
            if dbid == dst_blob:
                adj[("p_dst", lid)].append((DST, _chebyshev(dx, dy, dst_x, dst_y), None))

    for pid in ports_by_blob.get(src_blob, []):
        px, py = port_coords[pid]
        adj[SRC].append((("port", pid), _chebyshev(src_x, src_y, px, py), None))
    for pid in ports_by_blob.get(dst_blob, []):
        px, py = port_coords[pid]
        adj[("port", pid)].append((DST, _chebyshev(px, py, dst_x, dst_y), None))

    # Src and dst blobs may have no ports of their own; in that case the only
    # way to enter / leave them is via blob_adjacencies.
    for row_id, ba, bb, ax, ay, bx, by, dist in adj_rows:
        if ba == src_blob:
            adj[SRC].append((("adj_a", row_id), _chebyshev(src_x, src_y, ax, ay), None))
        if bb == dst_blob:
            adj[("adj_b", row_id)].append((DST, _chebyshev(bx, by, dst_x, dst_y), None))

    def node_xy(node: tuple) -> tuple[int, int]:
        kind, key = node
        if kind == "src":
            return (src_x, src_y)
        if kind == "dst":
            return (dst_x, dst_y)
        if kind == "port":
            return port_coords[key]
        if kind == "p_src":
            return (links_by_id[key].src_x, links_by_id[key].src_y)
        if kind == "p_dst":
            return (links_by_id[key].dst_x, links_by_id[key].dst_y)
        if kind == "adj_a":
            ax, ay, _, _ = adj_coords[key]
            return (ax, ay)
        if kind == "adj_b":
            _, _, bx, by = adj_coords[key]
            return (bx, by)
        raise ValueError(f"unknown node kind: {kind}")

    g_score: dict[tuple, int] = {SRC: 0}
    came_from: dict[tuple, tuple[tuple, MapLink | None]] = {}
    closed: set[tuple] = set()
    counter = 0
    heap: list[tuple[int, int, tuple]] = [(0, 0, SRC)]

    while heap:
        _, _, node = heapq.heappop(heap)
        if node in closed:
            continue
        closed.add(node)
        if node == DST:
            break
        current_g = g_score[node]
        for neighbor, cost, via_link in adj.get(node, []):
            if neighbor in closed:
                continue
            new_g = current_g + cost
            if new_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = new_g
                came_from[neighbor] = (node, via_link)
                nx, ny = node_xy(neighbor)
                h = _chebyshev(nx, ny, dst_x, dst_y)
                counter += 1
                heapq.heappush(heap, (new_g + h, counter, neighbor))

    if DST not in g_score:
        return None

    # Reconstruct: walk back from DST -> SRC, collecting (node, via_link).
    chain: list[tuple[tuple, MapLink | None]] = []
    cur: tuple | None = DST
    while cur is not None and cur != SRC:
        prev_info = came_from.get(cur)
        if prev_info is None:
            break
        prev, via = prev_info
        chain.append((cur, via))
        cur = prev
    chain.reverse()

    path: list[PathStep] = []
    prev_xy = (src_x, src_y)
    for node, via in chain:
        this_xy = node_xy(node)
        if via is not None:
            if via.src_location == MAP_LINK_ANYWHERE:
                src_portal_xy = prev_xy
            else:
                src_portal_xy = (via.src_x, via.src_y)
            path.append(PathStep(
                src_portal_xy[0], src_portal_xy[1],
                via.dst_x, via.dst_y,
                via,
            ))
            prev_xy = (via.dst_x, via.dst_y)
        else:
            if this_xy != prev_xy:
                path.append(PathStep(prev_xy[0], prev_xy[1], this_xy[0], this_xy[1], None))
            prev_xy = this_xy

    return path


def _stitch_canvas(conn: sqlite3.Connection, x_min: int, x_max: int, y_min: int, y_max: int):
    """Stitch color map tiles for a game coordinate region. Returns (canvas, extent)."""
    return MapSquare.stitch(conn, x_min, x_max, y_min, y_max)


def render_path(
    conn: sqlite3.Connection,
    path: list[PathStep],
    output_path: str,
    padding: int = 200,
    dpi: int = 200,
) -> None:
    """Render a path on the map with colored arrows for each edge type.

    Solid arrows for walking, dashed for teleports/transport.
    Surface and underground are rendered as stacked subplots.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not path:
        return

    UNDERGROUND_THRESHOLD = 5000

    edge_styles = {
        MapLinkType.WALKABLE: {"color": "lime", "linestyle": "-", "label": "Walk"},
        MapLinkType.ENTRANCE: {"color": "cyan", "linestyle": "-", "label": "Entrance"},
        MapLinkType.EXIT: {"color": "cyan", "linestyle": "-", "label": "Exit"},
        MapLinkType.FAIRY_RING: {"color": "magenta", "linestyle": "--", "label": "Fairy ring"},
        MapLinkType.CHARTER_SHIP: {"color": "orange", "linestyle": "--", "label": "Charter ship"},
        MapLinkType.QUETZAL: {"color": "yellow", "linestyle": "--", "label": "Quetzal"},
        MapLinkType.TELEPORT: {"color": "white", "linestyle": ":", "label": "Teleport"},
    }
    default_style = {"color": "white", "linestyle": "--", "label": "Other"}

    # Cluster path into panels based on coordinate jumps
    # A jump > PANEL_BREAK_THRESHOLD tiles triggers a new panel
    PANEL_BREAK_THRESHOLD = 6 * GAME_TILES_PER_REGION  # 384 tiles

    # Collect ordered coordinates with their link index
    panels: list[list[tuple[int, int]]] = [[]]
    link_panel: dict[int, int] = {}  # link index -> panel index

    for li, link in enumerate(path):
        if link.src_location == MAP_LINK_ANYWHERE:
            link_panel[li] = 0
            panels[0].append((link.dst_x, link.dst_y))
            continue

        src = (link.src_x, link.src_y)
        dst = (link.dst_x, link.dst_y)

        # Check if this link's src is far from the current panel
        if panels[-1]:
            last = panels[-1][-1]
            dx = abs(src[0] - last[0])
            dy = abs(src[1] - last[1])
            if max(dx, dy) > PANEL_BREAK_THRESHOLD:
                panels.append([])

        panels[-1].append(src)

        # Check if dst jumps far from src (the link itself spans a long distance)
        jump = max(abs(dst[0] - src[0]), abs(dst[1] - src[1]))
        if jump > PANEL_BREAK_THRESHOLD:
            link_panel[li] = len(panels) - 1
            panels.append([])
            panels[-1].append(dst)
        else:
            panels[-1].append(dst)
            link_panel[li] = len(panels) - 1

    # Remove empty panels
    panels = [p for p in panels if p]

    n_panels = len(panels)
    fig, axes = plt.subplots(n_panels, 1, figsize=(16, max(4, 8 * n_panels)))
    if n_panels == 1:
        axes = [axes]

    panel_axes = []
    for pi, panel_coords in enumerate(panels):
        ax = axes[pi]
        px = [c[0] for c in panel_coords]
        py = [c[1] for c in panel_coords]
        p_xmin, p_xmax = min(px) - padding, max(px) + padding
        p_ymin, p_ymax = min(py) - padding, max(py) + padding

        canvas_img, extent = _stitch_canvas(conn, p_xmin, p_xmax, p_ymin, p_ymax)
        ax.imshow(canvas_img, extent=extent, aspect="equal")
        ax.set_xlim(p_xmin, p_xmax)
        ax.set_ylim(p_ymin, p_ymax)
        ax.axis("off")
        panel_axes.append(ax)

    def get_ax_for_link(link_idx: int):
        return panel_axes[link_panel.get(link_idx, 0)]

    # Draw edges
    seen_labels: set[str] = set()
    for li, link in enumerate(path):
        style = edge_styles.get(link.link_type, default_style)
        ax = get_ax_for_link(li)

        if link.src_location == MAP_LINK_ANYWHERE:
            ax.plot(link.dst_x, link.dst_y, "*", color=style["color"], markersize=15, zorder=15,
                    label=style["label"] if style["label"] not in seen_labels else None)
            seen_labels.add(style["label"])
            continue

        src_panel_idx = link_panel.get(li, 0)
        # Check if dst is in the same panel by seeing if the next link is on a different panel
        # or if this link itself spans a large jump
        jump = max(abs(link.src_x - link.dst_x), abs(link.src_y - link.dst_y))
        dst_in_same = jump <= PANEL_BREAK_THRESHOLD

        if dst_in_same:
            ax.annotate("",
                         xy=(link.dst_x, link.dst_y),
                         xytext=(link.src_x, link.src_y),
                         arrowprops=dict(arrowstyle="->", color=style["color"],
                                         linestyle=style["linestyle"], lw=2),
                         zorder=10)
        else:
            # Cross-panel: departure marker on src panel, arrival marker on dst panel
            ax.plot(link.src_x, link.src_y, "v", color=style["color"], markersize=12,
                    markeredgecolor="black", markeredgewidth=1, zorder=15)
            ax.text(link.src_x, link.src_y - 15, f"→ {link.dst_location}",
                    fontsize=8, color=style["color"], ha="center", va="top",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.8))
            # Arrival marker on the destination panel
            dst_panel_idx = src_panel_idx + 1 if src_panel_idx + 1 < n_panels else src_panel_idx
            dst_ax = panel_axes[dst_panel_idx]
            dst_ax.plot(link.dst_x, link.dst_y, "^", color=style["color"], markersize=12,
                        markeredgecolor="black", markeredgewidth=1, zorder=15)
            dst_ax.text(link.dst_x, link.dst_y + 15, f"← {link.src_location}",
                        fontsize=8, color=style["color"], ha="center", va="bottom",
                        fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.8))

        label = style["label"] if style["label"] not in seen_labels else None
        if label:
            panel_axes[0].plot([], [], color=style["color"], linestyle=style["linestyle"], lw=2, label=label)
            seen_labels.add(style["label"])

    # Mark named portal endpoints on the panel they live in.
    locations_on_path: list[tuple[str, int, int]] = []
    for step in path:
        if step.link is None:
            continue
        if step.src_location and step.src_location != MAP_LINK_ANYWHERE:
            locations_on_path.append((step.src_location, step.src_x, step.src_y))
        if step.dst_location:
            locations_on_path.append((step.dst_location, step.dst_x, step.dst_y))

    seen_locs: set[str] = set()
    unique_locs: list[tuple[str, int, int]] = []
    for name, x, y in locations_on_path:
        if name not in seen_locs:
            seen_locs.add(name)
            unique_locs.append((name, x, y))

    for name, x, y in unique_locs:
        best_ax = panel_axes[0]
        for pi, panel_coords in enumerate(panels):
            px = [c[0] for c in panel_coords]
            py = [c[1] for c in panel_coords]
            if (px and py
                    and min(px) - padding <= x <= max(px) + padding
                    and min(py) - padding <= y <= max(py) + padding):
                best_ax = panel_axes[pi]
                break
        best_ax.plot(x, y, "o", color="white", markersize=8, markeredgecolor="black",
                     markeredgewidth=1, zorder=20)
        best_ax.text(x, y + 12, name, fontsize=8, color="white", ha="center", va="bottom",
                     zorder=21, fontweight="bold",
                     bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.7))

    panel_axes[0].legend(loc="upper left", fontsize=10, framealpha=0.8)
    title = (
        f"{unique_locs[0][0]} → {unique_locs[-1][0]}"
        if unique_locs
        else f"({path[0].src_x}, {path[0].src_y}) → ({path[-1].dst_x}, {path[-1].dst_y})"
    )
    fig.suptitle(title, fontsize=14)
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close()


def render_path_tiles(
    conn: sqlite3.Connection,
    path: list[PathStep],
    output_path: str,
    padding: int = 80,
    dpi: int = 200,
) -> None:
    """Debug: expand each walking step into its tile-by-tile BFS route and
    plot every tile as a dot. Slow; use only for visual verification."""
    import io
    from collections import deque

    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    from ragger.collision import BLOCK_FULL, build_flags_grid, can_move

    if not path:
        return

    xs = [s.src_x for s in path] + [s.dst_x for s in path]
    ys = [s.src_y for s in path] + [s.dst_y for s in path]
    x_min, x_max = min(xs) - padding, max(xs) + padding
    y_min, y_max = min(ys) - padding, max(ys) + padding

    collision, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.COLLISION, region_padding=0)
    water, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.WATER, region_padding=0)
    flags = build_flags_grid(collision, water)
    H, W = flags.shape

    rx_min = x_min // GAME_TILES_PER_REGION
    ry_max = (y_max - 1) // GAME_TILES_PER_REGION
    sx_origin = rx_min * GAME_TILES_PER_REGION
    sy_top = (ry_max + 1) * GAME_TILES_PER_REGION

    def to_array(gx: int, gy: int) -> tuple[int, int]:
        return sy_top - 1 - gy, gx - sx_origin

    def bfs_tiles(sx: int, sy: int, dx: int, dy: int) -> list[tuple[int, int]]:
        spy, spx = to_array(sx, sy)
        dpy, dpx = to_array(dx, dy)
        if not (0 <= spy < H and 0 <= spx < W and 0 <= dpy < H and 0 <= dpx < W):
            return [(sx, sy), (dx, dy)]
        if (flags[spy, spx] & BLOCK_FULL) or (flags[dpy, dpx] & BLOCK_FULL):
            return [(sx, sy), (dx, dy)]
        parent: dict[tuple[int, int], tuple[int, int] | None] = {(spy, spx): None}
        queue = deque([(spy, spx)])
        while queue:
            cy, cx = queue.popleft()
            if (cy, cx) == (dpy, dpx):
                break
            for ddy in (-1, 0, 1):
                for ddx in (-1, 0, 1):
                    if ddy == 0 and ddx == 0:
                        continue
                    ny, nx = cy + ddy, cx + ddx
                    if (ny, nx) in parent:
                        continue
                    if can_move(flags, cy, cx, ddy, ddx, H, W):
                        parent[(ny, nx)] = (cy, cx)
                        queue.append((ny, nx))
        if (dpy, dpx) not in parent:
            return [(sx, sy), (dx, dy)]
        chain: list[tuple[int, int]] = []
        cur: tuple[int, int] | None = (dpy, dpx)
        while cur is not None:
            py, px = cur
            chain.append((sx_origin + px, sy_top - 1 - py))
            cur = parent[cur]
        chain.reverse()
        return chain

    fig, ax = plt.subplots(figsize=(12, 12 * (y_max - y_min) / max(x_max - x_min, 1)))
    basemap, extent = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, region_padding=0)
    ax.imshow(basemap, extent=extent, aspect="equal")

    for step in path:
        if step.link is None:
            tiles = bfs_tiles(step.src_x, step.src_y, step.dst_x, step.dst_y)
            txs = [t[0] for t in tiles]
            tys = [t[1] for t in tiles]
            ax.plot(txs, tys, "o", color="lime", markersize=1.5, zorder=10)
        else:
            ax.annotate(
                "", xy=(step.dst_x, step.dst_y), xytext=(step.src_x, step.src_y),
                arrowprops=dict(arrowstyle="->", color="magenta", linestyle="--", lw=2),
                zorder=11,
            )

    ax.plot(path[0].src_x, path[0].src_y, "o", color="yellow", markersize=10, markeredgecolor="black", zorder=20)
    ax.plot(path[-1].dst_x, path[-1].dst_y, "*", color="red", markersize=14, markeredgecolor="black", zorder=20)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close()


def blob_at(conn: sqlite3.Connection, x: int, y: int, plane: int = 0) -> int:
    """Return the blob id at a game coordinate, or 0 if blocked / no blob.

    Reads a single BLOB map square (not the full stitched grid), so this is
    cheap enough to call repeatedly from a pathfinder.
    """
    import io

    import numpy as np
    from PIL import Image

    region_x = x // GAME_TILES_PER_REGION
    region_y = y // GAME_TILES_PER_REGION
    ms = MapSquare.get(conn, plane, region_x, region_y, MapSquareType.BLOB)
    if ms is None:
        return 0

    tile_x = x - region_x * GAME_TILES_PER_REGION
    tile_y = y - region_y * GAME_TILES_PER_REGION
    arr = np.asarray(Image.open(io.BytesIO(ms.image)), dtype=np.uint16)
    py = GAME_TILES_PER_REGION - 1 - tile_y
    px = tile_x
    return int(arr[py, px])


