package dev.clogger.cachedump;

import net.runelite.cache.fs.Store;
import net.runelite.cache.region.Region;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Dumps collision flag images from the OSRS cache.
 *
 * Output: {output-dir}/{rx}_{ry}.png — red = blocked, white = walkable (64x64 px)
 *
 * Bridge tiles (plane 1 flag 0x2) are resolved to their actual collision plane.
 *
 * Usage: DumpCollision [--cache <path>] [--output <dir>]
 */
public class DumpCollision {

    private static final int REGION_SIZE = 64;

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

            List<Region> regions = CacheLoader.loadRegions(store);
            Files.createDirectories(outputDir);

            int count = 0;
            for (Region region : regions) {
                dumpRegion(region, outputDir, plane);
                count++;
                if (count % 500 == 0) {
                    System.out.println("  " + count + "/" + regions.size() + "...");
                }
            }

            System.out.println("Done. Dumped " + count + " collision maps to " + outputDir);
        }
    }

    private static void dumpRegion(Region region, Path outputDir, int plane) throws Exception {
        BufferedImage img = new BufferedImage(REGION_SIZE, REGION_SIZE, BufferedImage.TYPE_INT_ARGB);

        for (int x = 0; x < REGION_SIZE; x++) {
            for (int y = 0; y < REGION_SIZE; y++) {
                // Bridge flag on plane above — use that plane's collision instead
                int effectivePlane = plane;
                if (plane < 3 && (region.getTileSetting(plane + 1, x, y) & 0x2) != 0) {
                    effectivePlane = plane + 1;
                }

                boolean blocked = (region.getTileSetting(effectivePlane, x, y) & 0x1) != 0;
                img.setRGB(x, REGION_SIZE - 1 - y, blocked ? 0xFFFF0000 : 0xFFFFFFFF);
            }
        }

        String filename = plane + "_" + region.getRegionX() + "_" + region.getRegionY() + ".png";
        ImageIO.write(img, "PNG", outputDir.resolve(filename).toFile());
    }
}
