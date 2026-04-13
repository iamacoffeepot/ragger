package dev.ragger.cachedump;

import net.runelite.cache.ObjectManager;
import net.runelite.cache.definitions.ObjectDefinition;
import net.runelite.cache.fs.Store;
import net.runelite.cache.region.Location;
import net.runelite.cache.region.Region;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Dumps collision flag images from the OSRS cache.
 *
 * Includes both tile-based collision (flag 0x1) and object-based collision:
 * - Wall types (loc 0-3): directional blocking derived from type + orientation
 * - Game objects (loc 9-21): full blocking on all covered tiles
 * - Floor decorations (loc 22): full blocking if interactType == 1
 *
 * Output: {output-dir}/{plane}_{rx}_{ry}.png — red = blocked, white = walkable (64x64 px)
 *
 * Usage: DumpCollision [--cache <path>] [--output <dir>] [--plane <n>]
 */
public class DumpCollision {

    private static final int REGION_SIZE = 64;

    // Cardinal collision flags (blue channel bits 0-3)
    private static final int BLOCK_W = 0x1;
    private static final int BLOCK_N = 0x2;
    private static final int BLOCK_E = 0x4;
    private static final int BLOCK_S = 0x8;
    private static final int BLOCK_FULL = 0x10;

    /** Marker bit to distinguish data-present tiles from void (all zeros). */
    private static final int DATA_PRESENT = 0x20;

    // Diagonal collision flags — block only the diagonal corner traversal
    // (green channel bits 0-3 when packed to PNG).
    private static final int BLOCK_NW = 0x100;
    private static final int BLOCK_NE = 0x200;
    private static final int BLOCK_SE = 0x400;
    private static final int BLOCK_SW = 0x800;

    public static void main(String[] args) throws Exception {
        String cachePath = null;
        Path outputDir = Path.of("../../data/cache-dump/collision");
        int plane = 0;

        for (int i = 0; i < args.length - 1; i++) {
            if ("--cache".equals(args[i])) cachePath = args[i + 1];
            if ("--output".equals(args[i])) outputDir = Path.of(args[i + 1]);
            if ("--plane".equals(args[i])) plane = Integer.parseInt(args[i + 1]);
        }

        File cacheDir = CacheLoader.resolveCache(cachePath, Path.of("../../data"));

        System.out.println("Loading cache from " + cacheDir);
        try (Store store = new Store(cacheDir)) {
            store.load();

            ObjectManager objectManager = new ObjectManager(store);
            objectManager.load();
            System.out.println("Loaded " + objectManager.getObjects().size() + " object definitions");

            List<Region> regions = CacheLoader.loadRegions(store);
            Files.createDirectories(outputDir);

            int count = 0;
            for (Region region : regions) {
                dumpRegion(region, objectManager, outputDir, plane);
                count++;
                if (count % 500 == 0) {
                    System.out.println("  " + count + "/" + regions.size() + "...");
                }
            }

            System.out.println("Done. Dumped " + count + " collision maps to " + outputDir);
        }
    }

