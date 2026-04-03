package dev.ragger.plugin;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Parsed response from Claude CLI containing chat text, tool usage log,
 * and any scripts submitted via the RaggerRun tool.
 */
public class ClaudeResponse {

    private final String text;
    private final Map<String, String> scripts;
    private final List<String> toolLog;

    public ClaudeResponse(String text, Map<String, String> scripts, List<String> toolLog) {
        this.text = text;
        this.scripts = scripts;
        this.toolLog = toolLog;
    }

    public String getText() {
        return text;
    }

    public Map<String, String> getScripts() {
        return scripts;
    }

    public boolean hasScripts() {
        return scripts != null && !scripts.isEmpty();
    }

    public List<String> getToolLog() {
        return toolLog;
    }
}
