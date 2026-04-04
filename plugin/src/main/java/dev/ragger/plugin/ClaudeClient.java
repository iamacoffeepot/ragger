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
import java.util.function.Consumer;

/**
 * Manages communication with the Claude CLI with persistent sessions.
 * Streams text as it arrives via a callback.
 */
public class ClaudeClient {

    private static final Logger log = LoggerFactory.getLogger(ClaudeClient.class);

    private final String claudePath;
    private final String model;
    private final int bridgePort;
    private final String bridgeToken;
    private final boolean devMode;
    private final String extraTools;
    private String sessionId;
    private volatile Process currentProcess;
    private volatile boolean cancelled;

    public ClaudeClient(String claudePath, String model, int bridgePort, String bridgeToken, boolean devMode, String extraTools) {
        this.claudePath = claudePath;
        this.model = model;
        this.bridgePort = bridgePort;
        this.bridgeToken = bridgeToken;
        this.devMode = devMode;
        this.extraTools = extraTools;
    }

    /**
     * Callback interface for streaming events.
     */
    public interface StreamListener {
        void onText(String text);
        void onToolUse(String toolLog);
        void onComplete(String finalText);
        void onError(String error);
        void onCancelled();
    }

    /**
     * Cancel the current request, killing the Claude CLI process.
     */
    public void cancel() {
        cancelled = true;
        Process p = currentProcess;
        if (p != null) {
            p.destroyForcibly();
            log.info("Claude CLI process cancelled");
        }
    }

    public boolean isBusy() {
        return currentProcess != null;
    }

    /**
     * Send a message to Claude, streaming responses via the listener.
     */
    public void send(String message, StreamListener listener, String... behaviors) {
        CompletableFuture.runAsync(() -> {
            try {
                execute(message, listener, behaviors);
            } catch (Exception e) {
                log.error("Claude CLI error", e);
                listener.onError("Error: " + e.getMessage());
            }
        });
    }

    private void execute(String message, StreamListener listener, String... behaviors) throws IOException, InterruptedException {
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
        command.add("mcp__ragger__RaggerSource");
        command.add("mcp__ragger__RaggerList");

        if (devMode) {
            command.add("Edit(/**/*)");
            command.add("Write(/**/*)");
        }

        if (extraTools != null && !extraTools.isBlank()) {
            for (String tool : extraTools.split(",")) {
                String trimmed = tool.strip();
                if (!trimmed.isEmpty()) {
                    command.add(trimmed);
                }
            }
        }

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
        cancelled = false;
        Process process = pb.start();
        currentProcess = process;

        // Track the last text we've seen to detect new content
        StringBuilder lastSeenText = new StringBuilder();
        String finalResult = null;

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) continue;

                try {
                    JsonObject event = new JsonParser().parse(line).getAsJsonObject();

                    if (event.has("session_id")) {
                        sessionId = event.get("session_id").getAsString();
                    }

                    if (event.has("result")) {
                        finalResult = event.get("result").getAsString();
                    }

                    // Stream text content from assistant messages
                    if (event.has("type") && "assistant".equals(event.get("type").getAsString())) {
                        if (event.has("message")) {
                            JsonObject msg = event.getAsJsonObject("message");
                            if (msg.has("content")) {
                                for (JsonElement el : msg.getAsJsonArray("content")) {
                                    JsonObject block = el.getAsJsonObject();
                                    String blockType = block.get("type").getAsString();

                                    if ("text".equals(blockType) && block.has("text")) {
                                        String fullText = block.get("text").getAsString();
                                        // Only emit the new portion
                                        if (fullText.length() > lastSeenText.length()) {
                                            String newPart = fullText.substring(lastSeenText.length());
                                            lastSeenText.setLength(0);
                                            lastSeenText.append(fullText);
                                            listener.onText(newPart);
                                        }
                                    } else if ("tool_use".equals(blockType)) {
                                        String toolName = block.get("name").getAsString();
                                        JsonObject input = block.has("input") ? block.getAsJsonObject("input") : null;
                                        // Reset text tracking — onToolUse handles ending the stream
                                        lastSeenText.setLength(0);
                                        listener.onToolUse(formatToolLog(toolName, input));
                                    }
                                }
                            }
                        }
                    }
                } catch (Exception e) {
                    log.debug("Non-JSON stream line: {}", line);
                }
            }
        }

        currentProcess = null;

        if (cancelled) {
            listener.onCancelled();
            return;
        }

        boolean finished = process.waitFor(120, java.util.concurrent.TimeUnit.SECONDS);
        if (!finished) {
            log.warn("Claude CLI timed out after 120s, killing process");
            process.destroyForcibly();
            listener.onError("Request timed out. Try again or /reset the session.");
        } else if (process.exitValue() != 0) {
            log.warn("Claude CLI exited with code {}", process.exitValue());
        }

        listener.onComplete(finalResult != null ? finalResult : lastSeenText.toString());
    }

    private String formatToolLog(String toolName, JsonObject input) {
        String displayName = toolName.replaceFirst("^mcp__\\w+__", "");

        if (input == null) return displayName + "()";

        if (input.has("command")) {
            return displayName + "(" + truncate(censorPath(input.get("command").getAsString()), 60) + ")";
        }
        if (input.has("pattern")) {
            return displayName + "(" + input.get("pattern").getAsString() + ")";
        }
        if (input.has("file_path")) {
            return displayName + "(" + censorPath(input.get("file_path").getAsString()) + ")";
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

    private static String censorPath(String text) {
        String projectRoot = System.getenv("RAGGER_PROJECT_ROOT");
        if (projectRoot != null) {
            String prefix = projectRoot.endsWith("/") ? projectRoot : projectRoot + "/";
            text = text.replace(prefix, "");
        }
        String home = System.getProperty("user.home");
        if (home != null) {
            text = text.replace(home, "~");
        }
        return text;
    }

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
                sb.append(new String(is.readAllBytes(), StandardCharsets.UTF_8));
            } catch (IOException e) {
                log.error("Failed to load behavior: {}", behavior, e);
            }
        }
        return sb.toString();
    }

    public void resetSession() {
        sessionId = null;
    }
}
