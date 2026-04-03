package dev.ragger.plugin.scripting;

import net.runelite.client.chat.ChatMessageManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.ConcurrentHashMap;

/**
 * Manages Lua script lifecycles. Each script gets its own LuaJ runtime
 * with API bindings injected.
 */
public class ScriptManager {

    private static final Logger log = LoggerFactory.getLogger(ScriptManager.class);

    private final ChatMessageManager chatMessageManager;
    private final ConcurrentHashMap<String, LuaScript> scripts = new ConcurrentHashMap<>();

    public ScriptManager(ChatMessageManager chatMessageManager) {
        this.chatMessageManager = chatMessageManager;
    }

    /**
     * Load and start a Lua script from source.
     */
    public String load(String name, String source) {
        LuaScript existing = scripts.get(name);
        if (existing != null) {
            existing.stop();
        }

        LuaScript script = new LuaScript(name, source, chatMessageManager);
        scripts.put(name, script);
        script.start();
        log.info("Loaded script: {}", name);
        return name;
    }

    /**
     * Unload and stop a script.
     */
    public void unload(String name) {
        LuaScript script = scripts.remove(name);
        if (script != null) {
            script.stop();
            log.info("Unloaded script: {}", name);
        }
    }

    /**
     * Shut down all scripts.
     */
    public void shutdown() {
        for (LuaScript script : scripts.values()) {
            script.stop();
        }
        scripts.clear();
    }
}
