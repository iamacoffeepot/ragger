package dev.ragger.plugin.scripting;

import net.runelite.api.*;
import net.runelite.api.coords.WorldPoint;
import party.iroiro.luajava.Lua;

import java.util.ArrayList;
import java.util.List;

/**
 * Builds the "scene" Lua table with JFunction entries.
 * Each function returns Lua tables with primitive fields.
 */
public class SceneApi {

    private final Client client;

    public SceneApi(Client client) {
        this.client = client;
    }

    /**
     * Register the scene table and all its functions on the Lua state.
     */
    public void register(Lua lua) {
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

    private int npcs(Lua lua) {
        List<NPC> npcs = client.getNpcs();

        lua.createTable(npcs.size(), 0);
        int index = 1;

        for (NPC npc : npcs) {
            if (npc == null || npc.getName() == null) continue;

            lua.createTable(0, 10);

            pushString(lua, "name", npc.getName());
            pushInt(lua, "id", npc.getId());
            pushInt(lua, "combat", npc.getCombatLevel());
            pushInt(lua, "animation", npc.getAnimation());
            pushInt(lua, "hp_ratio", npc.getHealthRatio());
            pushInt(lua, "hp_scale", npc.getHealthScale());
            pushBool(lua, "is_dead", npc.isDead());

            WorldPoint wp = npc.getWorldLocation();
            if (wp != null) {
                pushInt(lua, "x", wp.getX());
                pushInt(lua, "y", wp.getY());
                pushInt(lua, "plane", wp.getPlane());
            }

            lua.rawSetI(-2, index++);
        }

        return 1;
    }

    private int players(Lua lua) {
        List<Player> players = client.getPlayers();

        lua.createTable(players.size(), 0);
        int index = 1;

        for (Player player : players) {
            if (player == null || player.getName() == null) continue;

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

            WorldPoint wp = player.getWorldLocation();
            if (wp != null) {
                pushInt(lua, "x", wp.getX());
                pushInt(lua, "y", wp.getY());
                pushInt(lua, "plane", wp.getPlane());
            }

            lua.rawSetI(-2, index++);
        }

        return 1;
    }

    private int ground_items(Lua lua) {
        Scene scene = client.getScene();
        Tile[][][] tiles = scene.getTiles();
        int plane = client.getPlane();

        lua.createTable(0, 0);
        int index = 1;

        for (int x = 0; x < tiles[plane].length; x++) {
            for (int y = 0; y < tiles[plane][x].length; y++) {
                Tile tile = tiles[plane][x][y];
                if (tile == null) continue;

                List<TileItem> items = tile.getGroundItems();
                if (items == null) continue;

                WorldPoint wp = tile.getWorldLocation();

                for (TileItem item : items) {
                    if (item == null) continue;

                    lua.createTable(0, 7);

                    pushInt(lua, "id", item.getId());
                    pushInt(lua, "quantity", item.getQuantity());
                    pushInt(lua, "ownership", item.getOwnership());
                    pushBool(lua, "is_private", item.isPrivate());

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

    private int objects(Lua lua) {
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
                int len = lua.rawLength(2);
                for (int i = 1; i <= len; i++) {
                    lua.rawGetI(2, i);
                    if (lua.isString(-1)) {
                        filters.add(lua.toString(-1).toLowerCase());
                    }
                    lua.pop(1);
                }
            }
        }

        Scene scene = client.getScene();
        Tile[][][] tiles = scene.getTiles();
        int plane = client.getPlane();

        lua.createTable(0, 0);
        int index = 1;

        for (int x = 0; x < tiles[plane].length; x++) {
            for (int y = 0; y < tiles[plane][x].length; y++) {
                Tile tile = tiles[plane][x][y];
                if (tile == null) continue;

                WorldPoint wp = tile.getWorldLocation();

                // Game objects (trees, rocks, interactables, etc.)
                GameObject[] gameObjects = tile.getGameObjects();
                if (gameObjects != null) {
                    for (GameObject obj : gameObjects) {
                        if (obj == null) continue;
                        index = pushTileObject(lua, obj, wp, filters, "game", index);
                    }
                }

                // Wall objects (doors, gates, walls)
                WallObject wall = tile.getWallObject();
                if (wall != null) {
                    index = pushTileObject(lua, wall, wp, filters, "wall", index);
                }

                // Ground objects (floor decorations)
                GroundObject ground = tile.getGroundObject();
                if (ground != null) {
                    index = pushTileObject(lua, ground, wp, filters, "ground", index);
                }

                // Decorative objects (wall decorations, curtains)
                DecorativeObject decor = tile.getDecorativeObject();
                if (decor != null) {
                    index = pushTileObject(lua, decor, wp, filters, "decorative", index);
                }
            }
        }

        return 1;
    }

    private int pushTileObject(Lua lua, TileObject obj, WorldPoint wp, List<String> filters, String type, int index) {
        int id = obj.getId();
        ObjectComposition comp = client.getObjectDefinition(id);
        if (comp == null) return index;

        String name = comp.getName();
        if (name == null || "null".equals(name)) return index;

        if (filters != null) {
            String lower = name.toLowerCase();
            boolean matched = false;
            for (String f : filters) {
                if (lower.contains(f)) {
                    matched = true;
                    break;
                }
            }
            if (!matched) return index;
        }

        String[] actions = comp.getActions();

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
            for (String action : actions) {
                if (action != null) {
                    lua.push(action);
                    lua.rawSetI(-2, ai);
                }
                ai++;
            }
            lua.setField(-2, "actions");
        }

        lua.rawSetI(-2, index++);
        return index;
    }

    private static void pushString(Lua lua, String key, String value) {
        lua.push(value);
        lua.setField(-2, key);
    }

    private static void pushInt(Lua lua, String key, int value) {
        lua.push(value);
        lua.setField(-2, key);
    }

    private static void pushBool(Lua lua, String key, boolean value) {
        lua.push(value);
        lua.setField(-2, key);
    }
}
