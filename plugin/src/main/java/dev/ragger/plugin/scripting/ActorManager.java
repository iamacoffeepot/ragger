package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.client.chat.ChatMessageManager;
import net.runelite.client.game.ItemManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Manages Lua actor lifecycles. Each script gets its own LuaJ runtime
 * with API bindings injected.
 *
 * Scripts are stored in a flat map with "/" namespacing for parent-child
 * relationships. A script "foo" that spawns "bar" creates "foo/bar".
 * Stopping a parent cascade-stops all children.
 */
public class ActorManager {

    private static final Logger log = LoggerFactory.getLogger(ActorManager.class);

    private final Client client;
    private final ChatMessageManager chatMessageManager;
    private final ItemManager itemManager;
    private final ConcurrentHashMap<String, LuaActor> scripts = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, String> templates = new ConcurrentHashMap<>();
    private final CopyOnWriteArrayList<Runnable> changeListeners = new CopyOnWriteArrayList<>();

    private final ConcurrentLinkedQueue<MailMessage> mailQueue = new ConcurrentLinkedQueue<>();
    private final ConcurrentLinkedQueue<MailMessage> claudeMailbox = new ConcurrentLinkedQueue<>();
    private final ConcurrentLinkedQueue<LuaEvent> eventQueue = new ConcurrentLinkedQueue<>();

    /** Map from event type to Lua hook name. */
    private static final Map<LuaEvent.Type, String> HOOK_NAMES = new EnumMap<>(LuaEvent.Type.class);
    static {
        HOOK_NAMES.put(LuaEvent.Type.HITSPLAT, "on_hitsplat");
        HOOK_NAMES.put(LuaEvent.Type.PROJECTILE, "on_projectile");
        HOOK_NAMES.put(LuaEvent.Type.DEATH, "on_death");
        HOOK_NAMES.put(LuaEvent.Type.CHAT, "on_chat");
        HOOK_NAMES.put(LuaEvent.Type.ITEM_SPAWNED, "on_item_spawned");
        HOOK_NAMES.put(LuaEvent.Type.ITEM_DESPAWNED, "on_item_despawned");
        HOOK_NAMES.put(LuaEvent.Type.INVENTORY_CHANGED, "on_inventory_changed");
        HOOK_NAMES.put(LuaEvent.Type.XP_DROP, "on_xp_drop");
        HOOK_NAMES.put(LuaEvent.Type.PLAYER_SPAWNED, "on_player_spawned");
        HOOK_NAMES.put(LuaEvent.Type.PLAYER_DESPAWNED, "on_player_despawned");
        HOOK_NAMES.put(LuaEvent.Type.NPC_SPAWNED, "on_npc_spawned");
        HOOK_NAMES.put(LuaEvent.Type.NPC_DESPAWNED, "on_npc_despawned");
        HOOK_NAMES.put(LuaEvent.Type.ANIMATION, "on_animation");
        HOOK_NAMES.put(LuaEvent.Type.GRAPHIC, "on_graphic");
        HOOK_NAMES.put(LuaEvent.Type.GAME_OBJECT_SPAWNED, "on_object_spawned");
        HOOK_NAMES.put(LuaEvent.Type.GAME_OBJECT_DESPAWNED, "on_object_despawned");
        HOOK_NAMES.put(LuaEvent.Type.VARP_CHANGED, "on_varp_changed");
        HOOK_NAMES.put(LuaEvent.Type.LOGIN, "on_login");
        HOOK_NAMES.put(LuaEvent.Type.LOGOUT, "on_logout");
        HOOK_NAMES.put(LuaEvent.Type.WORLD_CHANGED, "on_world_changed");
        HOOK_NAMES.put(LuaEvent.Type.WIDGET_LOADED, "on_widget_loaded");
        HOOK_NAMES.put(LuaEvent.Type.WIDGET_CLOSED, "on_widget_closed");
        HOOK_NAMES.put(LuaEvent.Type.MOUSE_CLICK, "on_mouse_click");
    }

    private int maxDepth = 3;
    private int maxChildren = 50;

    public ActorManager(Client client, ChatMessageManager chatMessageManager, ItemManager itemManager) {
        this.client = client;
        this.chatMessageManager = chatMessageManager;
        this.itemManager = itemManager;
    }

    /**
     * Update script limits from config.
     */
    public void setLimits(int maxDepth, int maxChildren) {
        this.maxDepth = maxDepth;
        this.maxChildren = maxChildren;
    }

    /**
     * Register a listener that is called whenever scripts or templates change.
     */
    public void addChangeListener(Runnable listener) {
        changeListeners.add(listener);
    }

    private void fireChange() {
        for (Runnable listener : changeListeners) {
            try {
                listener.run();
            } catch (Exception e) {
                log.warn("Change listener error", e);
            }
        }
    }

