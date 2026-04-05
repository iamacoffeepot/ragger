package dev.ragger.plugin.scripting;

import net.runelite.api.*;
import net.runelite.api.Perspective;
import net.runelite.api.coords.LocalPoint;

import java.util.*;

/**
 * Computes model silhouette outlines by projecting 3D model geometry to screen space
 * and extracting edges where front-facing and back-facing triangles meet.
 *
 * Unlike convex hulls, silhouette outlines follow the actual model shape —
 * every concavity, limb, and protrusion is captured.
 *
 * The algorithm:
 * 1. Project all model vertices to screen space via Perspective.modelToCanvas
 * 2. Classify each triangle as front-facing or back-facing (screen-space winding)
 * 3. Find silhouette edges: edges where a front-facing and back-facing triangle meet,
 *    or boundary edges of front-facing triangles
 * 4. Chain edges into ordered contour loops
 */
public class SilhouetteComputer {

    private final Client client;

    public SilhouetteComputer(Client client) {
        this.client = client;
    }

    /**
     * A single contour: an ordered list of screen-space points forming a closed loop.
     */
    public record Contour(List<int[]> points) {}

    /**
     * Compute silhouette outlines for an NPC by name.
     * @param name NPC name (case-insensitive)
     * @param index 1-based index if multiple NPCs share the name
     * @return list of contours, or null if not found/no model
     */
    public List<Contour> npcOutline(String name, int index) {
        List<NPC> npcs = client.getNpcs();
        NPC target = null;
        int count = 0;
        for (NPC npc : npcs) {
            if (npc != null && npc.getName() != null && name.equalsIgnoreCase(npc.getName())) {
                count++;
                if (count == index) {
                    target = npc;
                    break;
                }
            }
        }

        if (target == null) {
            return null;
        }

        return computeActorOutline(target);
    }

    /**
     * Compute silhouette outlines for a player by name.
     * @param name player name (case-insensitive)
     * @return list of contours, or null if not found/no model
     */
    public List<Contour> playerOutline(String name) {
        List<Player> players = client.getPlayers();
        Player target = null;
        for (Player player : players) {
            if (player != null && player.getName() != null && name.equalsIgnoreCase(player.getName())) {
                target = player;
                break;
            }
        }

        if (target == null) {
            return null;
        }

        return computeActorOutline(target);
    }

    /**
     * Compute silhouette outlines for a game object at a tile.
     * @param worldX world X coordinate
     * @param worldY world Y coordinate
     * @param name optional name filter (case-insensitive partial match), or null
     * @return list of contours, or null if not found/no model
     */
    public List<Contour> objectOutline(int worldX, int worldY, String name) {
        Scene scene = client.getScene();
        Tile[][][] tiles = scene.getTiles();
        int plane = client.getPlane();

        LocalPoint lp = LocalPoint.fromWorld(client, worldX, worldY);
        if (lp == null) {
            return null;
        }

        int sceneX = lp.getSceneX();
        int sceneY = lp.getSceneY();

        if (sceneX < 0 || sceneY < 0 || sceneX >= tiles[plane].length || sceneY >= tiles[plane][0].length) {
            return null;
        }

        Tile tile = tiles[plane][sceneX][sceneY];
        if (tile == null) {
            return null;
        }

        GameObject[] gameObjects = tile.getGameObjects();
        if (gameObjects != null) {
            for (GameObject obj : gameObjects) {
                if (obj == null) continue;

                if (name != null) {
                    ObjectComposition comp = client.getObjectDefinition(obj.getId());
                    if (comp == null || comp.getName() == null) continue;
                    if (!comp.getName().toLowerCase().contains(name.toLowerCase())) continue;
                }

                return computeObjectOutline(obj);
            }
        }

        return null;
    }

    // ── Outline computation ───────────────────────────────────────────

