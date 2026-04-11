# Java Style Guide

## Immutability — final by default

Everything that can be `final` should be `final`. Mutability is a deliberate choice.

```java
// WRONG
String name = actor.getName();
int count = list.size();
for (Map.Entry<String, LuaActor> entry : scripts.entrySet()) { ... }

// RIGHT
final String name = actor.getName();
final int count = list.size();
for (final Map.Entry<String, LuaActor> entry : scripts.entrySet()) { ... }
```

Parameters too:

```java
// WRONG
public void start(int port) throws IOException {

// RIGHT
public void start(final int port) throws IOException {
```

Fields that aren't reassigned:

```java
// WRONG
private Client client;
private String token;

// RIGHT
private final Client client;
private final String token;
```

## Braces — always, even for single statements

Never use braceless control flow.

```java
// WRONG
if (!authenticate(exchange)) return;

// WRONG
if (!authenticate(exchange))
    respond(exchange, 401, "{\"error\":\"unauthorized\"}");

// RIGHT
if (!authenticate(exchange)) {
    respond(exchange, 401, "{\"error\":\"unauthorized\"}");
    return;
}
```

## Logical grouping — blank lines as paragraph breaks

Separate code into visual groups by purpose: guards, setup, operations, return.

```java
// WRONG — wall of code
public void start(final int port) throws IOException {
    server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
    server.createContext("/eval", this::handleEval);
    server.createContext("/run", this::handleRun);
    server.setExecutor(null);
    server.start();
    log.info("Bridge server listening on port {}", port);
}

// RIGHT — grouped by purpose
public void start(final int port) throws IOException {
    server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);

    server.createContext("/eval", this::handleEval);
    server.createContext("/run", this::handleRun);

    server.setExecutor(null);
    server.start();
    log.info("Bridge server listening on port {}", port);
}
```

## Indentation — 4 spaces, no tabs

4 spaces for everything: base indent, continuation lines, tab width.

## Line width — ~120 chars, prefer unsplit

Keep lines unsplit when they fit in ~120 characters. When wrapping is needed, put each element on its own line with the closing delimiter at the original indent level:

```java
// WRONG — inconsistent wrapping
public LuaActor(final String name, final String source,
    final Client client, final ChatMessageManager chatMessageManager) {

// WRONG — too aggressive, these fit on one line
public void send(
    final ChatMessageType type,
    final String message
) {

// RIGHT — each param on its own line, closing paren at original indent
public LuaActor(
    final String name,
    final String source,
    final Client client,
    final ChatMessageManager chatMessageManager,
    final ItemManager itemManager,
    final ActorManager actorManager,
    final Map<String, Object> args
) {

// RIGHT — fits on one line, keep it there
public void send(final ChatMessageType type, final String message) {
```

## Switch over chained equals — prefer pattern switch for dispatch

When an if-else chain compares the same value with `.equals()`, use a switch expression/statement instead. Cleaner to read, easier to extend, and the compiler checks for exhaustiveness on sealed types.

```java
// WRONG — repetitive equals chains
if ("bridgePort".equals(key)) {
    restartBridge();
} else if ("consoleModel".equals(key) || "consoleDevMode".equals(key)) {
    rebuildConsole();
} else if ("agentModel".equals(key)) {
    rebuildAgent();
}

// RIGHT — switch with grouped cases
switch (key) {
    case "bridgePort" -> restartBridge();
    case "consoleModel", "consoleDevMode" -> rebuildConsole();
    case "agentModel" -> rebuildAgent();
}
```

## Imports — never inline qualified names

Always use import statements. Never write fully qualified names inline.

```java
// WRONG
final com.google.gson.JsonObject body = com.google.gson.JsonParser.parseString(raw).getAsJsonObject();

// RIGHT
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
// ...
final JsonObject body = JsonParser.parseString(raw).getAsJsonObject();
```

## Named variables — extract for readability

Pull conditions, calculations, and intermediate values into named locals so code reads like prose. Don't inline complex expressions.

```java
// WRONG — dense, hard to scan
if (scripts.entrySet().stream().filter(e -> e.getKey().startsWith(prefix + "/")).count() >= maxChildren) {
    log.warn("Too many children");
    return;
}

// RIGHT — named variable explains what we're checking
final long childCount = scripts.entrySet().stream()
    .filter(e -> e.getKey().startsWith(prefix + "/"))
    .count();

if (childCount >= maxChildren) {
    log.warn("Too many children");
    return;
}
```

```java
// WRONG — what is this boolean?
respond(exchange, 200, result.get(GAME_TICK_TIMEOUT_SECONDS, TimeUnit.SECONDS) != null);

// RIGHT
final String evalResult = result.get(GAME_TICK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
final boolean succeeded = evalResult != null;
respond(exchange, 200, succeeded);
```

## No section headers

Never use comments as section dividers. Let blank lines and logical grouping speak for themselves.

```java
// WRONG
// --- Dependencies ---
private final Client client;

// WRONG
// =====================
// Event handlers
// =====================

// RIGHT — just group with blank lines, no headers
private final Client client;
private final ItemManager itemManager;

private LuaActor activeActor;
```

## Comments — only when non-obvious

Don't narrate what code does. Comment only when the *why* isn't clear from the code itself.

```java
// WRONG — the code already says this
// Set the name
this.name = name;

// WRONG — obvious from the method name
// Send a game message
chat.game("Hello");

// RIGHT — explains a non-obvious constraint
/** Max seconds to wait for a game-tick eval or script load. */
private static final int GAME_TICK_TIMEOUT_SECONDS = 5;

// RIGHT — explains a non-obvious grouping choice
// Dependencies injected at construction, services created lazily
private final Client client;
```
