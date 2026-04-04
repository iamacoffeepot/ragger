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
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Loads Lua service templates from classpath resources, spawns configured
 * service instances on startup, and watches for crashes to respawn them.
 *
 * Services are managed actors that run under a "svc/" namespace.
 * The manifest at services/services.json declares which templates to
 * register and which service instances to spawn.
 */
public class ServiceManager {

    private static final Logger log = LoggerFactory.getLogger(ServiceManager.class);
    private static final String RESOURCE_BASE = "/dev/ragger/plugin/services/";
    private static final String MANIFEST = RESOURCE_BASE + "services.json";
    private static final String SERVICE_PREFIX = "svc/";

    /** Minimum ticks between respawn attempts for the same service. */
    private static final int RESPAWN_COOLDOWN_TICKS = 10;

    /** Max consecutive respawns before giving up on a service. */
    private static final int MAX_RESPAWN_ATTEMPTS = 5;

    /** Ticks of sustained uptime before resetting the respawn counter. */
    private static final int RESPAWN_RESET_UPTIME_TICKS = 100;

    private final ActorManager actorManager;
    private final List<ServiceEntry> services = new ArrayList<>();
    private final Map<String, String> templateSources = new HashMap<>();
    private boolean started = false;

    public ServiceManager(ActorManager actorManager) {
        this.actorManager = actorManager;
    }

    /**
     * Load manifest, register templates, spawn services, and start watching.
     * Safe to call on the game tick thread.
     */
    public void start() {
        if (started) return;
        started = true;

        JsonObject manifest = loadManifest();
        if (manifest == null) {
            log.warn("No service manifest found — skipping service layer");
            return;
        }

        // Load and register templates referenced by services
        loadTemplates(manifest);

        // Spawn service instances
        JsonArray svcs = manifest.getAsJsonArray("services");
        if (svcs == null) return;

        for (JsonElement el : svcs) {
            JsonObject obj = el.getAsJsonObject();
            String name = obj.get("name").getAsString();
            String template = obj.get("template").getAsString();

            String source = templateSources.get(template);
            if (source == null) {
                log.warn("Service '{}' references unknown template '{}' — skipping", name, template);
                continue;
            }

            ServiceEntry entry = new ServiceEntry(name, template, source);
            services.add(entry);
            spawnService(entry);
        }

        log.info("Service layer started: {} templates, {} services",
            templateSources.size(), services.size());
    }

    /**
     * Called every game tick to check for crashed services and respawn them.
     */
    public void tick() {
        if (!started) return;

        for (ServiceEntry entry : services) {
            String fullName = SERVICE_PREFIX + entry.name;
            entry.ticksSinceCheck++;

            if (!actorManager.isRunning(fullName)) {
                if (entry.dead) continue;

                if (entry.respawnAttempts >= MAX_RESPAWN_ATTEMPTS) {
                    if (!entry.dead) {
                        log.warn("Service '{}' exceeded max respawn attempts ({}), giving up",
                            entry.name, MAX_RESPAWN_ATTEMPTS);
                        entry.dead = true;
                    }
                    continue;
                }

                if (entry.ticksSinceCheck < RESPAWN_COOLDOWN_TICKS) continue;

                log.info("Service '{}' not running — respawning (attempt {}/{})",
                    entry.name, entry.respawnAttempts + 1, MAX_RESPAWN_ATTEMPTS);
                entry.ticksSinceCheck = 0;
                spawnService(entry);
            } else {
                // Running — reset respawn counter on sustained uptime
                if (entry.ticksSinceCheck > RESPAWN_RESET_UPTIME_TICKS) {
                    entry.respawnAttempts = 0;
                }
            }
        }
    }

    /**
     * List managed service names and their status.
     */
    public List<ServiceStatus> status() {
        List<ServiceStatus> result = new ArrayList<>();
        for (ServiceEntry entry : services) {
            String fullName = SERVICE_PREFIX + entry.name;
            boolean running = actorManager.isRunning(fullName);
            result.add(new ServiceStatus(entry.name, entry.template, running,
                entry.respawnAttempts, entry.dead));
        }
        return result;
    }

    /**
     * Reset a dead service so the watchdog will try respawning it again.
     */
    public boolean revive(String name) {
        for (ServiceEntry entry : services) {
            if (entry.name.equals(name)) {
                entry.dead = false;
                entry.respawnAttempts = 0;
                entry.ticksSinceCheck = RESPAWN_COOLDOWN_TICKS;
                return true;
            }
        }
        return false;
    }

    /**
     * Shut down all managed services.
     */
    public void shutdown() {
        for (ServiceEntry entry : services) {
            String fullName = SERVICE_PREFIX + entry.name;
            if (actorManager.isRunning(fullName)) {
                actorManager.unload(fullName);
            }
        }
        services.clear();
        templateSources.clear();
        started = false;
    }

    // -- internals --

    private void spawnService(ServiceEntry entry) {
        String fullName = SERVICE_PREFIX + entry.name;
        String templateName = "svc-" + entry.template;
        // Resolve from template registry so hot-reloaded templates take effect
        String source = actorManager.getTemplate(templateName);
        if (source == null) {
            source = entry.source; // fallback to initial source
        }
        try {
            actorManager.load(fullName, source);
            entry.respawnAttempts++;
            log.info("Spawned service: {}", fullName);
        } catch (Exception e) {
            entry.respawnAttempts++;
            log.error("Failed to spawn service '{}': {}", entry.name, e.getMessage());
        }
    }

    private void loadTemplates(JsonObject manifest) {
        // Discover templates from service entries
        JsonArray svcs = manifest.getAsJsonArray("services");
        if (svcs == null) return;

        for (JsonElement el : svcs) {
            JsonObject obj = el.getAsJsonObject();
            String template = obj.get("template").getAsString();

            if (templateSources.containsKey(template)) continue;

            String source = loadResource(RESOURCE_BASE + template + ".lua");
            if (source == null) {
                log.warn("Template resource not found: {}.lua", template);
                continue;
            }

            templateSources.put(template, source);
            actorManager.defineTemplate("svc-" + template, source);
        }
    }

    private JsonObject loadManifest() {
        String json = loadResource(MANIFEST);
        if (json == null) return null;
        return new Gson().fromJson(json, JsonObject.class);
    }

    private String loadResource(String path) {
        try (InputStream is = getClass().getResourceAsStream(path)) {
            if (is == null) return null;
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.error("Failed to read resource: {}", path, e);
            return null;
        }
    }

    // -- data classes --

    private static class ServiceEntry {
        final String name;
        final String template;
        final String source;
        int respawnAttempts = 0;
        int ticksSinceCheck = RESPAWN_COOLDOWN_TICKS; // allow immediate first spawn
        boolean dead = false;

        ServiceEntry(String name, String template, String source) {
            this.name = name;
            this.template = template;
            this.source = source;
        }
    }

    public record ServiceStatus(String name, String template, boolean running,
                                 int respawnAttempts, boolean dead) {}
}
