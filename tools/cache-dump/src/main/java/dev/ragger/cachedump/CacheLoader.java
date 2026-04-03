package dev.ragger.cachedump;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import net.runelite.cache.fs.Store;
import net.runelite.cache.region.Region;
import net.runelite.cache.region.RegionLoader;
import net.runelite.cache.util.XteaKeyManager;

import java.io.File;
import java.io.FileOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Shared utilities for loading the OSRS cache from disk or OpenRS2.
 */
public class CacheLoader {

    private static final String OPENRS2_API = "https://archive.openrs2.org";

    /**
     * Find the latest oldschool cache ID from OpenRS2.
     */
    public static int findLatestCacheId() throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(OPENRS2_API + "/caches.json"))
            .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

        JsonArray caches = JsonParser.parseString(response.body()).getAsJsonArray();
        int latestId = -1;
        String latestTimestamp = "";

        for (JsonElement el : caches) {
            JsonObject cache = el.getAsJsonObject();
            String game = cache.has("game") && !cache.get("game").isJsonNull()
                ? cache.get("game").getAsString() : "";
            String env = cache.has("environment") && !cache.get("environment").isJsonNull()
                ? cache.get("environment").getAsString() : "";

            if ("oldschool".equals(game) && "live".equals(env)) {
                String ts = cache.has("timestamp") && !cache.get("timestamp").isJsonNull()
                    ? cache.get("timestamp").getAsString() : "";
                if (ts.compareTo(latestTimestamp) > 0) {
                    latestTimestamp = ts;
                    latestId = cache.get("id").getAsInt();
                }
            }
        }

        return latestId;
    }

    /**
     * Download and extract cache from OpenRS2 into a local directory.
     */
    public static Path downloadCache(int cacheId, Path baseDir) throws Exception {
        Path cacheDir = baseDir.resolve("cache-" + cacheId);
        Path nested = cacheDir.resolve("cache");
        if (Files.isDirectory(nested) && Files.exists(nested.resolve("main_file_cache.dat2"))) {
            System.out.println("Cache already downloaded at " + nested);
            return nested;
        }

        Files.createDirectories(cacheDir);
        String url = OPENRS2_API + "/caches/runescape/" + cacheId + "/disk.zip";
        System.out.println("Downloading cache " + cacheId + " from " + url + "...");

        HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .build();

        Path tempZip = baseDir.resolve("cache-" + cacheId + ".zip");
        client.send(request, HttpResponse.BodyHandlers.ofFile(tempZip));
        System.out.println("Downloaded " + Files.size(tempZip) + " bytes");

        try (ZipInputStream zis = new ZipInputStream(Files.newInputStream(tempZip))) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                Path target = cacheDir.resolve(entry.getName());
                if (entry.isDirectory()) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    try (FileOutputStream fos = new FileOutputStream(target.toFile())) {
                        zis.transferTo(fos);
                    }
                }
            }
        }

        Files.deleteIfExists(tempZip);

        if (Files.isDirectory(nested) && Files.exists(nested.resolve("main_file_cache.dat2"))) {
            cacheDir = nested;
        }

        System.out.println("Cache extracted to " + cacheDir);
        return cacheDir;
    }

    /**
     * Resolve cache directory — either from a provided path or by downloading from OpenRS2.
     */
    public static File resolveCache(String cachePath, Path dataDir) throws Exception {
        if (cachePath != null) {
            return new File(cachePath);
        }
        System.out.println("Finding latest OSRS cache on OpenRS2...");
        int cacheId = findLatestCacheId();
        if (cacheId < 0) {
            throw new RuntimeException("Could not find latest oldschool cache on OpenRS2");
        }
        System.out.println("Latest cache: ID " + cacheId);
        return downloadCache(cacheId, dataDir).toFile();
    }

    /**
     * Load all regions from a store.
     */
    public static List<Region> loadRegions(Store store) throws Exception {
        XteaKeyManager keyManager = new XteaKeyManager();
        RegionLoader regionLoader = new RegionLoader(store, keyManager);
        regionLoader.loadRegions();
        return new ArrayList<>(regionLoader.getRegions());
    }
}
