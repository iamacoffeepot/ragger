package dev.ragger.plugin;

import com.google.gson.JsonObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

/**
 * Manages communication with the Claude CLI with persistent sessions.
 * Streams text as it arrives via a callback.
 */
public class ClaudeClient {

    private static final Logger log = LoggerFactory.getLogger(ClaudeClient.class);

    /** Max seconds to wait for the CLI process to exit after stream ends. */
    private static final int CLI_TIMEOUT_SECONDS = 120;

    /** Max characters shown for a tool argument in the tool log. */
    private static final int TOOL_LOG_TRUNCATE_LENGTH = 60;

    private final String claudePath;
    private final String model;
    private final int bridgePort;
    private final String bridgeToken;
    private final boolean devMode;
    private final String extraTools;
    private String sessionId;
    private volatile Process currentProcess;
    private volatile boolean cancelled;

    public ClaudeClient(
        final String claudePath,
        final String model,
        final int bridgePort,
        final String bridgeToken,
        final boolean devMode,
        final String extraTools
    ) {
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

        final Process p = currentProcess;
        if (p != null) {
            // Kill entire process tree (Claude CLI + MCP server subprocess)
            p.descendants().forEach(ProcessHandle::destroyForcibly);
            p.destroyForcibly();
            log.info("Claude CLI process tree cancelled");
        }
    }

    public boolean isBusy() {
        return currentProcess != null;
    }

    /**
     * Send a message to Claude, streaming responses via the listener.
     */
    public void send(final String message, final StreamListener listener, final String... behaviors) {
        CompletableFuture.runAsync(() -> {
            try {
                execute(message, listener, behaviors);
            } catch (Exception e) {
                log.error("Claude CLI error", e);
                listener.onError("Error: " + e.getMessage());
            }
        });
    }

