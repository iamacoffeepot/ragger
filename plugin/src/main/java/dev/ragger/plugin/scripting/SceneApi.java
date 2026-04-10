package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.api.DecorativeObject;
import net.runelite.api.GameObject;
import net.runelite.api.GroundObject;
import net.runelite.api.ItemComposition;
import net.runelite.api.NPC;
import net.runelite.api.ObjectComposition;
import net.runelite.api.Player;
import net.runelite.api.Scene;
import net.runelite.api.Tile;
import net.runelite.api.TileItem;
import net.runelite.api.TileObject;
import net.runelite.api.WallObject;
import net.runelite.api.coords.WorldPoint;
import net.runelite.client.game.ItemManager;
import party.iroiro.luajava.Lua;

import java.util.ArrayList;
import java.util.List;

/**
 * Builds the "scene" Lua table with JFunction entries.
 * Each function returns Lua tables with primitive fields.
 */
public class SceneApi {

    private final Client client;
    private final ItemManager itemManager;

    public SceneApi(final Client client, final ItemManager itemManager) {
        this.client = client;
        this.itemManager = itemManager;
    }

    /**
     * Register the scene table and all its functions on the Lua state.
     */
    public void register(final Lua lua) {
        lua.createTable(0, 4);

        lua.push(this::npcs);
        lua.setField(-2, "npcs");

        lua.push(this::players);
        lua.setField(-2, "players");

        lua.push(this::ground_items);
        lua.setField(-2, "ground_items");

        lua.push(this::objects);
        lua.setField(-2, "objects");

        lua.setGlobal("scene");
    }

    private int npcs(final Lua lua) {
        final List<NPC> npcs = client.getNpcs();

        lua.createTable(npcs.size(), 0);
        int index = 1;

        for (final NPC npc : npcs) {
            if (npc == null || npc.getName() == null) {
                continue;
            }

            lua.createTable(0, 10);

            pushString(lua, "name", npc.getName());
            pushInt(lua, "id", npc.getId());
            pushInt(lua, "combat", npc.getCombatLevel());
            pushInt(lua, "animation", npc.getAnimation());
            pushInt(lua, "hp_ratio", npc.getHealthRatio());
            pushInt(lua, "hp_scale", npc.getHealthScale());
            pushBool(lua, "is_dead", npc.isDead());

            final WorldPoint wp = npc.getWorldLocation();
            if (wp != null) {
                pushInt(lua, "x", wp.getX());
                pushInt(lua, "y", wp.getY());
                pushInt(lua, "plane", wp.getPlane());
            }

            lua.rawSetI(-2, index++);
        }

        return 1;
    }

    private int players(final Lua lua) {
        final List<Player> players = client.getPlayers();

        lua.createTable(players.size(), 0);
        int index = 1;

        for (final Player player : players) {
            if (player == null || player.getName() == null) {
                continue;
            }

            lua.createTable(0, 10);

            pushString(lua, "name", player.getName());
            pushInt(lua, "combat", player.getCombatLevel());
            pushInt(lua, "animation", player.getAnimation());
            pushInt(lua, "hp_ratio", player.getHealthRatio());
            pushInt(lua, "hp_scale", player.getHealthScale());
            pushBool(lua, "is_dead", player.isDead());
            pushBool(lua, "is_friend", player.isFriend());
            pushBool(lua, "is_clan", player.isClanMember());
            pushInt(lua, "team", player.getTeam());

            final WorldPoint wp = player.getWorldLocation();
            if (wp != null) {
                pushInt(lua, "x", wp.getX());
                pushInt(lua, "y", wp.getY());
                pushInt(lua, "plane", wp.getPlane());
            }

            lua.rawSetI(-2, index++);
        }

        return 1;
    }

    private int ground_items(final Lua lua) {
        final Scene scene = client.getScene();
        final Tile[][][] tiles = scene.getTiles();
        final int plane = client.getPlane();

        lua.createTable(0, 0);
        int index = 1;

        for (int x = 0; x < tiles[plane].length; x++) {
            for (int y = 0; y < tiles[plane][x].length; y++) {
                final Tile tile = tiles[plane][x][y];
                if (tile == null) {
                    continue;
                }

                final List<TileItem> items = tile.getGroundItems();
                if (items == null) {
                    continue;
                }

                final WorldPoint wp = tile.getWorldLocation();

                for (final TileItem item : items) {
                    if (item == null) {
                        continue;
                    }

                    lua.createTable(0, 8);

                    final int itemId = item.getId();
                    pushInt(lua, "id", itemId);
                    pushInt(lua, "quantity", item.getQuantity());
                    pushInt(lua, "ownership", item.getOwnership());
                    pushBool(lua, "is_private", item.isPrivate());

                    final ItemComposition comp = itemManager.getItemComposition(itemId);
                    if (comp != null) {
                        pushString(lua, "name", comp.getName());
                    }

                    if (wp != null) {
                        pushInt(lua, "x", wp.getX());
                        pushInt(lua, "y", wp.getY());
                        pushInt(lua, "plane", wp.getPlane());
                    }

                    lua.rawSetI(-2, index++);
                }
            }
        }

        return 1;
    }

