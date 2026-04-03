package dev.ragger.plugin;

import net.runelite.client.config.Config;
import net.runelite.client.config.ConfigGroup;
import net.runelite.client.config.ConfigItem;

@ConfigGroup("ragger")
public interface RaggerConfig extends Config {

    @ConfigItem(
        keyName = "claudePath",
        name = "Claude CLI Path",
        description = "Path to the Claude CLI executable",
        position = 0
    )
    default String claudePath() {
        return "claude";
    }

    @ConfigItem(
        keyName = "claudeModel",
        name = "Claude Model",
        description = "Model to use (e.g. claude-opus-4-6, claude-sonnet-4-6)",
        position = 1
    )
    default String claudeModel() {
        return "claude-opus-4-6";
    }
}
