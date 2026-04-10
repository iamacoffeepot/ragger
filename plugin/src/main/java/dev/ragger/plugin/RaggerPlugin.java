package dev.ragger.plugin;

import com.google.inject.Provides;
import dev.ragger.plugin.ui.ChatPanel;
import dev.ragger.plugin.ui.ConsoleOverlay;
import dev.ragger.plugin.scripting.ActorManager;
import dev.ragger.plugin.scripting.ActorOverlay;
import dev.ragger.plugin.scripting.LuaEvent;
import dev.ragger.plugin.scripting.MinimapOverlay;
import dev.ragger.plugin.scripting.ServiceManager;
import net.runelite.api.Client;
import net.runelite.api.GameState;
import net.runelite.api.InventoryID;
import net.runelite.api.Item;
import net.runelite.api.ItemContainer;
import net.runelite.api.events.ActorDeath;
import net.runelite.api.events.AnimationChanged;
import net.runelite.api.events.ChatMessage;
import net.runelite.api.events.GameObjectDespawned;
import net.runelite.api.events.GameObjectSpawned;
import net.runelite.api.events.GameStateChanged;
import net.runelite.api.events.MenuOpened;
import net.runelite.api.events.ClientTick;
import net.runelite.api.events.GameTick;
import net.runelite.api.events.GraphicChanged;
import net.runelite.api.events.HitsplatApplied;
import net.runelite.api.events.ItemDespawned;
import net.runelite.api.events.ItemSpawned;
import net.runelite.api.events.NpcDespawned;
import net.runelite.api.events.NpcSpawned;
import net.runelite.api.events.PlayerDespawned;
import net.runelite.api.events.PlayerSpawned;
import net.runelite.api.events.ProjectileMoved;
import net.runelite.api.events.StatChanged;
import net.runelite.api.events.VarbitChanged;
import net.runelite.api.events.WidgetClosed;
import net.runelite.api.events.WidgetLoaded;
import net.runelite.client.chat.ChatMessageManager;
import net.runelite.client.game.ItemManager;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.events.ConfigChanged;
import net.runelite.client.eventbus.Subscribe;
import net.runelite.client.input.KeyListener;
import net.runelite.client.input.KeyManager;
import net.runelite.client.input.MouseListener;
import net.runelite.client.input.MouseManager;
import net.runelite.client.plugins.Plugin;
import net.runelite.client.plugins.PluginDescriptor;
import net.runelite.client.ui.overlay.OverlayManager;
import net.runelite.client.ui.overlay.worldmap.WorldMapPointManager;
import net.runelite.client.ui.ClientToolbar;
import net.runelite.client.ui.NavigationButton;
import net.runelite.client.util.ImageUtil;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import java.awt.event.KeyEvent;
import java.awt.event.MouseEvent;
import java.awt.image.BufferedImage;
import java.io.IOException;

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
    private WorldMapPointManager worldMapPointManager;

    @Inject
    private RaggerConfig config;

    @Provides
    RaggerConfig provideConfig(final ConfigManager configManager) {
        return configManager.getConfig(RaggerConfig.class);
    }

    private ChatPanel chatPanel;
    private NavigationButton navButton;
    private ActorManager actorManager;
    private ServiceManager serviceManager;
    private ActorOverlay actorOverlay;
    private MinimapOverlay minimapOverlay;
    private ConsoleOverlay consoleOverlay;
    private BridgeServer bridgeServer;
    private ClaudeClient claude;
    private KeyListener consoleKeyListener;
    private net.runelite.client.input.MouseWheelListener consoleMouseWheelListener;
    private MouseListener actorMouseListener;

    // Inventory snapshot for change detection
    private final int[] prevInventoryIds = new int[28];
    private final int[] prevInventoryQtys = new int[28];
    private int prevWorld = -1;

    @Override
    protected void startUp() {
        actorManager = new ActorManager(client, chatMessageManager, itemManager, worldMapPointManager);
        actorManager.setLimits(config.actorMaxDepth(), config.actorMaxChildren());
        serviceManager = new ServiceManager(actorManager);
        actorOverlay = new ActorOverlay(actorManager);
        minimapOverlay = new MinimapOverlay(actorManager);
        overlayManager.add(actorOverlay);
        overlayManager.add(minimapOverlay);

        bridgeServer = new BridgeServer(actorManager);
        try {
            bridgeServer.start(config.bridgePort());
        } catch (final IOException e) {
            log.error("Failed to start bridge server", e);
        }

        claude = new ClaudeClient(
            config.claudePath(),
            config.claudeModel(),
            config.bridgePort(),
            bridgeServer.getToken(),
            config.devMode(),
            config.extraTools()
        );
        chatPanel = new ChatPanel();
        chatPanel.setActorManager(actorManager);

        consoleOverlay = new ConsoleOverlay(client, this::onUserMessage);
        overlayManager.add(consoleOverlay);

        consoleKeyListener = new KeyListener() {
            @Override
            public void keyTyped(final KeyEvent e) {
                if (e.getKeyChar() == '`') {
                    consoleOverlay.toggle();
                    e.consume();
                    return;
                }
                consoleOverlay.handleKeyTyped(e);
            }

            @Override
            public void keyPressed(final KeyEvent e) {
                consoleOverlay.handleKeyPressed(e);
            }

            @Override
            public void keyReleased(final KeyEvent e) {}
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

        actorMouseListener = new MouseListener() {
            @Override
            public MouseEvent mouseClicked(final MouseEvent e) {
                actorManager.bufferEvent(LuaEvent.fromMouseClick(e));
                return e;
            }

            @Override
            public MouseEvent mousePressed(final MouseEvent e) {
                return e;
            }

            @Override
            public MouseEvent mouseReleased(final MouseEvent e) {
                return e;
            }

            @Override
            public MouseEvent mouseEntered(final MouseEvent e) {
                return e;
            }

            @Override
            public MouseEvent mouseExited(final MouseEvent e) {
                return e;
            }

            @Override
            public MouseEvent mouseDragged(final MouseEvent e) {
                return e;
            }

            @Override
            public MouseEvent mouseMoved(final MouseEvent e) {
                return e;
            }
        };
        mouseManager.registerMouseListener(actorMouseListener);

        final BufferedImage icon = ImageUtil.loadImageResource(getClass(), "icon.png");
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
        overlayManager.remove(minimapOverlay);
        overlayManager.remove(consoleOverlay);
        keyManager.unregisterKeyListener(consoleKeyListener);
        mouseManager.unregisterMouseWheelListener(consoleMouseWheelListener);
        mouseManager.unregisterMouseListener(actorMouseListener);
        bridgeServer.stop();
        serviceManager.shutdown();
        actorManager.shutdown();
    }

    @Subscribe
    public void onClientTick(final ClientTick event) {
        actorManager.frame();
    }

    @Subscribe
    public void onGameTick(final GameTick event) {
        serviceManager.start(); // no-op after first call
        bridgeServer.tick();
        diffInventory();
        actorManager.markGameTick();
        serviceManager.tick();
    }

    /**
     * Diff the inventory against the previous snapshot and buffer change events.
     */
    private void diffInventory() {
        final ItemContainer inv = client.getItemContainer(InventoryID.INVENTORY);
        if (inv == null) {
            return;
        }

        final Item[] items = inv.getItems();

        for (int i = 0; i < 28; i++) {
            final int id = i < items.length ? items[i].getId() : -1;
            final int qty = i < items.length ? items[i].getQuantity() : 0;

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
    public void onHitsplatApplied(final HitsplatApplied event) {
        actorManager.bufferEvent(LuaEvent.fromHitsplat(event));
    }

    @Subscribe
    public void onProjectileMoved(final ProjectileMoved event) {
        // Only buffer on first cycle to avoid duplicate events per projectile
        final var projectile = event.getProjectile();
        final int remaining = projectile.getRemainingCycles();
        final int total = projectile.getEndCycle() - projectile.getStartCycle();

        if (remaining == total) {
            actorManager.bufferEvent(LuaEvent.fromProjectile(event));
        }
    }

    @Subscribe
    public void onActorDeath(final ActorDeath event) {
        actorManager.bufferEvent(LuaEvent.fromActorDeath(event));
    }

    @Subscribe
    public void onChatMessage(final ChatMessage event) {
        actorManager.bufferEvent(LuaEvent.fromChat(event));
    }

    @Subscribe
    public void onItemSpawned(final ItemSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromItemSpawned(event));
    }

    @Subscribe
    public void onItemDespawned(final ItemDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromItemDespawned(event));
    }

    @Subscribe
    public void onStatChanged(final StatChanged event) {
        actorManager.bufferEvent(LuaEvent.fromStatChanged(event));
    }

    @Subscribe
    public void onPlayerSpawned(final PlayerSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromPlayerSpawned(event));
    }

    @Subscribe
    public void onPlayerDespawned(final PlayerDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromPlayerDespawned(event));
    }

    @Subscribe
    public void onNpcSpawned(final NpcSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromNpcSpawned(event));
    }

    @Subscribe
    public void onNpcDespawned(final NpcDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromNpcDespawned(event));
    }

    @Subscribe
    public void onAnimationChanged(final AnimationChanged event) {
        final var actor = event.getActor();
        actorManager.bufferEvent(LuaEvent.fromAnimation(actor, actor.getAnimation()));
    }

    @Subscribe
    public void onGraphicChanged(final GraphicChanged event) {
        final var actor = event.getActor();
        actorManager.bufferEvent(LuaEvent.fromGraphic(actor, actor.getGraphic()));
    }

    @Subscribe
    public void onGameObjectSpawned(final GameObjectSpawned event) {
        actorManager.bufferEvent(LuaEvent.fromGameObjectSpawned(event));
    }

    @Subscribe
    public void onGameObjectDespawned(final GameObjectDespawned event) {
        actorManager.bufferEvent(LuaEvent.fromGameObjectDespawned(event));
    }

    @Subscribe
    public void onVarbitChanged(final VarbitChanged event) {
        actorManager.bufferEvent(LuaEvent.fromVarpChanged(event));
    }

    @Subscribe
    public void onGameStateChanged(final GameStateChanged event) {
        final GameState state = event.getGameState();

        if (state == GameState.LOGGED_IN) {
            final int world = client.getWorld();

            if (prevWorld == -1) {
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
    public void onWidgetLoaded(final WidgetLoaded event) {
        actorManager.bufferEvent(LuaEvent.fromWidgetLoaded(event));
    }

    @Subscribe
    public void onWidgetClosed(final WidgetClosed event) {
        actorManager.bufferEvent(LuaEvent.fromWidgetClosed(event));
    }

    @Subscribe
    public void onMenuOpened(final MenuOpened event) {
        actorManager.bufferEvent(LuaEvent.fromMenuOpened(event));
    }

    @Subscribe
    public void onConfigChanged(final ConfigChanged event) {
        if (!"ragger".equals(event.getGroup())) {
            return;
        }

        final String key = event.getKey();

        if ("bridgePort".equals(key)) {
            bridgeServer.stop();
            try {
                bridgeServer.start(config.bridgePort());
            } catch (final IOException e) {
                log.error("Failed to restart bridge server on new port", e);
            }

            claude = new ClaudeClient(
                config.claudePath(),
                config.claudeModel(),
                config.bridgePort(),
                bridgeServer.getToken(),
                config.devMode(),
                config.extraTools()
            );
            log.info("Bridge server restarted on port {}", config.bridgePort());
        } else if ("claudePath".equals(key) || "claudeModel".equals(key) || "devMode".equals(key) || "extraTools".equals(key)) {
            claude = new ClaudeClient(
                config.claudePath(),
                config.claudeModel(),
                config.bridgePort(),
                bridgeServer.getToken(),
                config.devMode(),
                config.extraTools()
            );
            log.info("Claude client recreated with updated config");
        }
    }

    private void onUserMessage(final String message) {
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
            final var statuses = serviceManager.status();

            if (statuses.isEmpty()) {
                consoleOverlay.addToolMessage("No managed services.");
            } else {
                final StringBuilder sb = new StringBuilder("Services:");

                for (final var s : statuses) {
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
            final String name = message.substring(8).trim();

            if (serviceManager.revive(name)) {
                consoleOverlay.addToolMessage("Reviving service: " + name);
            } else {
                consoleOverlay.addToolMessage("Unknown service: " + name);
            }
            return;
        }

        if (message.startsWith("/stop ")) {
            final String name = message.substring(6).trim();
            actorManager.unload(name);
            consoleOverlay.addToolMessage("Stopped: " + name);
            return;
        }

        if (message.equalsIgnoreCase("/actors")) {
            final var names = actorManager.list();

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
            public void onText(final String text) {
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
            public void onToolUse(final String toolLog) {
                consoleOverlay.removeThinking();

                if (streaming) {
                    consoleOverlay.endStream();
                    streaming = false;
                }

                consoleOverlay.addToolMessage(toolLog);
            }

            @Override
            public void onComplete(final String finalText) {
                consoleOverlay.removeThinking();

                if (streaming) {
                    consoleOverlay.endStream();
                    streaming = false;
                }

                consoleOverlay.setBusy(false);

                final String queued = consoleOverlay.pollQueue();
                if (queued != null) {
                    onUserMessage(queued);
                }
            }

            @Override
            public void onError(final String error) {
                consoleOverlay.removeThinking();

                if (streaming) {
                    consoleOverlay.endStream();
                    streaming = false;
                }

                consoleOverlay.addMessage("Claude", error);
                consoleOverlay.setBusy(false);

                final String queued = consoleOverlay.pollQueue();
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
                consoleOverlay.clearQueue();
                consoleOverlay.setBusy(false);
            }
        }, "BASE", "ASSISTANT");
    }
}
