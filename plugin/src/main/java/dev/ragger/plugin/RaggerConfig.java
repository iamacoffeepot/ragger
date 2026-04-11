package dev.ragger.plugin;

import net.runelite.client.config.Config;
import net.runelite.client.config.ConfigGroup;
import net.runelite.client.config.ConfigItem;

@ConfigGroup("ragger")
public interface RaggerConfig extends Config {

    // -- Shared --

    @ConfigItem(
        keyName = "claudePath",
        name = "Claude CLI Path",
        description = "Path to the Claude CLI executable",
        position = 0,
        section = "shared"
    )
    default String claudePath() {
        return "claude";
    }

    @ConfigItem(
        keyName = "bridgePort",
        name = "Bridge Port",
        description = "HTTP port for MCP tool bridge",
        position = 1,
        section = "shared"
    )
    default int bridgePort() {
        return 7919;
    }

    @ConfigItem(
        keyName = "actorMaxDepth",
        name = "Actor Max Depth",
        description = "Maximum nesting depth for child actors",
        position = 2,
        section = "shared"
    )
    default int actorMaxDepth() {
        return 3;
    }

    @ConfigItem(
        keyName = "actorMaxChildren",
        name = "Actor Max Children",
        description = "Maximum number of direct children per parent actor",
        position = 3,
        section = "shared"
    )
    default int actorMaxChildren() {
        return 50;
    }

    // -- Console Claude --

    @ConfigItem(
        keyName = "consoleModel",
        name = "Console Model",
        description = "Model for the console Claude (e.g. claude-opus-4-6, claude-sonnet-4-6)",
        position = 10,
        section = "console"
    )
    default String consoleModel() {
        return "claude-opus-4-6";
    }

    @ConfigItem(
        keyName = "consoleDevMode",
        name = "Console Dev Mode",
        description = "Enable write tools (Edit, Write) for console Claude",
        position = 11,
        section = "console"
    )
    default boolean consoleDevMode() {
        return false;
    }

    @ConfigItem(
        keyName = "consoleExtraTools",
        name = "Console Extra Tools",
        description = "Comma-separated additional tools for console Claude",
        position = 12,
        section = "console"
    )
    default String consoleExtraTools() {
        return "";
    }

    // -- Agent Claude --

    @ConfigItem(
        keyName = "agentEnabled",
        name = "Agent Enabled",
        description = "Enable the background agent Claude instance",
        position = 20,
        section = "agent"
    )
    default boolean agentEnabled() {
        return false;
    }

    @ConfigItem(
        keyName = "agentModel",
        name = "Agent Model",
        description = "Model for the agent Claude (e.g. claude-sonnet-4-6, claude-haiku-4-5-20251001)",
        position = 21,
        section = "agent"
    )
    default String agentModel() {
        return "claude-sonnet-4-6";
    }

    @ConfigItem(
        keyName = "agentDevMode",
        name = "Agent Dev Mode",
        description = "Enable write tools (Edit, Write) for agent Claude",
        position = 22,
        section = "agent"
    )
    default boolean agentDevMode() {
        return false;
    }

    @ConfigItem(
        keyName = "agentExtraTools",
        name = "Agent Extra Tools",
        description = "Comma-separated additional tools for agent Claude",
        position = 23,
        section = "agent"
    )
    default String agentExtraTools() {
        return "";
    }

    @ConfigItem(
        keyName = "agentMaxRequests",
        name = "Agent Max Requests",
        description = "Restart agent after this many responses to keep context fresh (0 = never)",
        position = 24,
        section = "agent"
    )
    default int agentMaxRequests() {
        return 5;
    }
}
