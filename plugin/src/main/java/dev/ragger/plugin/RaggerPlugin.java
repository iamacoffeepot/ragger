package dev.ragger.plugin;

import com.google.inject.Provides;
import dev.ragger.plugin.ui.ChatPanel;
import dev.ragger.plugin.ui.ConsoleOverlay;
import dev.ragger.plugin.scripting.ActorManager;
import dev.ragger.plugin.scripting.ActorOverlay;
import dev.ragger.plugin.scripting.LuaEvent;
import dev.ragger.plugin.scripting.ServiceManager;
import net.runelite.api.*;
import net.runelite.api.events.*;
import net.runelite.client.chat.ChatMessageManager;
import net.runelite.client.game.ItemManager;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.events.ConfigChanged;
import net.runelite.client.eventbus.Subscribe;
import net.runelite.client.input.KeyManager;
import net.runelite.client.input.MouseManager;
import net.runelite.client.plugins.Plugin;
import net.runelite.client.plugins.PluginDescriptor;
import net.runelite.client.ui.overlay.OverlayManager;
import net.runelite.client.ui.ClientToolbar;
import net.runelite.client.ui.NavigationButton;
import net.runelite.client.util.ImageUtil;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import java.awt.image.BufferedImage;

@PluginDescriptor(
    name = "Ragger",
    description = "AI assistant powered by Claude with Lua actors",
    tags = {"ai", "claude", "lua", "assistant"}
)
public class RaggerPlugin extends Plugin {

    private static final Logger log = LoggerFactory.getLogger(RaggerPlugin.class);

    @Inject
    private Client client;

    @Inject
    private ClientToolbar clientToolbar;

    @Inject
    private ChatMessageManager chatMessageManager;

    @Inject
    private OverlayManager overlayManager;

    @Inject
    private ItemManager itemManager;

    @Inject
    private KeyManager keyManager;

    @Inject
    private MouseManager mouseManager;

    @Inject
    private RaggerConfig config;

    @Provides
    RaggerConfig provideConfig(ConfigManager configManager) {
        return configManager.getConfig(RaggerConfig.class);
    }

    private ChatPanel chatPanel;
    private NavigationButton navButton;
    private ActorManager actorManager;
    private ServiceManager serviceManager;
    private ActorOverlay actorOverlay;
    private ConsoleOverlay consoleOverlay;
    private BridgeServer bridgeServer;
    private ClaudeClient claude;
    private net.runelite.client.input.KeyListener consoleKeyListener;
    private net.runelite.client.input.MouseWheelListener consoleMouseWheelListener;
    private net.runelite.client.input.MouseListener actorMouseListener;

    // Inventory snapshot for change detection
    private int[] prevInventoryIds = new int[28];
    private int[] prevInventoryQtys = new int[28];
    private int prevWorld = -1;