    private static void dumpRegion(Region region, ObjectManager objectManager, Path outputDir, int plane) throws Exception {
        // Per-tile directional collision bitmask
        int[][] flags = new int[REGION_SIZE][REGION_SIZE];

        // Step 1: tile settings (existing logic)
        for (int x = 0; x < REGION_SIZE; x++) {
            for (int y = 0; y < REGION_SIZE; y++) {
                int effectivePlane = plane;
                if (plane < 3 && (region.getTileSetting(plane + 1, x, y) & 0x2) != 0) {
                    effectivePlane = plane + 1;
                }
                if ((region.getTileSetting(effectivePlane, x, y) & 0x1) != 0) {
                    flags[x][y] |= BLOCK_FULL;
                }
            }
        }

        // Step 2: object-based collision
        int baseX = region.getRegionX() * REGION_SIZE;
        int baseY = region.getRegionY() * REGION_SIZE;

        for (Location loc : region.getLocations()) {
            if (loc.getPosition().getZ() != plane) {
                continue; // Only process objects on the target plane
            }

            ObjectDefinition def = objectManager.getObject(loc.getId());
            if (def == null) continue;

            int interactType = def.getInteractType();
            if (interactType == 0) continue; // purely decorative

            int type = loc.getType();
            int orientation = loc.getOrientation();

            // Walkthrough arches / open gates: wall objects with interactType=1
            // (clickable scenery, usually just Examine) AND obstructsGround=false
            // are physically walkable in-game even though they render as walls.
            // Skip their collision so pathing can route through them. Fences and
            // solid walls have interactType=2 and remain blocked.
            if (type >= 0 && type <= 3 && interactType == 1 && !def.isObstructsGround()) continue;
            int lx = loc.getPosition().getX() - baseX;
            int ly = loc.getPosition().getY() - baseY;

            // Skip objects on bridge tiles — bridge surface overrides collision
            if (plane == 0 && lx >= 0 && lx < REGION_SIZE && ly >= 0 && ly < REGION_SIZE
                && (region.getTileSetting(1, lx, ly) & 0x2) != 0) {
                continue;
            }

            if (type >= 0 && type <= 3) {
                // Wall types — directional blocking
                applyWallCollision(flags, lx, ly, type, orientation);
            } else if (type >= 9 && type <= 21) {
                // Game objects — full blocking on covered tiles
                int sizeX = def.getSizeX();
                int sizeY = def.getSizeY();
                if (orientation == 1 || orientation == 3) {
                    // Swap dimensions for rotated objects
                    int tmp = sizeX;
                    sizeX = sizeY;
                    sizeY = tmp;
                }
                for (int dx = 0; dx < sizeX; dx++) {
                    for (int dy = 0; dy < sizeY; dy++) {
                        int tx = lx + dx;
                        int ty = ly + dy;
                        if (tx >= 0 && tx < REGION_SIZE && ty >= 0 && ty < REGION_SIZE) {
                            flags[tx][ty] |= BLOCK_FULL;
                        }
                    }
                }
            } else if (type == 22) {
                // Floor decoration — blocking if interactType == 1
                if (interactType == 1 && lx >= 0 && lx < REGION_SIZE && ly >= 0 && ly < REGION_SIZE) {
                    flags[lx][ly] |= BLOCK_FULL;
                }
            }
            // Types 4-8 (wall decorations): no collision
        }

        // Step 3: render to image — encode raw flags as pixel values across
        // two channels so diagonal flags fit alongside the cardinal ones.
        // Blue channel  = cardinal flags + BLOCK_FULL + DATA_PRESENT (bits 0-7)
        // Green channel = diagonal flags (bits 8-15, shifted down to 0-7)
        // Python decodes with: flags = (green << 8) | blue
        BufferedImage img = new BufferedImage(REGION_SIZE, REGION_SIZE, BufferedImage.TYPE_INT_ARGB);
        for (int x = 0; x < REGION_SIZE; x++) {
            for (int y = 0; y < REGION_SIZE; y++) {
                int packed = DATA_PRESENT | flags[x][y];
                int blue = packed & 0xFF;
                int green = (packed >> 8) & 0xFF;
                img.setRGB(x, REGION_SIZE - 1 - y, 0xFF000000 | (green << 8) | blue);
            }
        }

        String filename = plane + "_" + region.getRegionX() + "_" + region.getRegionY() + ".png";
        ImageIO.write(img, "PNG", outputDir.resolve(filename).toFile());
    }

