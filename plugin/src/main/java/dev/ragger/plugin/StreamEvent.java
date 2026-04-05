package dev.ragger.plugin;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.annotations.SerializedName;

import java.util.List;

/**
 * A single event from Claude CLI's stream-json output format.
 */
public class StreamEvent {

    private static final Gson GSON = new Gson();

    private String type;

    @SerializedName("session_id")
    private String sessionId;

    private String result;
    private Message message;

    public String getType() {
        return type;
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getResult() {
        return result;
    }

    public Message getMessage() {
        return message;
    }

    public boolean isAssistant() {
        return "assistant".equals(type);
    }

    public static StreamEvent parse(String json) {
        return GSON.fromJson(json, StreamEvent.class);
    }

    public static class Message {
        private List<ContentBlock> content;

        public List<ContentBlock> getContent() {
            return content;
        }
    }

    public static class ContentBlock {
        private String type;
        private String text;
        private String name;
        private JsonObject input;

        public String getType() {
            return type;
        }

        public boolean isText() {
            return "text".equals(type);
        }

        public boolean isToolUse() {
            return "tool_use".equals(type);
        }

        public String getText() {
            return text;
        }

        public String getName() {
            return name;
        }

        public JsonObject getInput() {
            return input;
        }
    }
}