    @Override
    protected void startUp() {
        actorManager = new ActorManager(client, chatMessageManager, itemManager);
        actorManager.setLimits(config.actorMaxDepth(), config.actorMaxChildren());
        serviceManager = new ServiceManager(actorManager);
        actorOverlay = new ActorOverlay(actorManager);
        overlayManager.add(actorOverlay);

        bridgeServer = new BridgeServer(actorManager);
        try {
            bridgeServer.start(config.bridgePort());
        } catch (java.io.IOException e) {
            log.error("Failed to start bridge server", e);
        }

        claude = new ClaudeClient(config.claudePath(), config.claudeModel(), config.bridgePort(), bridgeServer.getToken(), config.devMode(), config.extraTools());
        chatPanel = new ChatPanel();
        chatPanel.setActorManager(actorManager);
        consoleOverlay = new ConsoleOverlay(client, this::onUserMessage);
        overlayManager.add(consoleOverlay);

        consoleKeyListener = new net.runelite.client.input.KeyListener() {
            @Override
            public void keyTyped(java.awt.event.KeyEvent e) {
                if (e.getKeyChar() == '`') {
                    consoleOverlay.toggle();
                    e.consume();
                    return;
                }
                consoleOverlay.handleKeyTyped(e);
            }

            @Override
            public void keyPressed(java.awt.event.KeyEvent e) {
                consoleOverlay.handleKeyPressed(e);
            }

            @Override
            public void keyReleased(java.awt.event.KeyEvent e) {}
        };
        keyManager.registerKeyListener(consoleKeyListener);

        consoleMouseWheelListener = e -> {
            if (consoleOverlay.isVisible()) {
                consoleOverlay.handleScroll(e.getWheelRotation());
                e.consume();
            }
            return e;
        };
        mouseManager.registerMouseWheelListener(consoleMouseWheelListener);

        actorMouseListener = new net.runelite.client.input.MouseListener() {
            @Override
            public java.awt.event.MouseEvent mouseClicked(java.awt.event.MouseEvent e) {
                actorManager.bufferEvent(LuaEvent.fromMouseClick(e));
                return e;
            }

            @Override
            public java.awt.event.MouseEvent mousePressed(java.awt.event.MouseEvent e) {
                return e;
            }

            @Override
            public java.awt.event.MouseEvent mouseReleased(java.awt.event.MouseEvent e) {
                return e;
            }

            @Override
            public java.awt.event.MouseEvent mouseEntered(java.awt.event.MouseEvent e) {
                return e;
            }

            @Override
            public java.awt.event.MouseEvent mouseExited(java.awt.event.MouseEvent e) {
                return e;
            }

            @Override
            public java.awt.event.MouseEvent mouseDragged(java.awt.event.MouseEvent e) {
                return e;
            }

            @Override
            public java.awt.event.MouseEvent mouseMoved(java.awt.event.MouseEvent e) {
                return e;
            }
        };
        mouseManager.registerMouseListener(actorMouseListener);

        BufferedImage icon = ImageUtil.loadImageResource(getClass(), "icon.png");
        navButton = NavigationButton.builder()
            .tooltip("Ragger")
            .icon(icon)
            .priority(5)
            .panel(chatPanel)
            .build();
        clientToolbar.addNavigation(navButton);
    }

    @Override
    protected void shutDown() {
        clientToolbar.removeNavigation(navButton);
        overlayManager.remove(actorOverlay);
        overlayManager.remove(consoleOverlay);
        keyManager.unregisterKeyListener(consoleKeyListener);
        mouseManager.unregisterMouseWheelListener(consoleMouseWheelListener);
        mouseManager.unregisterMouseListener(actorMouseListener);
        bridgeServer.stop();
        serviceManager.shutdown();
        actorManager.shutdown();
    }

    @Subscribe
    public void onGameTick(GameTick event) {
        serviceManager.start(); // no-op after first call
        bridgeServer.tick();
        actorManager.drainMail();
        actorManager.tick();
        diffInventory();
        actorManager.drainEvents();
        serviceManager.tick();
    }

    /**
     * Diff the inventory against the previous snapshot and buffer change events.
     */
    private void diffInventory() {
        ItemContainer inv = client.getItemContainer(InventoryID.INVENTORY);
        if (inv == null) return;

        Item[] items = inv.getItems();
        for (int i = 0; i < 28; i++) {
            int id = i < items.length ? items[i].getId() : -1;
            int qty = i < items.length ? items[i].getQuantity() : 0;
            if (id != prevInventoryIds[i] || qty != prevInventoryQtys[i]) {
                actorManager.bufferEvent(LuaEvent.fromInventoryChanged(
                    i, prevInventoryIds[i], prevInventoryQtys[i], id, qty));
                prevInventoryIds[i] = id;
                prevInventoryQtys[i] = qty;
            }
        }
    }

    // -- Game event subscriptions --

    @Subscribe
    public void onHitsplatApplied(HitsplatApplied event) {
        actorManager.bufferEvent(LuaEvent.fromHitsplat(event));
    }

    @Subscribe
    public void onProjectileMoved(ProjectileMoved event) {
        // Only buffer on first cycle to avoid duplicate events per projectile
        if (event.getProjectile().getRemainingCycles() == event.getProjectile().getEndCycle() - event.getProjectile().getStartCycle()) {
            actorManager.bufferEvent(LuaEvent.fromProjectile(event));
        }
    }

