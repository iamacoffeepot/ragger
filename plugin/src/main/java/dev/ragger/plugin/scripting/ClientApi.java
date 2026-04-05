package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.api.GameState;

/**
 * Lua binding for client and game state information.
 * Exposed as the global "client" table in Lua scripts.
 */
public class ClientApi {

    // GameState constants
    public final GameState UNKNOWN = GameState.UNKNOWN;
    public final GameState STARTING = GameState.STARTING;
    public final GameState LOGIN_SCREEN = GameState.LOGIN_SCREEN;
    public final GameState LOGIN_SCREEN_AUTHENTICATOR = GameState.LOGIN_SCREEN_AUTHENTICATOR;
    public final GameState LOGGING_IN = GameState.LOGGING_IN;
    public final GameState LOADING = GameState.LOADING;
    public final GameState LOGGED_IN = GameState.LOGGED_IN;
    public final GameState CONNECTION_LOST = GameState.CONNECTION_LOST;
    public final GameState HOPPING = GameState.HOPPING;

    private final Client client;

    public ClientApi(final Client client) {
        this.client = client;
    }

    // World info
    public int world() { return client.getWorld(); }
    public int plane() { return client.getPlane(); }
    public int tick_count() { return client.getTickCount(); }
    public int fps() { return client.getFPS(); }

    // Player state
    public int energy() { return client.getEnergy(); }
    public int weight() { return client.getWeight(); }

    // Game state
    public GameState state() { return client.getGameState(); }
    public boolean logged_in() { return client.getGameState() == GameState.LOGGED_IN; }

    // Canvas/viewport dimensions
    public int canvas_width() { return client.getCanvasWidth(); }
    public int canvas_height() { return client.getCanvasHeight(); }
    public int viewport_width() { return client.getViewportWidth(); }
    public int viewport_height() { return client.getViewportHeight(); }
    public int viewport_x() { return client.getViewportXOffset(); }
    public int viewport_y() { return client.getViewportYOffset(); }

    // Idle tracking
    public int mouse_idle_ticks() { return client.getMouseIdleTicks(); }
    public int keyboard_idle_ticks() { return client.getKeyboardIdleTicks(); }
}
