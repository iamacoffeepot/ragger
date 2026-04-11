package dev.ragger.plugin;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import dev.ragger.plugin.scripting.ActorManager;
import dev.ragger.plugin.scripting.MailMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Executors;
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

    public BridgeServer(final ActorManager actorManager) {
        this.actorManager = actorManager;
        this.token = UUID.randomUUID().toString();
    }

    public String getToken() {
        return token;
    }

    public void start(final int port) throws IOException {
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

        server.setExecutor(Executors.newCachedThreadPool());
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
                final String result = actorManager.eval(req.script);
                req.future.complete(result);
            } catch (final Exception e) {
                final String escaped = e.getMessage().replace("\"", "'");
                req.future.complete("{\"error\":\"" + escaped + "\"}");
            }
        }

        PendingRun run;
        while ((run = pendingRuns.poll()) != null) {
            try {
                actorManager.load(run.name, run.script);
                actorManager.defineTemplate(run.name, run.script);
                run.future.complete("{\"status\":\"loaded\",\"name\":\"" + run.name + "\"}");
            } catch (final Exception e) {
                final String escaped = e.getMessage().replace("\"", "'");
                run.future.complete("{\"error\":\"" + escaped + "\"}");
            }
        }

        // Process pending sync mail recv requests
        final long now = System.currentTimeMillis();
        final Iterator<PendingMailRecv> it = pendingMailRecvs.iterator();

        while (it.hasNext()) {
            final PendingMailRecv pending = it.next();

            if (pending.future.isDone()) {
                it.remove();
                continue;
            }

            final boolean expired = now >= pending.deadlineMs;

            if (expired) {
                pending.future.complete(formatMailMessages(pending.collected));
                it.remove();
                continue;
            }

            final List<MailMessage> messages = actorManager.drainClaudeMailbox(
                pending.channel, pending.remaining(), pending.fromFilter);
            pending.collected.addAll(messages);

            if (pending.remaining() <= 0) {
                pending.future.complete(formatMailMessages(pending.collected));
                it.remove();
            }
        }
    }

    private boolean authenticate(final HttpExchange exchange) {
        final String auth = exchange.getRequestHeaders().getFirst("Authorization");
        return auth != null && auth.equals("Bearer " + token);
    }

    private void handleEval(final HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        final String body = new String(
            exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);

        try {
            final JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            final String script = json.get("script").getAsString();

            final CompletableFuture<String> future = new CompletableFuture<>();
            pendingRequests.add(new PendingRequest(script, future));

            final String result = future.get(GAME_TICK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            respond(exchange, 200, result);
        } catch (final Exception e) {
            final String escaped = e.getMessage().replace("\"", "'");
            respond(exchange, 500, "{\"error\":\"" + escaped + "\"}");
        }
    }

    private void handleRun(final HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        final String body = new String(
            exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);

        try {
            final JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            final String name = json.get("name").getAsString();
            final String script = json.get("script").getAsString();

            final CompletableFuture<String> future = new CompletableFuture<>();
            pendingRuns.add(new PendingRun(name, script, future));

            final String result = future.get(GAME_TICK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            respond(exchange, 200, result);
        } catch (final Exception e) {
            final String escaped = e.getMessage().replace("\"", "'");
            respond(exchange, 500, "{\"error\":\"" + escaped + "\"}");
        }
    }

    private void handleList(final HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        final List<String> names = actorManager.list();
        final JsonArray arr = new JsonArray();

        for (final String name : names) {
            arr.add(name);
        }

        final JsonObject result = new JsonObject();
        result.add("actors", arr);
        respond(exchange, 200, result.toString());
    }

    private void handleSource(final HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        final String body = new String(
            exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);

        try {
            final JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            final String name = json.get("name").getAsString();
            final String source = actorManager.getSource(name);

            if (source == null) {
                respond(exchange, 404, "{\"error\":\"script not found\"}");
            } else {
                final JsonObject result = new JsonObject();
                result.addProperty("name", name);
                result.addProperty("source", source);
                respond(exchange, 200, result.toString());
            }
        } catch (final Exception e) {
            final String escaped = e.getMessage().replace("\"", "'");
            respond(exchange, 500, "{\"error\":\"" + escaped + "\"}");
        }
    }

    private void handleTemplates(final HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        final List<String> names = actorManager.listTemplates();
        final JsonArray arr = new JsonArray();

        for (final String name : names) {
            arr.add(name);
        }

        final JsonObject result = new JsonObject();
        result.add("templates", arr);
        respond(exchange, 200, result.toString());
    }

    private void handleTemplateSource(final HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        final String body = new String(
            exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);

        try {
            final JsonObject json = new JsonParser().parse(body).getAsJsonObject();
            final String name = json.get("name").getAsString();
            final String source = actorManager.getTemplate(name);

            if (source == null) {
                respond(exchange, 404, "{\"error\":\"template not found\"}");
            } else {
                final JsonObject result = new JsonObject();
                result.addProperty("name", name);
                result.addProperty("source", source);
                respond(exchange, 200, result.toString());
            }
        } catch (final Exception e) {
            final String escaped = e.getMessage().replace("\"", "'");
            respond(exchange, 500, "{\"error\":\"" + escaped + "\"}");
        }
    }

    private void handleMailRecv(final HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        final Map<String, String> params = parseQueryParams(exchange);
        final String fromFilter = params.getOrDefault("from", null);
        final String limitStr = params.get("limit");

        final int limit;

        if (limitStr != null) {
            int parsed;
            try {
                parsed = Integer.parseInt(limitStr);
            } catch (final NumberFormatException ignored) {
                parsed = 0;
            }
            limit = parsed;
        } else {
            limit = 0;
        }

        final String channel = params.getOrDefault("channel", "console");
        final List<MailMessage> messages = actorManager.drainClaudeMailbox(channel, limit, fromFilter);
        respond(exchange, 200, formatMailMessages(messages));
    }

    private void handleMailRecvBlock(final HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"GET required\"}");
            return;
        }

        final Map<String, String> params = parseQueryParams(exchange);
        final String fromFilter = params.getOrDefault("from", null);
        final String countStr = params.get("count");
        final String timeoutStr = params.get("timeout");

        final int count;

        if (countStr != null) {
            int parsed;
            try {
                parsed = Math.max(1, Integer.parseInt(countStr));
            } catch (final NumberFormatException ignored) {
                parsed = 1;
            }
            count = parsed;
        } else {
            count = 1;
        }

        final int timeoutSec;

        if (timeoutStr != null) {
            int parsed;
            try {
                parsed = Math.max(1, Math.min(MAIL_RECV_MAX_TIMEOUT, Integer.parseInt(timeoutStr)));
            } catch (final NumberFormatException ignored) {
                parsed = MAIL_RECV_DEFAULT_TIMEOUT;
            }
            timeoutSec = parsed;
        } else {
            timeoutSec = MAIL_RECV_DEFAULT_TIMEOUT;
        }

        final String channel = params.getOrDefault("channel", "console");
        final CompletableFuture<String> future = new CompletableFuture<>();
        final long deadlineMs = System.currentTimeMillis() + (timeoutSec * 1000L);
        pendingMailRecvs.add(new PendingMailRecv(channel, count, fromFilter, deadlineMs, future));

        try {
            final long futureTimeout = timeoutSec + MAIL_RECV_BUFFER_SECONDS;
            final String result = future.get(futureTimeout, TimeUnit.SECONDS);
            respond(exchange, 200, result);
        } catch (final Exception e) {
            respond(exchange, 504, "{\"error\":\"timeout\"}");
        }
    }

    private Map<String, String> parseQueryParams(final HttpExchange exchange) {
        final Map<String, String> params = new HashMap<>();
        final String query = exchange.getRequestURI().getQuery();

        if (query != null) {
            for (final String pair : query.split("&")) {
                final int eq = pair.indexOf('=');

                if (eq > 0) {
                    params.put(pair.substring(0, eq), pair.substring(eq + 1));
                }
            }
        }

        return params;
    }

    private String formatMailMessages(final List<MailMessage> messages) {
        final JsonArray arr = new JsonArray();

        for (final MailMessage msg : messages) {
            final JsonObject entry = new JsonObject();
            entry.addProperty("from", msg.from());
            entry.add("data", toJsonElement(msg.data()));
            arr.add(entry);
        }

        final JsonObject result = new JsonObject();
        result.add("messages", arr);
        return result.toString();
    }

    @SuppressWarnings("unchecked")
    private static JsonElement toJsonElement(final Object value) {
        if (value instanceof Map) {
            final JsonObject obj = new JsonObject();

            for (final Map.Entry<String, Object> kv : ((Map<String, Object>) value).entrySet()) {
                obj.add(kv.getKey(), toJsonElement(kv.getValue()));
            }

            return obj;
        } else if (value instanceof List) {
            final JsonArray arr = new JsonArray();

            for (final Object item : (List<Object>) value) {
                arr.add(toJsonElement(item));
            }

            return arr;
        } else if (value instanceof Boolean) {
            return new JsonPrimitive((Boolean) value);
        } else if (value instanceof Number) {
            return new JsonPrimitive((Number) value);
        } else if (value instanceof String) {
            return new JsonPrimitive((String) value);
        } else {
            return new JsonPrimitive(String.valueOf(value));
        }
    }

    private static Object fromJsonElement(final JsonElement element) {
        if (element.isJsonObject()) {
            final Map<String, Object> map = new HashMap<>();

            for (final Map.Entry<String, JsonElement> kv : element.getAsJsonObject().entrySet()) {
                map.put(kv.getKey(), fromJsonElement(kv.getValue()));
            }

            return map;
        } else if (element.isJsonArray()) {
            final List<Object> list = new ArrayList<>();

            for (final JsonElement item : element.getAsJsonArray()) {
                list.add(fromJsonElement(item));
            }

            return list;
        } else if (element.isJsonPrimitive()) {
            final JsonPrimitive prim = element.getAsJsonPrimitive();

            if (prim.isBoolean()) {
                return prim.getAsBoolean();
            }

            if (prim.isNumber()) {
                final double num = prim.getAsDouble();
                final boolean isWholeInt = num == Math.floor(num)
                    && !Double.isInfinite(num)
                    && num >= Integer.MIN_VALUE
                    && num <= Integer.MAX_VALUE;

                if (isWholeInt) {
                    return (int) num;
                }

                return num;
            }

            return prim.getAsString();
        }

        return null;
    }

    private void handleMail(final HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{\"error\":\"POST required\"}");
            return;
        }

        final String body = new String(
            exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);

        try {
            final Map<String, String> params = parseQueryParams(exchange);
            final String channel = params.getOrDefault("channel", "console");
            final String sender = "claude:" + channel;
            final JsonElement parsed = new JsonParser().parse(body);

            // Batch mode: array of {target, data} messages
            if (parsed.isJsonArray()) {
                final JsonArray array = parsed.getAsJsonArray();
                int queued = 0;

                for (final JsonElement element : array) {
                    final JsonObject msg = element.getAsJsonObject();
                    final String target = msg.get("target").getAsString();
                    final JsonObject data = msg.getAsJsonObject("data");

                    if (data == null) {
                        continue;
                    }

                    @SuppressWarnings("unchecked")
                    final Map<String, Object> map =
                        (Map<String, Object>) fromJsonElement(data);
                    actorManager.enqueueMail(sender, target, map);
                    queued++;
                }

                respond(exchange, 200,
                    "{\"status\":\"queued\",\"count\":" + queued + "}");
                return;
            }

            // Single message mode
            final JsonObject json = parsed.getAsJsonObject();
            final String target = json.get("target").getAsString();
            final JsonObject data = json.getAsJsonObject("data");

            if (data == null) {
                respond(exchange, 400, "{\"error\":\"missing data field\"}");
                return;
            }

            @SuppressWarnings("unchecked")
            final Map<String, Object> map = (Map<String, Object>) fromJsonElement(data);

            actorManager.enqueueMail(sender, target, map);
            respond(exchange, 200,
                "{\"status\":\"queued\",\"target\":\"" + target + "\"}");
        } catch (final Exception e) {
            final String escaped = e.getMessage().replace("\"", "'");
            respond(exchange, 500, "{\"error\":\"" + escaped + "\"}");
        }
    }

    private void respond(
        final HttpExchange exchange,
        final int code,
        final String body
    ) throws IOException {
        final byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(code, bytes.length);

        try (final OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private record PendingRequest(String script, CompletableFuture<String> future) {}

    private record PendingRun(String name, String script, CompletableFuture<String> future) {}

    private static class PendingMailRecv {

        final String channel;
        final int count;
        final String fromFilter;
        final long deadlineMs;
        final CompletableFuture<String> future;
        final List<MailMessage> collected = new ArrayList<>();

        PendingMailRecv(
            final String channel,
            final int count,
            final String fromFilter,
            final long deadlineMs,
            final CompletableFuture<String> future
        ) {
            this.channel = channel;
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