    @Subscribe
    public void onActorDeath(ActorDeath event) {
        actorManager.bufferEvent(LuaEvent.fromActorDeath(event));
    }

    @Subscribe
    public void onChatMessage(ChatMessage event) {
        actorManager.bufferEvent(LuaEvent.fromChat(event));
    }

    @Subscribe
    public void onItemSpawned(ItemSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromItemSpawned(event));
    }

    @Subscribe
    public void onItemDespawned(ItemDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromItemDespawned(event));
    }

    @Subscribe
    public void onStatChanged(StatChanged event) {
        actorManager.bufferEvent(LuaEvent.fromStatChanged(event));
    }

    @Subscribe
    public void onPlayerSpawned(PlayerSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromPlayerSpawned(event));
    }

    @Subscribe
    public void onPlayerDespawned(PlayerDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromPlayerDespawned(event));
    }

    @Subscribe
    public void onNpcSpawned(NpcSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromNpcSpawned(event));
    }

    @Subscribe
    public void onNpcDespawned(NpcDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromNpcDespawned(event));
    }

    @Subscribe
    public void onAnimationChanged(AnimationChanged event) {
        actorManager.bufferEvent(LuaEvent.fromAnimation(event.getActor(), event.getActor().getAnimation()));
    }

    @Subscribe
    public void onGraphicChanged(GraphicChanged event) {
        actorManager.bufferEvent(LuaEvent.fromGraphic(event.getActor(), event.getActor().getGraphic()));
    }

    @Subscribe
    public void onGameObjectSpawned(GameObjectSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromGameObjectSpawned(event));
    }

    @Subscribe
    public void onGameObjectDespawned(GameObjectDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromGameObjectDespawned(event));
    }

    @Subscribe
    public void onVarbitChanged(VarbitChanged event) {
        actorManager.bufferEvent(LuaEvent.fromVarpChanged(event));
    }

    @Subscribe
    public void onGameStateChanged(GameStateChanged event) {
        GameState state = event.getGameState();
        if (state == GameState.LOGGED_IN) {
            int world = client.getWorld();
            if (prevWorld == -1) {
                // First login
                actorManager.bufferEvent(LuaEvent.fromLogin());
            } else if (prevWorld != world) {
                actorManager.bufferEvent(LuaEvent.fromWorldChanged(prevWorld, world));
            }
            prevWorld = world;
        } else if (state == GameState.LOGIN_SCREEN && prevWorld != -1) {
            actorManager.bufferEvent(LuaEvent.fromLogout());
            prevWorld = -1;
        }
    }

    @Subscribe
    public void onWidgetLoaded(WidgetLoaded event) {
        actorManager.bufferEvent(LuaEvent.fromWidgetLoaded(event));
    }

    @Subscribe
    public void onWidgetClosed(WidgetClosed event) {
        actorManager.bufferEvent(LuaEvent.fromWidgetClosed(event));
    }

    @Subscribe
    public void onConfigChanged(ConfigChanged event) {
        if (!"ragger".equals(event.getGroup())) {
            return;
        }

        String key = event.getKey();

        if ("bridgePort".equals(key)) {
            bridgeServer.stop();
            try {
                bridgeServer.start(config.bridgePort());
            } catch (java.io.IOException e) {
                log.error("Failed to restart bridge server on new port", e);
            }
            // Recreate claude client with new bridge port
            claude = new ClaudeClient(config.claudePath(), config.claudeModel(), config.bridgePort(), bridgeServer.getToken(), config.devMode(), config.extraTools());
            log.info("Bridge server restarted on port {}", config.bridgePort());
        } else if ("claudePath".equals(key) || "claudeModel".equals(key) || "devMode".equals(key) || "extraTools".equals(key)) {
            claude = new ClaudeClient(config.claudePath(), config.claudeModel(), config.bridgePort(), bridgeServer.getToken(), config.devMode(), config.extraTools());
            log.info("Claude client recreated with updated config");
        }
    }

    private void onUserMessage(String message) {
        if (message.equalsIgnoreCase("/reset")) {
            claude.resetSession();
            consoleOverlay.clear();
            consoleOverlay.addMessage("Claude", "Session reset.");
            return;
        }

        if (message.equalsIgnoreCase("/clear")) {
            consoleOverlay.clear();
            return;
        }

        if (message.equalsIgnoreCase("/cancel")) {
            claude.cancel();
            return;
        }

        if (message.equalsIgnoreCase("/stop")) {
            serviceManager.shutdown();
            actorManager.shutdown();
            consoleOverlay.addToolMessage("All actors and services stopped.");
            return;
        }

        if (message.equalsIgnoreCase("/services")) {
            var statuses = serviceManager.status();
            if (statuses.isEmpty()) {
                consoleOverlay.addToolMessage("No managed services.");
            } else {
                StringBuilder sb = new StringBuilder("Services:");
                for (var s : statuses) {
                    sb.append("\n  ").append(s.name()).append(" (").append(s.template()).append(") — ");
                    if (s.dead()) {
                        sb.append("dead (").append(s.respawnAttempts()).append(" attempts)");
                    } else if (s.running()) {
                        sb.append("running");
                    } else {
                        sb.append("restarting...");
                    }
                }
                consoleOverlay.addToolMessage(sb.toString());
            }
            return;
        }

        if (message.startsWith("/revive ")) {
            String name = message.substring(8).trim();
            if (serviceManager.revive(name)) {
                consoleOverlay.addToolMessage("Reviving service: " + name);
            } else {
                consoleOverlay.addToolMessage("Unknown service: " + name);
            }
            return;
        }

        if (message.startsWith("/stop ")) {
            String name = message.substring(6).trim();
            actorManager.unload(name);
            consoleOverlay.addToolMessage("Stopped: " + name);
            return;
        }

        if (message.equalsIgnoreCase("/actors")) {
            var names = actorManager.list();
            if (names.isEmpty()) {
                consoleOverlay.addToolMessage("No active actors.");
            } else {
                consoleOverlay.addToolMessage("Active actors: " + String.join(", ", names));
            }
            return;
        }

        consoleOverlay.addMessage("You", message);
        consoleOverlay.addThinking();
        consoleOverlay.setBusy(true);
        claude.send(message, new ClaudeClient.StreamListener() {
            private boolean streaming = false;
            private boolean senderShown = false;

            @Override
            public void onText(String text) {
                consoleOverlay.removeThinking();
                if (!streaming) {
                    if (!senderShown) {
                        consoleOverlay.beginStream("Claude");
                        senderShown = true;
                    } else {
                        consoleOverlay.beginStreamContinuation();
                    }
                    streaming = true;
                }
                consoleOverlay.appendStream(text);
            }

            @Override
            public void onToolUse(String toolLog) {
                consoleOverlay.removeThinking();
                if (streaming) {
                    consoleOverlay.endStream();
                    streaming = false;
                }
                consoleOverlay.addToolMessage(toolLog);
            }

            @Override
            public void onComplete(String finalText) {
                consoleOverlay.removeThinking();
                if (streaming) {
                    consoleOverlay.endStream();
                    streaming = false;
                }
                consoleOverlay.setBusy(false);
                String queued = consoleOverlay.pollQueue();
                if (queued != null) {
                    onUserMessage(queued);
                }
            }

            @Override
            public void onError(String error) {
                consoleOverlay.removeThinking();
                if (streaming) {
                    consoleOverlay.endStream();
                    streaming = false;
                }
                consoleOverlay.addMessage("Claude", error);
                consoleOverlay.setBusy(false);
                String queued = consoleOverlay.pollQueue();
                if (queued != null) {
                    onUserMessage(queued);
                }
            }
            @Override
            public void onCancelled() {
                consoleOverlay.removeThinking();
                if (streaming) {
                    consoleOverlay.endStream();
                    streaming = false;
                }
                consoleOverlay.addToolMessage("Request cancelled.");
                consoleOverlay.setBusy(false);
            }
        }, "BASE", "ASSISTANT");
    }
}
