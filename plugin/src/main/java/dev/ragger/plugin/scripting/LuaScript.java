package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.client.chat.ChatMessageManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import party.iroiro.luajava.Lua;
import party.iroiro.luajava.luaj.LuaJ;

/**
 * A single Lua script instance executed via LuaJ.
 *
 * Scripts can be one-shot (just runs top-to-bottom) or persistent
 * (returns a table with lifecycle hooks: on_start, on_tick, on_stop).
 */
public class LuaScript {

    private static final Logger log = LoggerFactory.getLogger(LuaScript.class);

    private final String name;
    private final String source;
    private final Client client;
    private final ChatMessageManager chatMessageManager;
    private Lua lua;
    private boolean running = false;
    private boolean hasHooks = false;

    public LuaScript(String name, String source, Client client, ChatMessageManager chatMessageManager) {
        this.name = name;
        this.source = source;
        this.client = client;
        this.chatMessageManager = chatMessageManager;
    }

    public void start() {
        if (running) return;

        try {
            lua = new LuaJ();
            lua.openLibrary("base");
            lua.openLibrary("string");
            lua.openLibrary("table");
            lua.openLibrary("math");

            lua.set("chat", new ChatApi(chatMessageManager));
            lua.set("camera", new CameraApi(client));
            lua.set("client", new ClientApi(client));

            lua.run(source);

            // Check if the script returned a hooks table
            if (lua.type(-1) == Lua.LuaType.TABLE) {
                lua.setGlobal("__hooks");
                hasHooks = true;
                callHook("on_start");
            }

            running = true;
            log.info("Script started: {} (hooks={})", name, hasHooks);
        } catch (Exception e) {
            log.error("Failed to start script: {}", name, e);
            stop();
        }
    }

    public void tick() {
        if (!running || !hasHooks) return;
        callHook("on_tick");
    }

    public void stop() {
        if (running && hasHooks) {
            callHook("on_stop");
        }
        if (lua != null) {
            lua.close();
            lua = null;
        }
        running = false;
        hasHooks = false;
        log.info("Script stopped: {}", name);
    }

    private void callHook(String hookName) {
        if (lua == null) return;

        try {
            lua.getGlobal("__hooks");
            lua.getField(-1, hookName);
            if (lua.type(-1) == Lua.LuaType.FUNCTION) {
                lua.pCall(0, 0);
            } else {
                lua.pop(1);
            }
            lua.pop(1); // pop __hooks
        } catch (Exception e) {
            log.error("Script '{}' hook '{}' error: {}", name, hookName, e.getMessage());
        }
    }

    public String getName() {
        return name;
    }

    public boolean isRunning() {
        return running;
    }

    public boolean hasHooks() {
        return hasHooks;
    }
}
