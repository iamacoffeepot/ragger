package dev.ragger.plugin;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * Manages communication with the Claude CLI with persistent sessions.
 * Uses stream-json output to capture both chat text and tool calls.
 */
public class ClaudeClient {

    private static final Logger log = LoggerFactory.getLogger(ClaudeClient.class);

    private final String claudePath;
    private final String model;
    private final int bridgePort;
    private final String bridgeToken;
    private String sessionId;

    public ClaudeClient(String claudePath, String model, int bridgePort, String bridgeToken) {
        this.claudePath = claudePath;
        this.model = model;
        this.bridgePort = bridgePort;
        this.bridgeToken = bridgeToken;
    }

    /**
     * Send a message to Claude asynchronously with the given behavior profiles.
     */
    public CompletableFuture<ClaudeResponse> send(String message, String... behaviors) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return execute(message, behaviors);
            } catch (Exception e) {
                log.error("Claude CLI error", e);
                return new ClaudeResponse("Error: " + e.getMessage(), List.of());
            }
        });
    }

    private ClaudeResponse execute(String message, String... behaviors) throws IOException, InterruptedException {
        List<String> command = new ArrayList<>();
        command.add(claudePath);
        command.add("-p");
        command.add(message);
        command.add("--output-format");
        command.add("stream-json");
        command.add("--verbose");
        command.add("--model");
        command.add(model);
        command.add("--allowedTools");
        command.add("Bash");
        command.add("Read");
        command.add("Glob");
        command.add("Grep");
        command.add("mcp__ragger__RaggerRun");
        command.add("mcp__ragger__RaggerEval");

        // Load Ragger MCP tools only for plugin sessions
        command.add("--mcp-config");
        command.add("{\"mcpServers\":{\"ragger\":{\"type\":\"stdio\",\"command\":\"uv\",\"args\":[\"run\",\"python\",\"src/ragger/mcp_server.py\"]}}}");

        String systemPrompt = loadBehaviors(behaviors);
        if (!systemPrompt.isEmpty()) {
            command.add("--append-system-prompt");
            command.add(systemPrompt);
        }

        if (sessionId != null) {
            command.add("--resume");
            command.add(sessionId);
        }

        ProcessBuilder pb = new ProcessBuilder(command);
        String projectRoot = System.getenv("RAGGER_PROJECT_ROOT");
        if (projectRoot != null) {
            pb.directory(new java.io.File(projectRoot));
        }
        pb.environment().put("RAGGER_BRIDGE_PORT", String.valueOf(bridgePort));
        pb.environment().put("RAGGER_BRIDGE_TOKEN", bridgeToken);
        pb.redirectErrorStream(true);
        pb.redirectInput(ProcessBuilder.Redirect.from(new java.io.File("/dev/null")));
        Process process = pb.start();

        StringBuilder resultText = new StringBuilder();
        List<String> toolLog = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                processStreamLine(line, resultText, toolLog);
            }
        }

        boolean finished = process.waitFor(120, java.util.concurrent.TimeUnit.SECONDS);
        if (!finished) {
            log.warn("Claude CLI timed out after 120s, killing process");
            process.destroyForcibly();
            if (resultText.isEmpty()) {
                resultText.append("Request timed out. Try again or /reset the session.");
            }
        } else if (process.exitValue() != 0) {
            log.warn("Claude CLI exited with code {}", process.exitValue());
        }

        return new ClaudeResponse(resultText.toString(), toolLog);
    }

    private void processStreamLine(String line, StringBuilder resultText, List<String> toolLog) {
        if (line.isBlank()) return;

        try {
            JsonObject event = new JsonParser().parse(line).getAsJsonObject();

            // Capture session ID from result event
            if (event.has("session_id")) {
                sessionId = event.get("session_id").getAsString();
                log.info("Session ID: {}", sessionId);
            }

            // Final result text
            if (event.has("result")) {
                resultText.append(event.get("result").getAsString());
            }

            // Process assistant messages for tool use
            if (event.has("type") && "assistant".equals(event.get("type").getAsString())) {
                if (event.has("message")) {
                    processToolUse(event.getAsJsonObject("message"), toolLog);
                }
            }
        } catch (Exception e) {
            // Not all lines are JSON (e.g. stderr), log for debugging
            log.debug("Non-JSON stream line: {}", line);
        }
    }

    private void processToolUse(JsonObject event, List<String> toolLog) {
        try {
            if (event.has("content")) {
                for (JsonElement element : event.getAsJsonArray("content")) {
                    JsonObject block = element.getAsJsonObject();
                    if (!"tool_use".equals(block.get("type").getAsString())) continue;

                    String toolName = block.get("name").getAsString();
                    JsonObject input = block.has("input") ? block.getAsJsonObject("input") : null;
                    toolLog.add(formatToolLog(toolName, input));
                }
            }

            if (event.has("name")) {
                String toolName = event.get("name").getAsString();
                JsonObject input = event.has("input") ? event.getAsJsonObject("input") : null;
                toolLog.add(formatToolLog(toolName, input));
            }
        } catch (Exception e) {
            log.debug("Error processing tool use event", e);
        }
    }

    private String formatToolLog(String toolName, JsonObject input) {
        // Strip mcp__ prefix for display
        String displayName = toolName.replaceFirst("^mcp__\\w+__", "");

        if (input == null) return displayName + "()";

        // Format like Claude Code: Tool(arg1, arg2, ...)
        if (input.has("command")) {
            return displayName + "(" + truncate(input.get("command").getAsString(), 60) + ")";
        }
        if (input.has("pattern")) {
            return displayName + "(" + input.get("pattern").getAsString() + ")";
        }
        if (input.has("file_path")) {
            return displayName + "(" + input.get("file_path").getAsString() + ")";
        }
        if (input.has("script")) {
            String name = input.has("name") ? input.get("name").getAsString() : "";
            return displayName + "(" + name + ", ...)";
        }
        return displayName + "()";
    }

    private static String truncate(String s, int maxLen) {
        if (s.length() <= maxLen) return s;
        return s.substring(0, maxLen) + "...";
    }

    /**
     * Load behavior files from classpath resources and concatenate them.
     */
    private String loadBehaviors(String... behaviors) {
        StringBuilder sb = new StringBuilder();
        for (String behavior : behaviors) {
            String resource = behavior + ".md";
            try (InputStream is = getClass().getResourceAsStream(resource)) {
                if (is == null) {
                    log.warn("Behavior resource not found: {}", resource);
                    continue;
                }
                if (!sb.isEmpty()) {
                    sb.append("\n\n");
                }
                String content = new String(is.readAllBytes(), StandardCharsets.UTF_8);
                sb.append(content);
                log.info("Loaded behavior '{}': {} chars", behavior, content.length());
            } catch (IOException e) {
                log.error("Failed to load behavior: {}", behavior, e);
            }
        }
        return sb.toString();
    }

    /**
     * Reset the session — next message starts a fresh conversation.
     */
    public void resetSession() {
        sessionId = null;
    }
}
