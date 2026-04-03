package dev.clogger.cachedump;

import net.runelite.cache.MapImageDumper;
import net.runelite.cache.fs.Store;
import net.runelite.cache.region.Region;
import net.runelite.cache.util.XteaKeyManager;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Dumps rendered map tile images from the OSRS cache.
 *
 * Output: {output-dir}/{rx}_{ry}.png — rendered map tiles (256x256 px, 4 px per tile)
 *
 * Flags control what gets rendered (each has a --no-* counterpart):
 *   --objects / --no-objects       Objects (trees, rocks, buildings) [default: off]
 *   --icons / --no-icons           Map icons [default: off]
 *   --walls / --no-walls           Walls [default: on]
 *   --labels / --no-labels         Text labels [default: off]
 *   --overlays / --no-overlays     Overlay textures [default: on]
 *   --transparent                  Transparent background [default: off]
 *   --plane N                      Plane to render [default: 0]
 *
 * Usage: ./gradlew dumpMapTiles
 *        ./gradlew dumpMapTiles --args="--objects --icons"
 *        ./gradlew dumpMapTiles --args="--no-overlays --transparent"
 */
public class DumpMapTiles {

    public static void main(String[] args) throws Exception {
        String cachePath = null;
        Path outputDir = Path.of("../../data/cache-dump/map-tiles");
        int plane = 0;

        boolean objects = false;
        boolean icons = false;
        boolean walls = true;
        boolean labels = false;
        boolean overlays = true;
        boolean transparent = false;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--cache" -> cachePath = args[++i];
                case "--output" -> outputDir = Path.of(args[++i]);
                case "--plane" -> plane = Integer.parseInt(args[++i]);
                case "--objects" -> objects = true;
                case "--no-objects" -> objects = false;
                case "--icons" -> icons = true;
                case "--no-icons" -> icons = false;
                case "--walls" -> walls = true;
                case "--no-walls" -> walls = false;
                case "--labels" -> labels = true;
                case "--no-labels" -> labels = false;
                case "--overlays" -> overlays = true;
                case "--no-overlays" -> overlays = false;
                case "--transparent" -> transparent = true;
            }
        }

        File cacheDir = CacheLoader.resolveCache(cachePath, Path.of("../../data"));
        Files.createDirectories(outputDir);

        System.out.println("Loading cache from " + cacheDir);
        System.out.printf("Render flags: objects=%b icons=%b walls=%b labels=%b overlays=%b transparent=%b plane=%d%n",
            objects, icons, walls, labels, overlays, transparent, plane);

        try (Store store = new Store(cacheDir)) {
            store.load();

            XteaKeyManager keyManager = new XteaKeyManager();
            MapImageDumper dumper = new MapImageDumper(store, keyManager);
            dumper.setRenderMap(true);
            dumper.setRenderObjects(objects);
            dumper.setRenderIcons(icons);
            dumper.setRenderWalls(walls);
            dumper.setRenderLabels(labels);
            dumper.setRenderOverlays(overlays);
            dumper.setTransparency(transparent);
            dumper.load();

            List<Region> regions = CacheLoader.loadRegions(store);

            int count = 0;
            for (Region region : regions) {
                BufferedImage img = dumper.drawRegion(region, plane);
                String filename = plane + "_" + region.getRegionX() + "_" + region.getRegionY() + ".png";
                ImageIO.write(img, "PNG", outputDir.resolve(filename).toFile());
                count++;
                if (count % 500 == 0) {
                    System.out.println("  " + count + "/" + regions.size() + "...");
                }
            }

            System.out.println("Done. Dumped " + count + " map tiles to " + outputDir);
        }
    }
}