    /**
     * Apply wall collision based on loc type (0-3) and orientation (0-3).
     *
     * Type 0: straight wall — blocks 1 cardinal edge
     * Type 1: thin diagonal corner piece — blocks 1 diagonal only
     * Type 2: L-corner (wall connector) — blocks 2 adjacent cardinals
     * Type 3: thin diagonal wall — blocks 1 diagonal only (same as type 1)
     *
     * Canonical semantics from Jagex's CollisionMap.addWall (see LocShape).
     * Types 1 and 3 are rendered as thin pieces at the tile corner and only
     * obstruct diagonal traversal through that corner; cardinal movement
     * through the tile's edges is unaffected. This is what makes archways
     * and open gates walkable even though they're drawn as walls.
     */
    private static void applyWallCollision(int[][] flags, int lx, int ly, int type, int orientation) {
        if (lx < 0 || lx >= REGION_SIZE || ly < 0 || ly >= REGION_SIZE) return;

        if (type == 0) {
            // Straight wall — single edge
            switch (orientation) {
                case 0 -> { // West wall
                    flags[lx][ly] |= BLOCK_W;
                    if (lx > 0) flags[lx - 1][ly] |= BLOCK_E;
                }
                case 1 -> { // North wall
                    flags[lx][ly] |= BLOCK_N;
                    if (ly < REGION_SIZE - 1) flags[lx][ly + 1] |= BLOCK_S;
                }
                case 2 -> { // East wall
                    flags[lx][ly] |= BLOCK_E;
                    if (lx < REGION_SIZE - 1) flags[lx + 1][ly] |= BLOCK_W;
                }
                case 3 -> { // South wall
                    flags[lx][ly] |= BLOCK_S;
                    if (ly > 0) flags[lx][ly - 1] |= BLOCK_N;
                }
            }
        } else if (type == 1 || type == 3) {
            // Thin diagonal corner / wall — blocks one diagonal traversal only
            switch (orientation) {
                case 0 -> { // NW diagonal
                    flags[lx][ly] |= BLOCK_NW;
                    if (lx > 0 && ly < REGION_SIZE - 1) flags[lx - 1][ly + 1] |= BLOCK_SE;
                }
                case 1 -> { // NE diagonal
                    flags[lx][ly] |= BLOCK_NE;
                    if (lx < REGION_SIZE - 1 && ly < REGION_SIZE - 1) flags[lx + 1][ly + 1] |= BLOCK_SW;
                }
                case 2 -> { // SE diagonal
                    flags[lx][ly] |= BLOCK_SE;
                    if (lx < REGION_SIZE - 1 && ly > 0) flags[lx + 1][ly - 1] |= BLOCK_NW;
                }
                case 3 -> { // SW diagonal
                    flags[lx][ly] |= BLOCK_SW;
                    if (lx > 0 && ly > 0) flags[lx - 1][ly - 1] |= BLOCK_NE;
                }
            }
        } else if (type == 2) {
            // L-corner (wall connector) — blocks two adjacent cardinals
            switch (orientation) {
                case 0 -> { // W + N
                    flags[lx][ly] |= BLOCK_W | BLOCK_N;
                    if (lx > 0) flags[lx - 1][ly] |= BLOCK_E;
                    if (ly < REGION_SIZE - 1) flags[lx][ly + 1] |= BLOCK_S;
                }
                case 1 -> { // N + E
                    flags[lx][ly] |= BLOCK_N | BLOCK_E;
                    if (ly < REGION_SIZE - 1) flags[lx][ly + 1] |= BLOCK_S;
                    if (lx < REGION_SIZE - 1) flags[lx + 1][ly] |= BLOCK_W;
                }
                case 2 -> { // E + S
                    flags[lx][ly] |= BLOCK_E | BLOCK_S;
                    if (lx < REGION_SIZE - 1) flags[lx + 1][ly] |= BLOCK_W;
                    if (ly > 0) flags[lx][ly - 1] |= BLOCK_N;
                }
                case 3 -> { // S + W
                    flags[lx][ly] |= BLOCK_S | BLOCK_W;
                    if (ly > 0) flags[lx][ly - 1] |= BLOCK_N;
                    if (lx > 0) flags[lx - 1][ly] |= BLOCK_E;
                }
            }
        }
    }
}
