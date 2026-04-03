package dev.clogger.cachedump;

import net.runelite.cache.ConfigType;
import net.runelite.cache.IndexType;
import net.runelite.cache.definitions.OverlayDefinition;
import net.runelite.cache.definitions.UnderlayDefinition;
import net.runelite.cache.definitions.loaders.OverlayLoader;
import net.runelite.cache.definitions.loaders.UnderlayLoader;
import net.runelite.cache.fs.Archive;
import net.runelite.cache.fs.ArchiveFiles;
import net.runelite.cache.fs.FSFile;
import net.runelite.cache.fs.Index;
import net.runelite.cache.fs.Store;
import net.runelite.cache.region.Region;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Dumps water mask images from the OSRS cache.
 *
 * Output: {output-dir}/{rx}_{ry}.png — blue = water, transparent = land (64x64 px)
 *
 * Detects water from underlay and overlay definition colors.
 *
 * Usage: DumpWater [--cache <path>] [--output <dir>]
 */
public class DumpWater {

    private static final int REGION_SIZE = 64;

    private final Map<Integer, UnderlayDefinition> underlays = new HashMap<>();
    private final Map<Integer, OverlayDefinition> overlays = new HashMap<>();

    public DumpWater(Store store) throws IOException {
        Index configIndex = store.getIndex(IndexType.CONFIGS);

        Archive underlayArchive = configIndex.getArchive(ConfigType.UNDERLAY.getId());
        byte[] underlayData = store.getStorage().loadArchive(underlayArchive);
        ArchiveFiles underlayFiles = underlayArchive.getFiles(underlayData);
        UnderlayLoader underlayLoader = new UnderlayLoader();
        for (FSFile file : underlayFiles.getFiles()) {
            underlays.put(file.getFileId(), underlayLoader.load(file.getFileId(), file.getContents()));
        }
        System.out.println("Loaded " + underlays.size() + " underlays");

        Archive overlayArchive = configIndex.getArchive(ConfigType.OVERLAY.getId());
        byte[] overlayData = store.getStorage().loadArchive(overlayArchive);
        ArchiveFiles overlayFiles = overlayArchive.getFiles(overlayData);
        OverlayLoader overlayLoader = new OverlayLoader();
        for (FSFile file : overlayFiles.getFiles()) {
            overlays.put(file.getFileId(), overlayLoader.load(file.getFileId(), file.getContents()));
        }
        System.out.println("Loaded " + overlays.size() + " overlays");
    }

    private boolean isWaterUnderlay(int underlayId) {
        if (underlayId <= 0) return false;
        UnderlayDefinition def = underlays.get(underlayId - 1);
        if (def == null) return false;
        int color = def.getColor();
        int r = (color >> 16) & 0xFF;
        int g = (color >> 8) & 0xFF;
        int b = color & 0xFF;
        return b > 100 && b > r + 30 && b > g;
    }

    private boolean isWaterOverlay(int overlayId) {
        if (overlayId <= 0) return false;
        OverlayDefinition def = overlays.get(overlayId - 1);
        if (def == null) return false;
        int color = def.getRgbColor();
        int r = (color >> 16) & 0xFF;
        int g = (color >> 8) & 0xFF;
        int b = color & 0xFF;
        return b > 100 && b > r + 30 && b > g;
    }

    public void dumpRegion(Region region, Path outputDir, int plane) throws IOException {
        BufferedImage img = new BufferedImage(REGION_SIZE, REGION_SIZE, BufferedImage.TYPE_INT_ARGB);

        for (int x = 0; x < REGION_SIZE; x++) {
            for (int y = 0; y < REGION_SIZE; y++) {
                int underlayId = region.getUnderlayId(plane, x, y);
                int overlayId = region.getOverlayId(plane, x, y);
                boolean isWater = isWaterUnderlay(underlayId) || isWaterOverlay(overlayId);
                img.setRGB(x, REGION_SIZE - 1 - y, isWater ? 0xFF0066CC : 0x00000000);
            }
        }

        String filename = plane + "_" + region.getRegionX() + "_" + region.getRegionY() + ".png";
        ImageIO.write(img, "PNG", outputDir.resolve(filename).toFile());
    }

    public static void main(String[] args) throws Exception {
        String cachePath = null;
        Path outputDir = Path.of("../../data/cache-dump/water");
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

            DumpWater dumper = new DumpWater(store);
            List<Region> regions = CacheLoader.loadRegions(store);
            Files.createDirectories(outputDir);

            int count = 0;
            for (Region region : regions) {
                dumper.dumpRegion(region, outputDir, plane);
                count++;
                if (count % 500 == 0) {
                    System.out.println("  " + count + "/" + regions.size() + "...");
                }
            }

            System.out.println("Done. Dumped " + count + " water masks to " + outputDir);
        }
    }
}
