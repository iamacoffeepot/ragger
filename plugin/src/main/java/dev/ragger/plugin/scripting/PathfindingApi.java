package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.api.CollisionData;
import net.runelite.api.CollisionDataFlag;
import party.iroiro.luajava.Lua;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

/**
 * Lua binding for tile-level A* pathfinding within the loaded scene.
 * Exposed as the global "pathfinding" table in Lua scripts.
 *
 * Uses RuneLite's CollisionData to check walkability. Only works within
 * the currently loaded 104x104 scene region.
 */
public class PathfindingApi {

    private static final int SCENE_SIZE = 104;
    private static final int MAX_NODES = 5000;

    /** Directional movement flags — blocks movement INTO a tile from the given direction. */
    private static final int BLOCK_WEST = CollisionDataFlag.BLOCK_MOVEMENT_WEST;
    private static final int BLOCK_EAST = CollisionDataFlag.BLOCK_MOVEMENT_EAST;
    private static final int BLOCK_SOUTH = CollisionDataFlag.BLOCK_MOVEMENT_SOUTH;
    private static final int BLOCK_NORTH = CollisionDataFlag.BLOCK_MOVEMENT_NORTH;
    private static final int BLOCK_SW = CollisionDataFlag.BLOCK_MOVEMENT_SOUTH_WEST;
    private static final int BLOCK_SE = CollisionDataFlag.BLOCK_MOVEMENT_SOUTH_EAST;
    private static final int BLOCK_NW = CollisionDataFlag.BLOCK_MOVEMENT_NORTH_WEST;
    private static final int BLOCK_NE = CollisionDataFlag.BLOCK_MOVEMENT_NORTH_EAST;
    private static final int BLOCK_FULL = CollisionDataFlag.BLOCK_MOVEMENT_FULL;

    /**
     * 8-directional neighbours.
     * Cardinals: dx, dy, flag on SOURCE blocking this direction, 0, 0.
     * Diagonals: dx, dy, flag on SOURCE blocking this diagonal,
     *            flag on SOURCE blocking the horizontal cardinal component,
     *            flag on SOURCE blocking the vertical cardinal component.
     */
    private static final int[][] DIRS = {
        { 0,  1, BLOCK_NORTH, 0, 0},
        { 0, -1, BLOCK_SOUTH, 0, 0},
        { 1,  0, BLOCK_EAST,  0, 0},
        {-1,  0, BLOCK_WEST,  0, 0},
        { 1,  1, BLOCK_NE, BLOCK_EAST, BLOCK_NORTH},
        {-1,  1, BLOCK_NW, BLOCK_WEST, BLOCK_NORTH},
        { 1, -1, BLOCK_SE, BLOCK_EAST, BLOCK_SOUTH},
        {-1, -1, BLOCK_SW, BLOCK_WEST, BLOCK_SOUTH},
    };

    private final Client client;

    public PathfindingApi(final Client client) {
        this.client = client;
    }

    public void register(final Lua lua) {
        lua.createTable(0, 5);

        lua.push(this::find_path);
        lua.setField(-2, "find_path");

        lua.push(this::find_path_toward);
        lua.setField(-2, "find_path_toward");

        lua.push(this::can_reach);
        lua.setField(-2, "can_reach");

        lua.push(this::distance);
        lua.setField(-2, "distance");

        lua.push(this::flags_at);
        lua.setField(-2, "flags_at");

        lua.setGlobal("pathfinding");
    }

    /**
     * pathfinding:flags_at(worldX, worldY) -> int collision flags or nil
     */
    private int flags_at(final Lua lua) {
        final int worldX = (int) lua.toInteger(2);
        final int worldY = (int) lua.toInteger(3);

        final CollisionData[] collisionData = client.getCollisionMaps();
        if (collisionData == null) {
            lua.pushNil();
            return 1;
        }

        final int plane = client.getPlane();
        final int[][] flags = collisionData[plane].getFlags();
        final int sx = worldX - client.getBaseX();
        final int sy = worldY - client.getBaseY();

        if (!inBounds(sx, sy)) {
            lua.pushNil();
            return 1;
        }

        lua.push(flags[sx][sy]);
        return 1;
    }

    /**
     * pathfinding:find_path(fromX, fromY, toX, toY) -> array of {x, y} waypoints or nil
     */
    private int find_path(final Lua lua) {
        final int fromX = (int) lua.toInteger(2);
        final int fromY = (int) lua.toInteger(3);
        final int toX = (int) lua.toInteger(4);
        final int toY = (int) lua.toInteger(5);

        final List<int[]> path = astar(fromX, fromY, toX, toY);
        if (path == null) {
            lua.pushNil();
            return 1;
        }

        return pushPath(lua, path);
    }

    /**
     * pathfinding:can_reach(fromX, fromY, toX, toY) -> boolean
     */
    private int can_reach(final Lua lua) {
        final int fromX = (int) lua.toInteger(2);
        final int fromY = (int) lua.toInteger(3);
        final int toX = (int) lua.toInteger(4);
        final int toY = (int) lua.toInteger(5);

        lua.push(astar(fromX, fromY, toX, toY) != null);
        return 1;
    }