    private void execute(
        final String message,
        final StreamListener listener,
        final String... behaviors
    ) throws IOException, InterruptedException {
        final List<String> command = new ArrayList<>();
        command.add(claudePath);
        command.add("-p");
        command.add(message);
        command.add("--output-format");
        command.add("stream-json");
        command.add("--include-partial-messages");
        command.add("--verbose");
        command.add("--model");
        command.add(model);
        command.add("--allowedTools");
        command.add("Bash");
        command.add("Read");
        command.add("Glob");
        command.add("Grep");
        command.add("mcp__ragger__RaggerActorSpawn");
        command.add("mcp__ragger__RaggerEval");
        command.add("mcp__ragger__RaggerActorList");
        command.add("mcp__ragger__RaggerActorSource");
        command.add("mcp__ragger__RaggerTemplateList");
        command.add("mcp__ragger__RaggerTemplateSource");
        command.add("mcp__ragger__RaggerMailSend");
        command.add("mcp__ragger__RaggerMailRecvAsync");
        command.add("mcp__ragger__RaggerMailRecvSync");

        if (devMode) {
            command.add("Edit(/**/*)");
            command.add("Write(/**/*)");
        }

        if (extraTools != null && !extraTools.isBlank()) {
            for (final String tool : extraTools.split(",")) {
                final String trimmed = tool.strip();
                if (!trimmed.isEmpty()) {
                    command.add(trimmed);
                }
            }
        }

        command.add("--mcp-config");
        command.add("{\"mcpServers\":{\"ragger\":{\"type\":\"stdio\",\"command\":\"uv\",\"args\":[\"run\",\"python\",\"src/ragger/mcp_server.py\"]}}}");

        final String systemPrompt = loadBehaviors(behaviors);
        if (!systemPrompt.isEmpty()) {
            command.add("--append-system-prompt");
            command.add(systemPrompt);
        }

        if (sessionId != null) {
            command.add("--resume");
            command.add(sessionId);
        }

        final ProcessBuilder pb = new ProcessBuilder(command);
        final String projectRoot = System.getenv("RAGGER_PROJECT_ROOT");
        if (projectRoot != null) {
            pb.directory(new File(projectRoot));
        }
        pb.environment().put("RAGGER_BRIDGE_PORT", String.valueOf(bridgePort));
        pb.environment().put("RAGGER_BRIDGE_TOKEN", bridgeToken);
        pb.redirectErrorStream(true);
        pb.redirectInput(ProcessBuilder.Redirect.from(new File("/dev/null")));
        cancelled = false;

        final Process process = pb.start();
        currentProcess = process;

        // Track the last text we've seen to detect new content
        final StringBuilder lastSeenText = new StringBuilder();
        String finalResult = null;

        try (
            BufferedReader reader = new BufferedReader(new InputStreamReader(
                process.getInputStream(),
                StandardCharsets.UTF_8
            ))
        ) {
            String line;
            while (!cancelled && (line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                try {
                    final StreamEvent event = StreamEvent.parse(line);

                    if (event.getSessionId() != null) {
                        sessionId = event.getSessionId();
                    }

                    if (event.getResult() != null) {
                        finalResult = event.getResult();
                    }

                    if (event.isStreamEvent()) {
                        processStreamEvent(event.getEvent(), lastSeenText, listener);
                        continue;
                    }

                    if (!event.isAssistant()) {
                        continue;
                    }

                    if (event.getMessage() == null) {
                        continue;
                    }

                    if (event.getMessage().getContent() == null) {
                        continue;
                    }

                    for (final StreamEvent.ContentBlock block : event.getMessage().getContent()) {
                        processContentBlock(block, lastSeenText, listener);
                    }
                } catch (final Exception e) {
                    log.debug("Non-JSON stream line: {}", line);
                }
            }
        }

        currentProcess = null;

        if (cancelled) {
            listener.onCancelled();
            return;
        }

        final boolean finished = process.waitFor(CLI_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        if (!finished) {
            log.warn("Claude CLI timed out after {}s, killing process", CLI_TIMEOUT_SECONDS);
            process.destroyForcibly();
            listener.onError("Request timed out. Try again or /reset the session.");
        } else if (process.exitValue() != 0) {
            log.warn("Claude CLI exited with code {}", process.exitValue());
        }

        listener.onComplete(finalResult != null ? finalResult : lastSeenText.toString());
    }

    private void processStreamEvent(
        final StreamEvent.Event event,
        final StringBuilder lastSeenText,
        final StreamListener listener
    ) {
        if (event == null) {
            return;
        }

        if (event.isContentBlockDelta()) {
            final StreamEvent.Delta delta = event.getDelta();
            if (delta != null && delta.isTextDelta() && delta.getText() != null) {
                lastSeenText.append(delta.getText());
                listener.onText(delta.getText());
            }
        }
    }

    private void processContentBlock(
        final StreamEvent.ContentBlock block,
        final StringBuilder lastSeenText,
        final StreamListener listener
    ) {
        if (block.isText() && block.getText() != null) {
            final String fullText = block.getText();
            if (fullText.length() <= lastSeenText.length()) {
                return;
            }

            final String newPart = fullText.substring(lastSeenText.length());
            lastSeenText.setLength(0);
            lastSeenText.append(fullText);
            listener.onText(newPart);
        } else if (block.isToolUse()) {
            // Reset text tracking — onToolUse handles ending the stream
            lastSeenText.setLength(0);
            listener.onToolUse(formatToolLog(block.getName(), block.getInput()));
        }
    }

    private String formatToolLog(final String toolName, final JsonObject input) {
        final String displayName = toolName.replaceFirst("^mcp__\\w+__", "");

        if (input == null) {
            return displayName + "()";
        }

        if (input.has("command")) {
            return displayName + "(" + truncate(censorPath(input.get("command").getAsString()), TOOL_LOG_TRUNCATE_LENGTH) + ")";
        }

        if (input.has("pattern")) {
            return displayName + "(" + input.get("pattern").getAsString() + ")";
        }

        if (input.has("file_path")) {
            return displayName + "(" + censorPath(input.get("file_path").getAsString()) + ")";
        }

        if (input.has("script")) {
            final String name = input.has("name") ? input.get("name").getAsString() : "";
            return displayName + "(" + name + ", ...)";
        }

        return displayName + "()";
    }

    private static String truncate(final String s, final int maxLen) {
        if (s.length() <= maxLen) {
            return s;
        }

        return s.substring(0, maxLen) + "...";
    }

    private static String censorPath(String text) {
        final String projectRoot = System.getenv("RAGGER_PROJECT_ROOT");
        if (projectRoot != null) {
            final String prefix = projectRoot.endsWith("/") ? projectRoot : projectRoot + "/";
            text = text.replace(prefix, "");
        }

        final String home = System.getProperty("user.home");
        if (home != null) {
            text = text.replace(home, "~");
        }

        return text;
    }

    private String loadBehaviors(final String... behaviors) {
        final StringBuilder sb = new StringBuilder();

        for (final String behavior : behaviors) {
            final String resource = behavior + ".md";

            try (final InputStream is = getClass().getResourceAsStream(resource)) {
                if (is == null) {
                    log.warn("Behavior resource not found: {}", resource);
                    continue;
                }

                if (!sb.isEmpty()) {
                    sb.append("\n\n");
                }

                sb.append(new String(is.readAllBytes(), StandardCharsets.UTF_8));
            } catch (final IOException e) {
                log.error("Failed to load behavior: {}", behavior, e);
            }
        }

        return sb.toString();
    }

    public void resetSession() {
        sessionId = null;
    }
}