    /**
     * Load and start a Lua script from source (top-level, no parent).
     */
    public String load(String name, String source) {
        return load(name, source, null);
    }

    /**
     * Load and start a Lua script from source with optional args table.
     */
    /**
     * Thrown when an actor cannot be loaded due to a limit violation.
     */
    public static class ActorLimitException extends RuntimeException {
        public ActorLimitException(String message) {
            super(message);
        }
    }

    public String load(String name, String source, Map<String, Object> args) {
        // Check depth limit
        long depth = name.chars().filter(c -> c == '/').count();
        if (depth >= maxDepth) {
            throw new ActorLimitException("depth limit reached (max " + maxDepth + ")");
        }

        // Check children limit for the parent
        int lastSlash = name.lastIndexOf('/');
        if (lastSlash > 0) {
            String parent = name.substring(0, lastSlash);
            long childCount = scripts.keySet().stream()
                .filter(k -> k.startsWith(parent + "/"))
                .filter(k -> k.indexOf('/', parent.length() + 1) == -1)
                .filter(k -> !k.equals(name)) // don't count replacement
                .count();
            if (childCount >= maxChildren) {
                throw new ActorLimitException("child limit reached for " + parent + " (max " + maxChildren + ")");
            }
        }

        LuaActor existing = scripts.get(name);
        if (existing != null) {
            existing.stop();
        }

        LuaActor script = new LuaActor(name, source, client, chatMessageManager, itemManager, this, args);
        scripts.put(name, script);
        script.start();
        log.info("Loaded actor: {}", name);
        fireChange();
        return name;
    }

    /**
     * Called every game tick — dispatches to all active scripts with hooks.
     */
    /**
     * Enqueue a mail message for delivery on the next drain.
     */
    public void enqueueMail(String from, String to, Map<String, Object> data) {
        mailQueue.add(new MailMessage(from, to, data));
    }

    /**
     * Drain the mail queue and deliver messages to recipients.
     * Uses snapshot pattern — messages sent during delivery queue for next drain.
     */
    public void drainMail() {
        List<MailMessage> batch = new ArrayList<>();
        MailMessage msg;
        while ((msg = mailQueue.poll()) != null) {
            batch.add(msg);
        }

        for (MailMessage m : batch) {
            if ("claude".equals(m.to())) {
                claudeMailbox.add(m);
                continue;
            }
            LuaActor target = scripts.get(m.to());
            if (target == null || !target.isRunning()) {
                log.debug("Mail dropped: target '{}' not found or not running", m.to());
                continue;
            }
            if (!target.deliverMail(m.from(), m.data())) {
                target.stop();
                scripts.remove(m.to());
                log.info("Actor '{}' self-stopped via on_mail", m.to());
                fireChange();
            }
        }
    }

    /**
     * Drain all messages addressed to "claude" and return them.
     */
    public List<MailMessage> drainClaudeMailbox() {
        List<MailMessage> messages = new ArrayList<>();
        MailMessage msg;
        while ((msg = claudeMailbox.poll()) != null) {
            messages.add(msg);
        }
        return messages;
    }

    /**
     * Drain up to {@code limit} messages from the claude mailbox, optionally filtered by sender.
     * If limit <= 0, drains all matching messages. The fromFilter is a regex pattern
     * (e.g. "loot-.*", "quest-guide/.*", or an exact name like "ping").
     */
    public List<MailMessage> drainClaudeMailbox(int limit, String fromFilter) {
        java.util.regex.Pattern pattern = compileFromFilter(fromFilter);
        List<MailMessage> matched = new ArrayList<>();
        List<MailMessage> skipped = new ArrayList<>();

        MailMessage msg;
        while ((msg = claudeMailbox.poll()) != null) {
            boolean matches = (pattern == null || pattern.matcher(msg.from()).matches());
            if (matches && (limit <= 0 || matched.size() < limit)) {
                matched.add(msg);
            } else {
                skipped.add(msg);
            }
        }

        // Put non-matching messages back
        for (MailMessage s : skipped) {
            claudeMailbox.add(s);
        }
        return matched;
    }

    /**
     * Count how many claude mailbox messages match the given filter, without consuming them.
     */
    public int countClaudeMailbox(String fromFilter) {
        java.util.regex.Pattern pattern = compileFromFilter(fromFilter);
        int count = 0;
        for (MailMessage msg : claudeMailbox) {
            if (pattern == null || pattern.matcher(msg.from()).matches()) {
                count++;
            }
        }
        return count;
    }

    private static final int MAX_FILTER_LENGTH = 200;

    private static java.util.regex.Pattern compileFromFilter(String fromFilter) {
        if (fromFilter == null || fromFilter.isEmpty()) {
            return null;
        }
        if (fromFilter.length() > MAX_FILTER_LENGTH) {
            return java.util.regex.Pattern.compile(java.util.regex.Pattern.quote(fromFilter));
        }
        try {
            return java.util.regex.Pattern.compile(fromFilter);
        } catch (java.util.regex.PatternSyntaxException e) {
            return java.util.regex.Pattern.compile(java.util.regex.Pattern.quote(fromFilter));
        }
    }