    /**
     * pathfinding:distance(fromX, fromY, toX, toY) -> int tile count or -1
     */
    private int distance(final Lua lua) {
        final int fromX = (int) lua.toInteger(2);
        final int fromY = (int) lua.toInteger(3);
        final int toX = (int) lua.toInteger(4);
        final int toY = (int) lua.toInteger(5);

        final List<int[]> path = astar(fromX, fromY, toX, toY);
        lua.push(path != null ? path.size() - 1 : -1);
        return 1;
    }

    /**
     * pathfinding:find_path_toward(fromX, fromY, toX, toY) -> array of {x, y} waypoints or nil
     *
     * Like find_path, but if the destination is unreachable (out of scene or blocked),
     * flood fills from the source and paths to the reachable tile closest to the target.
     */
    private int find_path_toward(final Lua lua) {
        final int fromX = (int) lua.toInteger(2);
        final int fromY = (int) lua.toInteger(3);
        final int toX = (int) lua.toInteger(4);
        final int toY = (int) lua.toInteger(5);

        // Try direct path first
        List<int[]> path = astar(fromX, fromY, toX, toY);
        if (path != null) {
            return pushPath(lua, path);
        }

        // Flood fill to find the reachable tile closest to the target
        final int[] best = floodFillClosest(fromX, fromY, toX, toY);
        if (best == null) {
            lua.pushNil();
            return 1;
        }

        path = astar(fromX, fromY, best[0], best[1]);
        if (path == null) {
            lua.pushNil();
            return 1;
        }

        return pushPath(lua, path);
    }

    /**
     * Flood fill from a world coordinate and return the reachable tile closest
     * to the target (Chebyshev distance). Uses the same movement rules as A*.
     */
    private int[] floodFillClosest(final int fromWorldX, final int fromWorldY, final int toWorldX, final int toWorldY) {
        final CollisionData[] collisionData = client.getCollisionMaps();
        if (collisionData == null) {
            return null;
        }

        final int plane = client.getPlane();
        final int[][] flags = collisionData[plane].getFlags();
        final int baseX = client.getBaseX();
        final int baseY = client.getBaseY();

        final int sx = fromWorldX - baseX;
        final int sy = fromWorldY - baseY;

        if (!inBounds(sx, sy) || (flags[sx][sy] & BLOCK_FULL) != 0) {
            return null;
        }

        final boolean[][] visited = new boolean[SCENE_SIZE][SCENE_SIZE];
        final java.util.ArrayDeque<int[]> queue = new java.util.ArrayDeque<>();
        queue.add(new int[]{sx, sy});
        visited[sx][sy] = true;

        int bestX = sx;
        int bestY = sy;
        int bestDist = chebyshev(sx + baseX, sy + baseY, toWorldX, toWorldY);

        while (!queue.isEmpty()) {
            final int[] tile = queue.poll();
            final int cx = tile[0];
            final int cy = tile[1];

            for (final int[] dir : DIRS) {
                final int nx = cx + dir[0];
                final int ny = cy + dir[1];

                if (!inBounds(nx, ny) || visited[nx][ny]) {
                    continue;
                }

                if ((flags[nx][ny] & BLOCK_FULL) != 0) {
                    continue;
                }

                if ((flags[cx][cy] & dir[2]) != 0) {
                    continue;
                }

                if (dir[0] != 0 && dir[1] != 0) {
                    if ((flags[cx][cy] & dir[3]) != 0 || (flags[cx][cy] & dir[4]) != 0) {
                        continue;
                    }
                    final int hx = cx + dir[0];
                    final int vy = cy + dir[1];
                    if ((flags[hx][cy] & BLOCK_FULL) != 0 || (flags[cx][vy] & BLOCK_FULL) != 0) {
                        continue;
                    }
                    if ((flags[hx][cy] & dir[4]) != 0 || (flags[cx][vy] & dir[3]) != 0) {
                        continue;
                    }
                }

                visited[nx][ny] = true;
                queue.add(new int[]{nx, ny});

                final int dist = chebyshev(nx + baseX, ny + baseY, toWorldX, toWorldY);
                if (dist < bestDist) {
                    bestDist = dist;
                    bestX = nx;
                    bestY = ny;
                }
            }
        }

        final int worldX = bestX + baseX;
        final int worldY = bestY + baseY;

        // Don't return the start tile as the "best"
        if (worldX == fromWorldX && worldY == fromWorldY) {
            return null;
        }

        return new int[]{worldX, worldY};
    }

    private int pushPath(final Lua lua, final List<int[]> path) {
        lua.createTable(path.size(), 0);
        for (int i = 0; i < path.size(); i++) {
            lua.createTable(0, 2);
            lua.push(path.get(i)[0]);
            lua.setField(-2, "x");
            lua.push(path.get(i)[1]);
            lua.setField(-2, "y");
            lua.rawSetI(-2, i + 1);
        }
        return 1;
    }

