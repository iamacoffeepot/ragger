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

    @ConfigItem(
        keyName = "bridgePort",
        name = "Bridge Port",
        description = "HTTP port for MCP tool bridge",
        position = 2
    )
    default int bridgePort() {
        return 7919;
    }

    @ConfigItem(
        keyName = "devMode",
        name = "Developer Mode",
        description = "Enable write tools (Edit, Write, Bash) for in-plugin Claude",
        position = 3
    )
    default boolean devMode() {
        return false;
    }

    @ConfigItem(
        keyName = "extraTools",
        name = "Extra Tools",
        description = "Comma-separated additional tools to allow (e.g. Edit,Write,Agent)",
        position = 4
    )
    default String extraTools() {
        return "";
    }

    @ConfigItem(
        keyName = "actorMaxDepth",
        name = "Actor Max Depth",
        description = "Maximum nesting depth for child actors",
        position = 5
    )
    default int actorMaxDepth() {
        return 3;
    }

    @ConfigItem(
        keyName = "actorMaxChildren",
        name = "Actor Max Children",
        description = "Maximum number of direct children per parent actor",
        position = 6
    )
    default int actorMaxChildren() {
        return 50;
    }
}
