package dev.ragger.cachedump;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.runelite.cache.EntityOpsDefinition;
import net.runelite.cache.ObjectManager;
import net.runelite.cache.definitions.ObjectDefinition;
import net.runelite.cache.fs.Store;

import java.io.File;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Dumps all object (scenery/loc) definitions from the OSRS cache to JSON.
 *
 * Output: a single JSON file with id, name, sizeX, sizeY,
 * ops (5 action slots), and conditionalOps (var-gated actions).
 */
public class DumpObjectDefinitions {

    record OpEntry(int index, String text) {}

    record ConditionalOpEntry(int index, String text, int varpId, int varbitId,
                              int minValue, int maxValue) {}

    record ObjectEntry(int id, String name, int sizeX, int sizeY,
                       List<OpEntry> ops, List<ConditionalOpEntry> conditionalOps) {}

    public static void main(final String[] args) throws Exception {
        String output = "../../data/cache-dump/object-definitions.json";
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

            final ObjectManager manager = new ObjectManager(store);
            manager.load();

            final List<ObjectEntry> entries = new ArrayList<>();

            for (final ObjectDefinition def : manager.getObjects()) {
                if ("null".equalsIgnoreCase(def.getName())) {
                    continue;
                }

                final List<OpEntry> ops = extractOps(def.getOps());
                final List<ConditionalOpEntry> conditionalOps = extractConditionalOps(def.getOps());

                entries.add(new ObjectEntry(
                    def.getId(), def.getName(), def.getSizeX(), def.getSizeY(),
                    ops.isEmpty() ? null : ops,
                    conditionalOps.isEmpty() ? null : conditionalOps
                ));
            }

            entries.sort((a, b) -> Integer.compare(a.id(), b.id()));

            final Gson gson = new GsonBuilder().setPrettyPrinting().create();
            try (final Writer writer = Files.newBufferedWriter(outputPath)) {
                gson.toJson(entries, writer);
            }

            System.out.printf("Dumped %d object definitions -> %s%n", entries.size(), outputPath);
        }
    }

    private static List<OpEntry> extractOps(final EntityOpsDefinition opsDefinition) {
        final List<OpEntry> result = new ArrayList<>();
        final List<EntityOpsDefinition.Op> rawOps = opsDefinition.getOps();

        for (int i = 0; i < rawOps.size(); i++) {
            final EntityOpsDefinition.Op op = rawOps.get(i);
            if (op != null && op.text != null) {
                result.add(new OpEntry(i, op.text));
            }
        }

        return result;
    }

    private static List<ConditionalOpEntry> extractConditionalOps(final EntityOpsDefinition opsDefinition) {
        final List<ConditionalOpEntry> result = new ArrayList<>();
        final List<List<EntityOpsDefinition.ConditionalOp>> rawCond = opsDefinition.getConditionalOps();

        for (int i = 0; i < rawCond.size(); i++) {
            final List<EntityOpsDefinition.ConditionalOp> conds = rawCond.get(i);
            if (conds == null) {
                continue;
            }

            for (final EntityOpsDefinition.ConditionalOp cop : conds) {
                if (cop.text != null) {
                    result.add(new ConditionalOpEntry(
                        i, cop.text, cop.varpID, cop.varbitID,
                        cop.minValue, cop.maxValue
                    ));
                }
            }
        }

        return result;
    }
}
