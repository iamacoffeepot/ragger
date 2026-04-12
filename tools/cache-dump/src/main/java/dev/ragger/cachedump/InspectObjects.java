package dev.ragger.cachedump;

import net.runelite.cache.ObjectManager;
import net.runelite.cache.definitions.ObjectDefinition;
import net.runelite.cache.fs.Store;
import net.runelite.cache.region.Location;
import net.runelite.cache.region.Region;

import java.io.File;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.TreeMap;

/**
 * Diagnostic: prints every object in a coordinate bounding box along with
 * every no-arg boolean/int/string getter on ObjectDefinition. Used to figure
 * out which field(s) distinguish walkthrough walls (archways, open gates)
 * from solid walls.
 *
 * Usage: InspectObjects --xmin N --xmax N --ymin N --ymax N [--plane 0] [--cache <path>]
 */
public class InspectObjects {

    public static void main(final String[] args) throws Exception {
        int xmin = -1, xmax = -1, ymin = -1, ymax = -1, plane = 0;
        String cachePath = null;

        for (int i = 0; i < args.length - 1; i++) {
            switch (args[i]) {
                case "--xmin" -> xmin = Integer.parseInt(args[i + 1]);
                case "--xmax" -> xmax = Integer.parseInt(args[i + 1]);
                case "--ymin" -> ymin = Integer.parseInt(args[i + 1]);
                case "--ymax" -> ymax = Integer.parseInt(args[i + 1]);
                case "--plane" -> plane = Integer.parseInt(args[i + 1]);
                case "--cache" -> cachePath = args[i + 1];
            }
        }
        if (xmin < 0 || xmax < 0 || ymin < 0 || ymax < 0) {
            System.err.println("Required: --xmin --xmax --ymin --ymax");
            System.exit(1);
        }

        final File cacheDir = CacheLoader.resolveCache(cachePath, Path.of("../../data/cache-dump"));

        try (final Store store = new Store(cacheDir)) {
            store.load();

            final ObjectManager manager = new ObjectManager(store);
            manager.load();

            final List<Region> regions = CacheLoader.loadRegions(store);
            int hits = 0;

            for (final Region region : regions) {
                for (final Location loc : region.getLocations()) {
                    if (loc.getPosition().getZ() != plane) continue;
                    int gx = loc.getPosition().getX();
                    int gy = loc.getPosition().getY();
                    if (gx < xmin || gx > xmax || gy < ymin || gy > ymax) continue;

                    ObjectDefinition def = manager.getObject(loc.getId());
                    String name = def != null ? def.getName() : "???";
                    System.out.printf("(%d,%d) id=%d name='%s' loc.type=%d orient=%d%n",
                        gx, gy, loc.getId(), name, loc.getType(), loc.getOrientation());
                    if (def != null) {
                        dumpGetters(def);
                    }
                    System.out.println();
                    hits++;
                }
            }
            System.out.printf("Total: %d objects in box%n", hits);
        }
    }

    private static void dumpGetters(final ObjectDefinition def) {
        final TreeMap<String, Object> values = new TreeMap<>();
        for (final Method m : def.getClass().getMethods()) {
            if (m.getParameterCount() != 0) continue;
            final String name = m.getName();
            if (!(name.startsWith("get") || name.startsWith("is")) || name.equals("getClass")) continue;
            final Class<?> rt = m.getReturnType();
            if (rt != int.class && rt != boolean.class && rt != String.class && rt != short.class && rt != byte.class && rt != long.class) continue;
            try {
                Object v = m.invoke(def);
                if (v != null && !"null".equals(String.valueOf(v))) {
                    values.put(name, v);
                }
            } catch (Exception e) {
                // skip getters that throw
            }
        }
        for (final var entry : values.entrySet()) {
            System.out.printf("    %s = %s%n", entry.getKey(), entry.getValue());
        }
    }
}
