package dev.ragger.plugin;

import com.google.inject.Provides;
import dev.ragger.plugin.ui.ChatPanel;
import dev.ragger.plugin.ui.ConsoleOverlay;
import dev.ragger.plugin.scripting.ScriptManager;
import dev.ragger.plugin.scripting.ScriptOverlay;
import net.runelite.api.Client;
import net.runelite.client.chat.ChatMessageManager;
import net.runelite.client.game.ItemManager;
import net.runelite.api.events.GameTick;
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
    description = "AI assistant powered by Claude with Lua scripting",
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
    private ScriptManager scriptManager;
    private ScriptOverlay scriptOverlay;
    private ConsoleOverlay consoleOverlay;
    private BridgeServer bridgeServer;
    private ClaudeClient claude;
    private net.runelite.client.input.KeyListener consoleKeyListener;
    private net.runelite.client.input.MouseWheelListener consoleMouseWheelListener;

    @Override
    protected void startUp() {
        scriptManager = new ScriptManager(client, chatMessageManager, itemManager);
        scriptOverlay = new ScriptOverlay(scriptManager);
        overlayManager.add(scriptOverlay);

        bridgeServer = new BridgeServer(scriptManager);
        try {
            bridgeServer.start(config.bridgePort());
        } catch (java.io.IOException e) {
            log.error("Failed to start bridge server", e);
        }

        claude = new ClaudeClient(config.claudePath(), config.claudeModel(), config.bridgePort(), bridgeServer.getToken(), config.devMode(), config.extraTools());
        chatPanel = new ChatPanel();
        chatPanel.setScriptManager(scriptManager);
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
        overlayManager.remove(scriptOverlay);
        overlayManager.remove(consoleOverlay);
        keyManager.unregisterKeyListener(consoleKeyListener);
        mouseManager.unregisterMouseWheelListener(consoleMouseWheelListener);
        bridgeServer.stop();
        scriptManager.shutdown();
    }

    @Subscribe
    public void onGameTick(GameTick event) {
        bridgeServer.tick();
        scriptManager.tick();
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
            scriptManager.shutdown();
            consoleOverlay.addToolMessage("All scripts stopped.");
            return;
        }

        if (message.startsWith("/stop ")) {
            String name = message.substring(6).trim();
            scriptManager.unload(name);
            consoleOverlay.addToolMessage("Stopped: " + name);
            return;
        }

        if (message.equalsIgnoreCase("/scripts")) {
            var names = scriptManager.list();
            if (names.isEmpty()) {
                consoleOverlay.addToolMessage("No active scripts.");
            } else {
                consoleOverlay.addToolMessage("Active scripts: " + String.join(", ", names));
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
