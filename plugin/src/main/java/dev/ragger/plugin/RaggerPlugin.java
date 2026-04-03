package dev.ragger.plugin;

import com.google.inject.Provides;
import dev.ragger.plugin.ui.ChatPanel;
import dev.ragger.plugin.wasm.ScriptManager;
import net.runelite.api.Client;
import net.runelite.api.events.GameTick;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.eventbus.Subscribe;
import net.runelite.client.plugins.Plugin;
import net.runelite.client.plugins.PluginDescriptor;
import net.runelite.client.ui.ClientToolbar;
import net.runelite.client.ui.NavigationButton;
import net.runelite.client.util.ImageUtil;

import javax.inject.Inject;
import java.awt.image.BufferedImage;

@PluginDescriptor(
    name = "Ragger",
    description = "AI assistant powered by Claude with Wasm scripting",
    tags = {"ai", "claude", "wasm", "assistant"}
)
public class RaggerPlugin extends Plugin {

    @Inject
    private Client client;

    @Inject
    private ClientToolbar clientToolbar;

    @Inject
    private RaggerConfig config;

    @Provides
    RaggerConfig provideConfig(ConfigManager configManager) {
        return configManager.getConfig(RaggerConfig.class);
    }

    private ChatPanel chatPanel;
    private NavigationButton navButton;
    private ScriptManager scriptManager;
    private ClaudeClient claude;

    @Override
    protected void startUp() {
        scriptManager = new ScriptManager(client);
        claude = new ClaudeClient(config.claudePath(), config.claudeModel());
        chatPanel = new ChatPanel(this::onUserMessage);

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
        scriptManager.shutdown();
    }

    @Subscribe
    public void onGameTick(GameTick event) {
        scriptManager.tick();
    }

    private void onUserMessage(String message) {
        if (message.equalsIgnoreCase("/reset")) {
            claude.resetSession();
            chatPanel.clear();
            chatPanel.addMessage("Claude", "Session reset.");
            return;
        }

        chatPanel.addMessage("You", message);
        chatPanel.showThinking();
        claude.send(message, "BASE", "ASSISTANT").thenAccept(response -> {
            chatPanel.addMessage("Claude", response);
        });
    }
}