    public void tick() {
        var it = scripts.entrySet().iterator();
        while (it.hasNext()) {
            var entry = it.next();
            LuaActor script = entry.getValue();
            script.tick();
            if (script.shouldStop()) {
                script.stop();
                it.remove();
                log.info("Script self-stopped: {}", entry.getKey());
                fireChange();
            }
        }
    }

    /**
     * Buffer a game event for delivery to actors on the next drainEvents() call.
     */
    public void bufferEvent(LuaEvent event) {
        eventQueue.add(event);
    }

    /**
     * Drain buffered events and deliver to all actors that define the matching hook.
     * Called after tick() — actors see on_tick first, then events from that tick.
     */
    public void drainEvents() {
        List<LuaEvent> batch = new ArrayList<>();
        LuaEvent evt;
        while ((evt = eventQueue.poll()) != null) {
            batch.add(evt);
        }

        if (batch.isEmpty()) return;

        for (LuaEvent event : batch) {
            String hookName = HOOK_NAMES.get(event.getType());
            if (hookName == null) continue;

            var it = scripts.entrySet().iterator();
            while (it.hasNext()) {
                var entry = it.next();
                LuaActor script = entry.getValue();
                if (!script.deliverEvent(hookName, event.getData())) {
                    script.stop();
                    it.remove();
                    log.info("Actor '{}' self-stopped via {}", entry.getKey(), hookName);
                    fireChange();
                }
            }
        }
    }

    /**
     * Evaluate a Lua expression and return the result as a string.
     * Runs in a temporary LuaJ runtime with all API bindings.
     */
    public String eval(String script) {
        LuaActor temp = new LuaActor("__eval", "return " + script, client, chatMessageManager, itemManager, this, null);
        try {
            return temp.evalAndReturn();
        } finally {
            temp.stop();
        }
    }

    /**
     * Unload and stop a script and all its children.
     */
    public void unload(String name) {
        // Stop children first
        String prefix = name + "/";
        var it = scripts.entrySet().iterator();
        while (it.hasNext()) {
            var entry = it.next();
            if (entry.getKey().startsWith(prefix)) {
                entry.getValue().stop();
                it.remove();
                log.info("Cascade-unloaded actor: {}", entry.getKey());
            }
        }

        // Stop the script itself
        LuaActor script = scripts.remove(name);
        if (script != null) {
            script.stop();
            log.info("Unloaded actor: {}", name);
        }
        fireChange();
    }

    /**
     * Resolve a child name relative to a parent.
     * Child names must not contain '/' or '..' to prevent namespace escaping.
     */
    public String childName(String parent, String child) {
        if (child == null || child.isEmpty() || child.contains("/") || child.contains("..")) {
            throw new IllegalArgumentException("invalid child name: must not be empty or contain '/' or '..'");
        }
        return parent + "/" + child;
    }

    /**
     * List direct children of a parent script.
     */
    public List<String> listChildren(String parent) {
        String prefix = parent + "/";
        List<String> result = new ArrayList<>();
        for (String key : scripts.keySet()) {
            if (key.startsWith(prefix)) {
                // Only direct children (no further slashes after prefix)
                String rest = key.substring(prefix.length());
                if (!rest.contains("/")) {
                    result.add(rest);
                }
            }
        }
        return result;
    }

    /**
     * Register a template (script blueprint).
     */
    public void defineTemplate(String name, String source) {
        templates.put(name, source);
        log.info("Defined template: {}", name);
        fireChange();
    }

    /**
     * Get a template's source by name.
     */
    public String getTemplate(String name) {
        return templates.get(name);
    }

    /**
     * List all registered template names.
     */
    public List<String> listTemplates() {
        return new ArrayList<>(templates.keySet());
    }

    /**
     * Called during overlay render — dispatches to all active scripts with hooks.
     */
    public void render(java.awt.Graphics2D graphics) {
        for (LuaActor script : scripts.values()) {
            script.render(graphics);
        }
    }

    /**
     * List all active script names.
     */
    public List<String> list() {
        return new ArrayList<>(scripts.keySet());
    }

    /**
     * Get the source code of a running script by name.
     */
    public String getSource(String name) {
        LuaActor script = scripts.get(name);
        return script != null ? script.getSource() : null;
    }

    /**
     * Check if a script is running.
     */
    public boolean isRunning(String name) {
        LuaActor script = scripts.get(name);
        return script != null && script.isRunning();
    }

    /**
     * Shut down all scripts and clear templates.
     */
    public void shutdown() {
        for (LuaActor script : scripts.values()) {
            script.stop();
        }
        scripts.clear();
        templates.clear();
        fireChange();
    }
}
