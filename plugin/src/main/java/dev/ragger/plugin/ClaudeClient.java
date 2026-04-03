package dev.ragger.plugin;

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
 */
public class ClaudeClient {

    private static final Logger log = LoggerFactory.getLogger(ClaudeClient.class);

    private final String claudePath;
    private final String model;
    private String sessionId;

    public ClaudeClient(String claudePath, String model) {
        this.claudePath = claudePath;
        this.model = model;
    }

    /**
     * Send a message to Claude asynchronously with the given behavior profiles.
     */
    public CompletableFuture<String> send(String message, String... behaviors) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return execute(message, behaviors);
            } catch (Exception e) {
                log.error("Claude CLI error", e);
                return "Error: " + e.getMessage();
            }
        });
    }

    private String execute(String message, String... behaviors) throws IOException, InterruptedException {
        List<String> command = new ArrayList<>();
        command.add(claudePath);
        command.add("-p");
        command.add(message);
        command.add("--output-format");
        command.add("json");
        command.add("--model");
        command.add(model);
        command.add("--allowedTools");
        command.add("Bash");
        command.add("Read");
        command.add("Glob");
        command.add("Grep");

        // Only set system prompt on the first message (new session)
        if (sessionId == null) {
            String systemPrompt = loadBehaviors(behaviors);
            if (!systemPrompt.isEmpty()) {
                command.add("--append-system-prompt");
                command.add(systemPrompt);
            }
        } else {
            command.add("--resume");
            command.add(sessionId);
        }

        ProcessBuilder pb = new ProcessBuilder(command);
        String projectRoot = System.getenv("RAGGER_PROJECT_ROOT");
        if (projectRoot != null) {
            pb.directory(new java.io.File(projectRoot));
        }
        pb.redirectErrorStream(true);
        pb.redirectInput(ProcessBuilder.Redirect.from(new java.io.File("/dev/null")));
        Process process = pb.start();

        StringBuilder output = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (!output.isEmpty()) {
                    output.append("\n");
                }
                output.append(line);
            }
        }

        int exitCode = process.waitFor();
        if (exitCode != 0) {
            log.warn("Claude CLI exited with code {}", exitCode);
        }

        return parseResponse(output.toString());
    }

    private String parseResponse(String rawOutput) {
        try {
            JsonObject json = new JsonParser().parse(rawOutput).getAsJsonObject();

            // Capture session ID for subsequent messages
            if (json.has("session_id")) {
                sessionId = json.get("session_id").getAsString();
                log.info("Session ID: {}", sessionId);
            }

            if (json.has("result")) {
                return json.get("result").getAsString();
            }

            return rawOutput;
        } catch (Exception e) {
            // If it's not valid JSON, return raw output (error messages, etc.)
            log.warn("Failed to parse Claude response as JSON", e);
            return rawOutput;
        }
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
                sb.append(new String(is.readAllBytes(), StandardCharsets.UTF_8));
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