    private List<Contour> computeActorOutline(Actor actor) {
        Model model = actor.getModel();
        if (model == null) {
            return null;
        }

        WorldView wv = actor.getWorldView();
        LocalPoint lp = actor.getLocalLocation();
        int tileHeight = Perspective.getFootprintTileHeight(client, lp, wv.getPlane(), actor.getFootprintSize())
                - actor.getAnimationHeightOffset();

        return computeOutline(wv, model, lp.getX(), lp.getY(), tileHeight, actor.getCurrentOrientation());
    }

    private List<Contour> computeObjectOutline(GameObject obj) {
        Renderable renderable = obj.getRenderable();
        if (renderable == null) {
            return null;
        }

        Model model = renderable instanceof Model ? (Model) renderable : renderable.getModel();
        if (model == null) {
            return null;
        }

        WorldView wv = obj.getWorldView();
        LocalPoint lp = obj.getLocalLocation();
        int tileHeight = obj.getZ() - renderable.getAnimationHeightOffset();

        return computeOutline(wv, model, lp.getX(), lp.getY(), tileHeight, obj.getModelOrientation());
    }

    private List<Contour> computeOutline(WorldView wv, Model model, int localX, int localY, int height, int orientation) {
        int vertexCount = model.getVerticesCount();
        int faceCount = model.getFaceCount();

        if (vertexCount == 0 || faceCount == 0) {
            return null;
        }

        float[] vx = model.getVerticesX();
        float[] vy = model.getVerticesY();
        float[] vz = model.getVerticesZ();
        int[] fi1 = model.getFaceIndices1();
        int[] fi2 = model.getFaceIndices2();
        int[] fi3 = model.getFaceIndices3();

        // Project all vertices to screen space
        int[] x2d = new int[vertexCount];
        int[] y2d = new int[vertexCount];

        Perspective.modelToCanvas(client, wv, vertexCount,
                localX, localY, height,
                orientation,
                vx, vz, vy, x2d, y2d);

        // Classify faces as front-facing or back-facing
        boolean[] frontFacing = new boolean[faceCount];
        boolean[] faceValid = new boolean[faceCount];

        for (int f = 0; f < faceCount; f++) {
            int a = fi1[f], b = fi2[f], c = fi3[f];

            if (x2d[a] == Integer.MIN_VALUE || x2d[b] == Integer.MIN_VALUE || x2d[c] == Integer.MIN_VALUE) {
                continue;
            }

            faceValid[f] = true;

            long cross = (long)(x2d[b] - x2d[a]) * (y2d[c] - y2d[a])
                       - (long)(y2d[b] - y2d[a]) * (x2d[c] - x2d[a]);
            frontFacing[f] = cross > 0;
        }

        // Build edge -> face adjacency map
        Map<Long, int[]> edgeFaces = new HashMap<>(faceCount * 3);

        for (int f = 0; f < faceCount; f++) {
            if (!faceValid[f]) continue;

            addEdgeFace(edgeFaces, fi1[f], fi2[f], f);
            addEdgeFace(edgeFaces, fi2[f], fi3[f], f);
            addEdgeFace(edgeFaces, fi3[f], fi1[f], f);
        }

        // Extract silhouette edges
        List<int[]> silhouetteEdges = new ArrayList<>();

        for (Map.Entry<Long, int[]> entry : edgeFaces.entrySet()) {
            int[] faces = entry.getValue();
            long edgeKey = entry.getKey();
            int v0 = (int) (edgeKey >> 32);
            int v1 = (int) (edgeKey & 0xFFFFFFFFL);

            if (faces[1] == -1) {
                if (frontFacing[faces[0]]) {
                    silhouetteEdges.add(new int[]{v0, v1});
                }
            } else {
                if (frontFacing[faces[0]] != frontFacing[faces[1]]) {
                    silhouetteEdges.add(new int[]{v0, v1});
                }
            }
        }

        if (silhouetteEdges.isEmpty()) {
            return null;
        }

        // Chain edges into contours
        List<List<int[]>> rawContours = chainEdges(silhouetteEdges, x2d, y2d);

        if (rawContours.isEmpty()) {
            return null;
        }

        // Filter out inner contours (holes) by signed area.
        // Outer contours share the winding direction of the largest contour;
        // inner holes wind the opposite way.
        double largestArea = 0;
        double[] areas = new double[rawContours.size()];
        for (int i = 0; i < rawContours.size(); i++) {
            areas[i] = signedArea(rawContours.get(i));
            if (Math.abs(areas[i]) > Math.abs(largestArea)) {
                largestArea = areas[i];
            }
        }

        boolean outerPositive = largestArea > 0;
        List<Contour> contours = new ArrayList<>();
        for (int i = 0; i < rawContours.size(); i++) {
            if ((areas[i] > 0) == outerPositive) {
                contours.add(new Contour(rawContours.get(i)));
            }
        }

        return contours.isEmpty() ? null : contours;
    }

