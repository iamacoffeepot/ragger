package dev.ragger.cachedump;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.stream.JsonWriter;
import net.runelite.cache.EntityOpsDefinition;
import net.runelite.cache.ObjectManager;
import net.runelite.cache.definitions.ObjectDefinition;
import net.runelite.cache.fs.Store;
import net.runelite.cache.region.Location;
import net.runelite.cache.region.Region;

import java.io.File;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Dumps world object spawn locations from the OSRS cache to JSON.
 *
 * Only includes objects whose definition has at least one menu action
 * (ops or conditionalOps), filtering out purely decorative scenery.
 *
 * Output: a single JSON array of {id, x, y, plane, type, orientation}.
 *
 * Usage: DumpObjectLocations [--cache <path>] [--output <file>]
 */
public class DumpObjectLocations {

    public static void main(final String[] args) throws Exception {
        String output = "../../data/cache-dump/object-locations.json";
        String cachePath = null;

        for (int i = 0; i < args.length - 1; i++) {
            if ("--output".equals(args[i])) {
                output = args[i + 1];
            } else if ("--cache".equals(args[i])) {
                cachePath = args[i + 1];
            }
        }

        final Path outputPath = Path.of(output);
        Files.createDirectories(outputPath.getParent());

        final File cacheDir = CacheLoader.resolveCache(cachePath, Path.of("../../data/cache-dump"));

        try (final Store store = new Store(cacheDir)) {
            store.load();

            final ObjectManager objectManager = new ObjectManager(store);
            objectManager.load();
            System.out.println("Loaded " + objectManager.getObjects().size() + " object definitions");

            // Pre-compute the set of object IDs that have any menu action
            final Set<Integer> interactiveIds = new HashSet<>();
            for (final ObjectDefinition def : objectManager.getObjects()) {
                if ("null".equalsIgnoreCase(def.getName())) {
                    continue;
                }
                if (hasActions(def.getOps())) {
                    interactiveIds.add(def.getId());
                }
            }
            System.out.println("Found " + interactiveIds.size() + " interactive object definitions");

            final List<Region> regions = CacheLoader.loadRegions(store);

            // Stream directly to JSON to avoid holding all entries in memory
            int count = 0;
            try (final Writer writer = Files.newBufferedWriter(outputPath);
                 final JsonWriter jw = new JsonWriter(writer)) {
                jw.setIndent(""); // compact output
                jw.beginArray();

                for (int r = 0; r < regions.size(); r++) {
                    final Region region = regions.get(r);

                    for (final Location loc : region.getLocations()) {
                        if (!interactiveIds.contains(loc.getId())) {
                            continue;
                        }

                        jw.beginArray();
                        jw.value(loc.getId());
                        jw.value(loc.getPosition().getX());
                        jw.value(loc.getPosition().getY());
                        jw.value(loc.getPosition().getZ());
                        jw.value(loc.getType());
                        jw.value(loc.getOrientation());
                        jw.endArray();
                        count++;
                    }

                    if ((r + 1) % 500 == 0) {
                        System.out.println("  " + (r + 1) + "/" + regions.size() + " regions...");
                    }
                }

                jw.endArray();
            }

            System.out.printf("Dumped %d interactive object spawns -> %s%n", count, outputPath);
        }
    }

    private static boolean hasActions(final EntityOpsDefinition ops) {
        for (final EntityOpsDefinition.Op op : ops.getOps()) {
            if (op != null && op.text != null) {
                return true;
            }
        }
        for (final List<EntityOpsDefinition.ConditionalOp> conds : ops.getConditionalOps()) {
            if (conds != null) {
                for (final EntityOpsDefinition.ConditionalOp cop : conds) {
                    if (cop.text != null) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
}
