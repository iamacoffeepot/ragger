package dev.ragger.plugin.scripting;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * Loads Lua actor templates from classpath resources and registers them
 * with the ActorManager. Unlike ServiceManager, templates are only
 * registered — not spawned or watchdogged. They're available for use
 * via actors:create() or ActorSpawn with a template name.
 */
public class ActorTemplateLoader {

    private static final Logger log = LoggerFactory.getLogger(ActorTemplateLoader.class);
    private static final String RESOURCE_BASE = "/dev/ragger/plugin/actors/";
    private static final String MANIFEST = RESOURCE_BASE + "actors.json";

    private final ActorManager actorManager;

    public ActorTemplateLoader(final ActorManager actorManager) {
        this.actorManager = actorManager;
    }

    /**
     * Load manifest and register all listed templates. Safe to call multiple
     * times — templates are idempotently overwritten in the registry.
     */
    public void load() {
        final String json = loadResource(MANIFEST);
        if (json == null) {
            log.warn("No actor template manifest found — skipping");
            return;
        }

        final JsonObject manifest = new Gson().fromJson(json, JsonObject.class);
        final JsonArray templates = manifest.getAsJsonArray("templates");
        if (templates == null) {
            return;
        }

        int loaded = 0;
        for (final JsonElement el : templates) {
            final String name = el.getAsString();
            final String source = loadResource(RESOURCE_BASE + name + ".lua");

            if (source == null) {
                log.warn("Actor template resource not found: {}.lua", name);
                continue;
            }

            actorManager.defineTemplate(name, source);
            loaded++;
        }

        log.info("Registered {} actor templates", loaded);
    }

    private String loadResource(final String path) {
        try (final InputStream is = getClass().getResourceAsStream(path)) {
            if (is == null) {
                return null;
            }
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        } catch (final IOException e) {
            log.error("Failed to read resource: {}", path, e);
            return null;
        }
    }
}