    /**
     * Add a face to the edge adjacency map.
     * Edge key is (min(v0,v1) << 32 | max(v0,v1)) to ensure consistent ordering.
     */
    private static void addEdgeFace(Map<Long, int[]> edgeFaces, int v0, int v1, int faceIndex) {
        long key = v0 < v1
                ? ((long) v0 << 32) | (v1 & 0xFFFFFFFFL)
                : ((long) v1 << 32) | (v0 & 0xFFFFFFFFL);

        int[] faces = edgeFaces.get(key);
        if (faces == null) {
            edgeFaces.put(key, new int[]{faceIndex, -1});
        } else if (faces[1] == -1) {
            faces[1] = faceIndex;
        }
    }

    /**
     * Signed area of a screen-space contour (shoelace formula).
     * Positive = clockwise in screen coords (Y-down), negative = counter-clockwise.
     */
    private static double signedArea(List<int[]> pts) {
        double area = 0;
        for (int i = 0, n = pts.size(); i < n; i++) {
            int[] a = pts.get(i);
            int[] b = pts.get((i + 1) % n);
            area += (double) a[0] * b[1] - (double) b[0] * a[1];
        }
        return area / 2.0;
    }

    /**
     * Chain silhouette edges into ordered contour loops.
     * Each contour is a list of screen-space {x, y} points.
     * Uses edge-level visited tracking to handle junction vertices (degree > 2).
     */
    private static List<List<int[]>> chainEdges(List<int[]> edges, int[] x2d, int[] y2d) {
        Map<Integer, List<int[]>> adj = new HashMap<>();
        for (int i = 0; i < edges.size(); i++) {
            int[] edge = edges.get(i);
            adj.computeIfAbsent(edge[0], k -> new ArrayList<>()).add(new int[]{edge[1], i});
            adj.computeIfAbsent(edge[1], k -> new ArrayList<>()).add(new int[]{edge[0], i});
        }

        boolean[] edgeUsed = new boolean[edges.size()];
        List<List<int[]>> contours = new ArrayList<>();

        for (int ei = 0; ei < edges.size(); ei++) {
            if (edgeUsed[ei]) continue;

            List<int[]> contour = new ArrayList<>();
            int start = edges.get(ei)[0];
            int current = start;
            int prevEdge = -1;

            while (true) {
                contour.add(new int[]{x2d[current], y2d[current]});

                List<int[]> neighbors = adj.get(current);
                if (neighbors == null) break;

                int next = -1;
                int nextEdge = -1;
                for (int[] ne : neighbors) {
                    if (!edgeUsed[ne[1]] && ne[1] != prevEdge) {
                        next = ne[0];
                        nextEdge = ne[1];
                        break;
                    }
                }

                if (nextEdge == -1) break;

                edgeUsed[nextEdge] = true;
                prevEdge = nextEdge;

                if (next == start) break;

                current = next;
            }

            if (contour.size() >= 3) {
                contours.add(contour);
            }
        }

        return contours;
    }
}
