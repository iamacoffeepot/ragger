package dev.ragger.plugin;

import java.util.List;

/**
 * Parsed response from Claude CLI containing chat text and tool usage log.
 */
public class ClaudeResponse {

    private final String text;
    private final List<String> toolLog;

    public ClaudeResponse(final String text, final List<String> toolLog) {
        this.text = text;
        this.toolLog = toolLog;
    }

    public String getText() {
        return text;
    }

    public List<String> getToolLog() {
        return toolLog;
    }
}
