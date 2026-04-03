package dev.ragger.plugin.scripting;

import net.runelite.api.ChatMessageType;
import net.runelite.client.chat.ChatMessageManager;
import net.runelite.client.chat.QueuedMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import party.iroiro.luajava.Lua;
import party.iroiro.luajava.LuaException;
import party.iroiro.luajava.luaj.LuaJ;

/**
 * A single Lua script instance executed via LuaJ.
 * Scripts have access to injected API bindings.
 */
public class LuaScript {

    private static final Logger log = LoggerFactory.getLogger(LuaScript.class);

    private final String name;
    private final String source;
    private final ChatMessageManager chatMessageManager;
    private Lua lua;
    private boolean running = false;

    public LuaScript(String name, String source, ChatMessageManager chatMessageManager) {
        this.name = name;
        this.source = source;
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

            bindChatApi();

            lua.run(source);
            running = true;
            log.info("Script started: {}", name);
        } catch (Exception e) {
            log.error("Failed to start script: {}", name, e);
            stop();
        }
    }

    private void bindChatApi() {
        lua.createTable(0, 2);

        // chat.game(message) — send a game message
        lua.push((Lua L) -> {
            String msg = L.toString(1);
            if (msg != null && chatMessageManager != null) {
                chatMessageManager.queue(QueuedMessage.builder()
                    .type(ChatMessageType.GAMEMESSAGE)
                    .value(msg)
                    .build());
            }
            return 0;
        });
        lua.setField(-2, "game");

        // chat.console(message) — send a console message
        lua.push((Lua L) -> {
            String msg = L.toString(1);
            if (msg != null && chatMessageManager != null) {
                chatMessageManager.queue(QueuedMessage.builder()
                    .type(ChatMessageType.CONSOLE)
                    .value(msg)
                    .build());
            }
            return 0;
        });
        lua.setField(-2, "console");

        lua.setGlobal("chat");
    }

    public void stop() {
        if (lua != null) {
            lua.close();
            lua = null;
        }
        running = false;
        log.info("Script stopped: {}", name);
    }

    public String getName() {
        return name;
    }

    public boolean isRunning() {
        return running;
    }
}
