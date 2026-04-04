package dev.ragger.plugin;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import dev.ragger.plugin.scripting.ActorManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.TimeUnit;

/**
 * Lightweight HTTP server bridging MCP tools to the RuneLite client thread.
 * Requests are queued and fulfilled on the game tick thread.
 */
public class BridgeServer {

    private static final Logger log = LoggerFactory.getLogger(BridgeServer.class);

    /** Max seconds to wait for a game-tick eval or script load. */
    private static final int GAME_TICK_TIMEOUT_SECONDS = 5;

    /** Default timeout for blocking mail recv. */
    private static final int MAIL_RECV_DEFAULT_TIMEOUT = 30;

    /** Max allowed timeout for blocking mail recv. */
    private static final int MAIL_RECV_MAX_TIMEOUT = 300;

    /** Extra seconds added to the future timeout beyond the mail deadline. */
    private static final int MAIL_RECV_BUFFER_SECONDS = 5;

    private final ActorManager actorManager;
    private final String token;
    private final ConcurrentLinkedQueue<PendingRequest> pendingRequests = new ConcurrentLinkedQueue<>();
    private final ConcurrentLinkedQueue<PendingRun> pendingRuns = new ConcurrentLinkedQueue<>();
    private final ConcurrentLinkedQueue<PendingMailRecv> pendingMailRecvs = new ConcurrentLinkedQueue<>();
    private HttpServer server;

    public BridgeServer(ActorManager actorManager) {
        this.actorManager = actorManager;
        this.token = java.util.UUID.randomUUID().toString();
    }

    public String getToken() {
        return token;
    }