    private int objects(final Lua lua) {
        // Optional name filter:
        //   scene:objects()                          -- all objects
        //   scene:objects("Bank booth")              -- single name filter
        //   scene:objects({"Bank booth", "Tree"})    -- multiple name filters
        List<String> filters = null;
        if (lua.getTop() >= 2) {
            if (lua.isString(2)) {
                filters = List.of(lua.toString(2).toLowerCase());
            } else if (lua.isTable(2)) {
                filters = new ArrayList<>();
                final int len = lua.rawLength(2);
                for (int i = 1; i <= len; i++) {
                    lua.rawGetI(2, i);
                    if (lua.isString(-1)) {
                        filters.add(lua.toString(-1).toLowerCase());
                    }
                    lua.pop(1);
                }
            }
        }

        final Scene scene = client.getScene();
        final Tile[][][] tiles = scene.getTiles();
        final int plane = client.getPlane();

        lua.createTable(0, 0);
        int index = 1;

        for (int x = 0; x < tiles[plane].length; x++) {
            for (int y = 0; y < tiles[plane][x].length; y++) {
                final Tile tile = tiles[plane][x][y];
                if (tile == null) {
                    continue;
                }

                final WorldPoint wp = tile.getWorldLocation();

                // Game objects (trees, rocks, interactables, etc.)
                final GameObject[] gameObjects = tile.getGameObjects();
                if (gameObjects != null) {
                    for (final GameObject obj : gameObjects) {
                        if (obj == null) {
                            continue;
                        }
                        index = pushTileObject(lua, obj, wp, filters, "game", index);
                    }
                }

                // Wall objects (doors, gates, walls)
                final WallObject wall = tile.getWallObject();
                if (wall != null) {
                    index = pushTileObject(lua, wall, wp, filters, "wall", index);
                }

                // Ground objects (floor decorations)
                final GroundObject ground = tile.getGroundObject();
                if (ground != null) {
                    index = pushTileObject(lua, ground, wp, filters, "ground", index);
                }

                // Decorative objects (wall decorations, curtains)
                final DecorativeObject decor = tile.getDecorativeObject();
                if (decor != null) {
                    index = pushTileObject(lua, decor, wp, filters, "decorative", index);
                }
            }
        }

        return 1;
    }

    private int pushTileObject(
        final Lua lua,
        final TileObject obj,
        final WorldPoint wp,
        final List<String> filters,
        final String type,
        final int index
    ) {
        final int id = obj.getId();
        final ObjectComposition comp = client.getObjectDefinition(id);
        if (comp == null) {
            return index;
        }

        final String name = comp.getName();
        if (name == null || "null".equals(name)) {
            return index;
        }

        if (filters != null) {
            final String lower = name.toLowerCase();
            boolean matched = false;
            for (final String f : filters) {
                if (lower.contains(f)) {
                    matched = true;
                    break;
                }
            }
            if (!matched) {
                return index;
            }
        }

        final String[] actions = comp.getActions();

        lua.createTable(0, 7);

        pushString(lua, "name", name);
        pushInt(lua, "id", id);
        pushString(lua, "type", type);

        if (wp != null) {
            pushInt(lua, "x", wp.getX());
            pushInt(lua, "y", wp.getY());
            pushInt(lua, "plane", wp.getPlane());
        }

        // Actions array
        if (actions != null) {
            lua.createTable(actions.length, 0);
            int ai = 1;
            for (final String action : actions) {
                if (action != null) {
                    lua.push(action);
                    lua.rawSetI(-2, ai);
                }
                ai++;
            }
            lua.setField(-2, "actions");
        }

        lua.rawSetI(-2, index);
        return index + 1;
    }

    private static void pushString(final Lua lua, final String key, final String value) {
        lua.push(value);
        lua.setField(-2, key);
    }

    private static void pushInt(final Lua lua, final String key, final int value) {
        lua.push(value);
        lua.setField(-2, key);
    }

    private static void pushBool(final Lua lua, final String key, final boolean value) {
        lua.push(value);
        lua.setField(-2, key);
    }
}