    /**
     * A* pathfinding over the scene collision map.
     * Coordinates are world tile coords. Returns path as world coords, or null if unreachable.
     */
    private List<int[]> astar(final int fromWorldX, final int fromWorldY, final int toWorldX, final int toWorldY) {
        final CollisionData[] collisionData = client.getCollisionMaps();
        if (collisionData == null) {
            return null;
        }

        final int plane = client.getPlane();
        final int[][] flags = collisionData[plane].getFlags();
        final int baseX = client.getBaseX();
        final int baseY = client.getBaseY();

        final int sx = fromWorldX - baseX;
        final int sy = fromWorldY - baseY;
        final int gx = toWorldX - baseX;
        final int gy = toWorldY - baseY;

        if (!inBounds(sx, sy) || !inBounds(gx, gy)) {
            return null;
        }

        if ((flags[sx][sy] & BLOCK_FULL) != 0 || (flags[gx][gy] & BLOCK_FULL) != 0) {
            return null;
        }

        final Map<Long, Long> cameFrom = new HashMap<>();
        final Map<Long, Integer> gScore = new HashMap<>();
        final long startKey = packKey(sx, sy);
        final long goalKey = packKey(gx, gy);

        gScore.put(startKey, 0);

        final PriorityQueue<long[]> open = new PriorityQueue<>(Comparator.comparingLong(a -> a[1]));
        open.add(new long[]{startKey, chebyshev(sx, sy, gx, gy)});

        int expanded = 0;

        while (!open.isEmpty() && expanded < MAX_NODES) {
            final long[] current = open.poll();
            final long currentKey = current[0];

            if (currentKey == goalKey) {
                return reconstructPath(cameFrom, goalKey, baseX, baseY);
            }

            expanded++;
            final int cx = unpackX(currentKey);
            final int cy = unpackY(currentKey);
            final int currentG = gScore.getOrDefault(currentKey, Integer.MAX_VALUE);

            for (final int[] dir : DIRS) {
                final int nx = cx + dir[0];
                final int ny = cy + dir[1];

                if (!inBounds(nx, ny)) {
                    continue;
                }

                if ((flags[nx][ny] & BLOCK_FULL) != 0) {
                    continue;
                }

                if ((flags[cx][cy] & dir[2]) != 0) {
                    continue;
                }

                // For diagonal movement, check cardinal components on source
                // and that intermediate tiles are passable
                if (dir[0] != 0 && dir[1] != 0) {
                    // Source must allow both cardinal components
                    if ((flags[cx][cy] & dir[3]) != 0 || (flags[cx][cy] & dir[4]) != 0) {
                        continue;
                    }
                    // Intermediate cardinal tiles must not be fully blocked
                    final int hx = cx + dir[0];
                    final int vy = cy + dir[1];
                    if ((flags[hx][cy] & BLOCK_FULL) != 0 || (flags[cx][vy] & BLOCK_FULL) != 0) {
                        continue;
                    }
                    // Horizontal intermediate must allow vertical component
                    // Vertical intermediate must allow horizontal component
                    if ((flags[hx][cy] & dir[4]) != 0 || (flags[cx][vy] & dir[3]) != 0) {
                        continue;
                    }
                }

                final int tentativeG = currentG + 1;
                final long neighborKey = packKey(nx, ny);
                final int prevG = gScore.getOrDefault(neighborKey, Integer.MAX_VALUE);

                if (tentativeG < prevG) {
                    cameFrom.put(neighborKey, currentKey);
                    gScore.put(neighborKey, tentativeG);
                    final int f = tentativeG + chebyshev(nx, ny, gx, gy);
                    open.add(new long[]{neighborKey, f});
                }
            }
        }

        return null;
    }

    private static List<int[]> reconstructPath(
        final Map<Long, Long> cameFrom,
        final long goalKey,
        final int baseX,
        final int baseY
    ) {
        final List<int[]> path = new ArrayList<>();
        long key = goalKey;

        while (key != -1L) {
            path.add(new int[]{unpackX(key) + baseX, unpackY(key) + baseY});
            final Long parent = cameFrom.get(key);
            key = parent != null ? parent : -1L;
        }

        // Reverse to get start->goal order
        final int size = path.size();
        for (int i = 0; i < size / 2; i++) {
            final int[] tmp = path.get(i);
            path.set(i, path.get(size - 1 - i));
            path.set(size - 1 - i, tmp);
        }

        return path;
    }

    private static boolean inBounds(final int x, final int y) {
        return x >= 0 && x < SCENE_SIZE && y >= 0 && y < SCENE_SIZE;
    }

    private static int chebyshev(final int x1, final int y1, final int x2, final int y2) {
        return Math.max(Math.abs(x2 - x1), Math.abs(y2 - y1));
    }

    private static long packKey(final int x, final int y) {
        return ((long) x << 16) | (y & 0xFFFFL);
    }

    private static int unpackX(final long key) {
        return (int) (key >> 16);
    }

    private static int unpackY(final long key) {
        return (int) (key & 0xFFFF);
    }
}