    public void start(int port) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);

        server.createContext("/eval", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleEval(exchange);
        });
        server.createContext("/run", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleRun(exchange);
        });
        server.createContext("/list", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleList(exchange);
        });
        server.createContext("/source", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleSource(exchange);
        });
        server.createContext("/templates", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleTemplates(exchange);
        });
        server.createContext("/template-source", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleTemplateSource(exchange);
        });
        server.createContext("/mail-recv-block", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleMailRecvBlock(exchange);
        });
        server.createContext("/mail-recv", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleMailRecv(exchange);
        });
        server.createContext("/mail", exchange -> {
            if (!authenticate(exchange)) {
                respond(exchange, 401, "{\"error\":\"unauthorized\"}");
                return;
            }
            handleMail(exchange);
        });
        server.createContext("/health", exchange -> {
            respond(exchange, 200, "{\"status\":\"ok\"}");
        });

        server.setExecutor(null);
        server.start();
        log.info("Bridge server started on port {}", port);
    }

    public void stop() {
        if (server != null) {
            server.stop(0);
            log.info("Bridge server stopped");
        }
    }

    /**
     * Called on the game tick thread. Processes all pending requests.
     */
    public void tick() {
        PendingRequest req;
        while ((req = pendingRequests.poll()) != null) {
            try {
                String result = actorManager.eval(req.script);
                req.future.complete(result);
            } catch (Exception e) {
                req.future.complete("{\"error\":\"" + e.getMessage().replace("\"", "'") + "\"}");
            }
        }

        PendingRun run;
        while ((run = pendingRuns.poll()) != null) {
            try {
                actorManager.load(run.name, run.script);
                actorManager.defineTemplate(run.name, run.script);
                run.future.complete("{\"status\":\"loaded\",\"name\":\"" + run.name + "\"}");
            } catch (Exception e) {
                run.future.complete("{\"error\":\"" + e.getMessage().replace("\"", "'") + "\"}");
            }
        }

        // Process pending sync mail recv requests
        long now = System.currentTimeMillis();
        Iterator<PendingMailRecv> it = pendingMailRecvs.iterator();
        while (it.hasNext()) {
            PendingMailRecv pending = it.next();
            if (pending.future.isDone()) {
                it.remove();
                continue;
            }

            // Check for timeout
            if (now >= pending.deadlineMs) {
                // Return whatever we collected so far
                pending.future.complete(formatMailMessages(pending.collected));
                it.remove();
                continue;
            }

            // Try to collect more messages
            var messages = actorManager.drainClaudeMailbox(
                pending.remaining(), pending.fromFilter);
            pending.collected.addAll(messages);

            if (pending.remaining() <= 0) {
                pending.future.complete(formatMailMessages(pending.collected));
                it.remove();
            }
        }
    }

    private boolean authenticate(HttpExchange exchange) {
        String auth = exchange.getRequestHeaders().getFirst("Authorization");
        return auth != null && auth.equals("Bearer " + token);
    }

    private void handleEval(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        try {
            JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            String script = json.get("script").getAsString();

            CompletableFuture<String> future = new CompletableFuture<>();
            pendingRequests.add(new PendingRequest(script, future));

            String result = future.get(GAME_TICK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            respond(exchange, 200, result);
        } catch (Exception e) {
            respond(exchange, 500, "{\"error\":\"" + e.getMessage().replace("\"", "'") + "\"}");
        }
    }

    private void handleRun(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        try {
            JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            String name = json.get("name").getAsString();
            String script = json.get("script").getAsString();

            CompletableFuture<String> future = new CompletableFuture<>();
            pendingRuns.add(new PendingRun(name, script, future));

            String result = future.get(GAME_TICK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            respond(exchange, 200, result);
        } catch (Exception e) {
            respond(exchange, 500, "{\"error\":\"" + e.getMessage().replace("\"", "'") + "\"}");
        }
    }

    private void handleList(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        var names = actorManager.list();
        var arr = new com.google.gson.JsonArray();
        for (String name : names) {
            arr.add(name);
        }
        JsonObject result = new JsonObject();
        result.add("actors", arr);
        respond(exchange, 200, result.toString());
    }

    private void handleSource(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        try {
            JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            String name = json.get("name").getAsString();
            String source = actorManager.getSource(name);
            if (source == null) {
                respond(exchange, 404, "{\"error\":\"script not found\"}");
            } else {
                JsonObject result = new JsonObject();
                result.addProperty("name", name);
                result.addProperty("source", source);
                respond(exchange, 200, result.toString());
            }
        } catch (Exception e) {
            respond(exchange, 500, "{\"error\":\"" + e.getMessage().replace("\"", "'") + "\"}");
        }
    }

    private void handleTemplates(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        var names = actorManager.listTemplates();
        var arr = new com.google.gson.JsonArray();
        for (String name : names) {
            arr.add(name);
        }
        JsonObject result = new JsonObject();
        result.add("templates", arr);
        respond(exchange, 200, result.toString());
    }

    private void handleTemplateSource(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        try {
            JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            String name = json.get("name").getAsString();
            String source = actorManager.getTemplate(name);
            if (source == null) {
                respond(exchange, 404, "{\"error\":\"template not found\"}");
            } else {
                JsonObject result = new JsonObject();
                result.addProperty("name", name);
                result.addProperty("source", source);
                respond(exchange, 200, result.toString());
            }
        } catch (Exception e) {
            respond(exchange, 500, "{\"error\":\"" + e.getMessage().replace("\"", "'") + "\"}");
        }
    }

    private void handleMailRecv(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        // Parse optional query params: ?limit=N&from=script-name
        var params = parseQueryParams(exchange);
        String fromFilter = params.getOrDefault("from", null);
        int limit = 0; // 0 = all
        String limitStr = params.get("limit");
        if (limitStr != null) {
            try { limit = Integer.parseInt(limitStr); } catch (NumberFormatException ignored) {}
        }

        var messages = actorManager.drainClaudeMailbox(limit, fromFilter);
        respond(exchange, 200, formatMailMessages(messages));
    }

    private void handleMailRecvBlock(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        var params = parseQueryParams(exchange);
        String fromFilter = params.getOrDefault("from", null);
        int count = 1;
        String countStr = params.get("count");
        if (countStr != null) {
            try { count = Math.max(1, Integer.parseInt(countStr)); } catch (NumberFormatException ignored) {}
        }
        int timeoutSec = MAIL_RECV_DEFAULT_TIMEOUT;
        String timeoutStr = params.get("timeout");
        if (timeoutStr != null) {
            try { timeoutSec = Math.max(1, Math.min(MAIL_RECV_MAX_TIMEOUT, Integer.parseInt(timeoutStr))); } catch (NumberFormatException ignored) {}
        }

        CompletableFuture<String> future = new CompletableFuture<>();
        long deadlineMs = System.currentTimeMillis() + (timeoutSec * 1000L);
        pendingMailRecvs.add(new PendingMailRecv(count, fromFilter, deadlineMs, future));

        try {
            String result = future.get(timeoutSec + MAIL_RECV_BUFFER_SECONDS, TimeUnit.SECONDS);
            respond(exchange, 200, result);
        } catch (Exception e) {
            respond(exchange, 504, "{\"error\":\"timeout\"}");
        }
    }

    private java.util.Map<String, String> parseQueryParams(HttpExchange exchange) {
        java.util.Map<String, String> params = new java.util.HashMap<>();
        String query = exchange.getRequestURI().getQuery();
        if (query != null) {
            for (String pair : query.split("&")) {
                int eq = pair.indexOf('=');
                if (eq > 0) {
                    params.put(pair.substring(0, eq), pair.substring(eq + 1));
                }
            }
        }
        return params;
    }

    private String formatMailMessages(List<dev.ragger.plugin.scripting.MailMessage> messages) {
        var arr = new com.google.gson.JsonArray();
        for (var msg : messages) {
            JsonObject entry = new JsonObject();
            entry.addProperty("from", msg.from());
            entry.add("data", toJsonElement(msg.data()));
            arr.add(entry);
        }
        JsonObject result = new JsonObject();
        result.add("messages", arr);
        return result.toString();
    }

    @SuppressWarnings("unchecked")
    private static com.google.gson.JsonElement toJsonElement(Object value) {
        if (value instanceof java.util.Map) {
            JsonObject obj = new JsonObject();
            for (var kv : ((java.util.Map<String, Object>) value).entrySet()) {
                obj.add(kv.getKey(), toJsonElement(kv.getValue()));
            }
            return obj;
        } else if (value instanceof java.util.List) {
            var arr = new com.google.gson.JsonArray();
            for (Object item : (java.util.List<Object>) value) {
                arr.add(toJsonElement(item));
            }
            return arr;
        } else if (value instanceof Boolean) {
            return new com.google.gson.JsonPrimitive((Boolean) value);
        } else if (value instanceof Number) {
            return new com.google.gson.JsonPrimitive((Number) value);
        } else if (value instanceof String) {
            return new com.google.gson.JsonPrimitive((String) value);
        } else {
            return new com.google.gson.JsonPrimitive(String.valueOf(value));
        }
    }

    private static Object fromJsonElement(com.google.gson.JsonElement element) {
        if (element.isJsonObject()) {
            java.util.Map<String, Object> map = new java.util.HashMap<>();
            for (var kv : element.getAsJsonObject().entrySet()) {
                map.put(kv.getKey(), fromJsonElement(kv.getValue()));
            }
            return map;
        } else if (element.isJsonArray()) {
            java.util.List<Object> list = new ArrayList<>();
            for (var item : element.getAsJsonArray()) {
                list.add(fromJsonElement(item));
            }
            return list;
        } else if (element.isJsonPrimitive()) {
            var prim = element.getAsJsonPrimitive();
            if (prim.isBoolean()) return prim.getAsBoolean();
            if (prim.isNumber()) {
                double num = prim.getAsDouble();
                if (num == Math.floor(num) && !Double.isInfinite(num)
                        && num >= Integer.MIN_VALUE && num <= Integer.MAX_VALUE) {
                    return (int) num;
                }
                return num;
            }
            return prim.getAsString();
        }
        return null;
    }

    private void handleMail(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        try {
            JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            String target = json.get("target").getAsString();
            JsonObject data = json.getAsJsonObject("data");
            if (data == null) {
                respond(exchange, 400, "{\"error\":\"missing data field\"}");
                return;
            }

            @SuppressWarnings("unchecked")
            java.util.Map<String, Object> map = (java.util.Map<String, Object>) fromJsonElement(data);

            actorManager.enqueueMail("claude", target, map);
            respond(exchange, 200, "{\"status\":\"queued\",\"target\":\"" + target + "\"}");
        } catch (Exception e) {
            respond(exchange, 500, "{\"error\":\"" + e.getMessage().replace("\"", "'") + "\"}");
        }
    }

    private void respond(HttpExchange exchange, int code, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private record PendingRequest(String script, CompletableFuture<String> future) {}
    private record PendingRun(String name, String script, CompletableFuture<String> future) {}

    private static class PendingMailRecv {
        final int count;
        final String fromFilter;
        final long deadlineMs;
        final CompletableFuture<String> future;
        final List<dev.ragger.plugin.scripting.MailMessage> collected = new ArrayList<>();

        PendingMailRecv(int count, String fromFilter, long deadlineMs, CompletableFuture<String> future) {
            this.count = count;
            this.fromFilter = fromFilter;
            this.deadlineMs = deadlineMs;
            this.future = future;
        }

        int remaining() {
            return count - collected.size();
        }
    }
}
