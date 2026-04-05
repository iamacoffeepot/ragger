package dev.ragger.plugin.scripting;

import net.runelite.api.*;
import net.runelite.api.coords.WorldPoint;
import net.runelite.api.events.*;

import java.util.HashMap;
import java.util.Map;

/**
 * A buffered game event destined for Lua actor hooks.
 *
 * Events are created via static factories from RuneLite event objects,
 * buffered in ActorManager, and dispatched to actors after on_tick.
 * The event carries a type (used for dispatch) and a data map
 * (pushed as a Lua table to the hook).
 */
public class LuaEvent {

    public enum Type {
        HITSPLAT,
        PROJECTILE,
        DEATH,
        CHAT,
        ITEM_SPAWNED,
        ITEM_DESPAWNED,
        INVENTORY_CHANGED,
        XP_DROP,
        PLAYER_SPAWNED,
        PLAYER_DESPAWNED,
        NPC_SPAWNED,
        NPC_DESPAWNED,
        ANIMATION,
        GRAPHIC,
        GAME_OBJECT_SPAWNED,
        GAME_OBJECT_DESPAWNED,
        VARP_CHANGED,
        LOGIN,
        LOGOUT,
        WORLD_CHANGED,
        WIDGET_LOADED,
        WIDGET_CLOSED,
        MOUSE_CLICK,
    }

    private final Type type;
    private final Map<String, Object> data;

    private LuaEvent(Type type, Map<String, Object> data) {
        this.type = type;
        this.data = data;
    }

    public Type getType() {
        return type;
    }

    public Map<String, Object> getData() {
        return data;
    }

    // -- Static factories --

    public static LuaEvent fromHitsplat(HitsplatApplied event) {
        Map<String, Object> data = new HashMap<>();
        Hitsplat splat = event.getHitsplat();
        Actor actor = event.getActor();

        data.put("amount", splat.getAmount());
        data.put("type", splat.getHitsplatType());
        data.put("is_mine", splat.isMine());

        if (actor instanceof NPC npc) {
            data.put("target_type", "npc");
            data.put("target_name", npc.getName());
            data.put("target_id", npc.getId());
        } else if (actor instanceof Player player) {
            data.put("target_type", "player");
            data.put("target_name", player.getName());
        }

        return new LuaEvent(Type.HITSPLAT, data);
    }

    public static LuaEvent fromProjectile(ProjectileMoved event) {
        Map<String, Object> data = new HashMap<>();
        Projectile proj = event.getProjectile();

        data.put("id", proj.getId());
        data.put("src_x", (int) proj.getX1());
        data.put("src_y", (int) proj.getY1());
        data.put("dst_x", event.getPosition().getX());
        data.put("dst_y", event.getPosition().getY());
        data.put("start_cycle", proj.getStartCycle());
        data.put("end_cycle", proj.getEndCycle());
        data.put("remaining_cycles", proj.getRemainingCycles());

        Actor target = proj.getInteracting();
        if (target instanceof NPC npc) {
            data.put("target_type", "npc");
            data.put("target_name", npc.getName());
            data.put("target_id", npc.getId());
        } else if (target instanceof Player player) {
            data.put("target_type", "player");
            data.put("target_name", player.getName());
        }

        return new LuaEvent(Type.PROJECTILE, data);
    }

    public static LuaEvent fromActorDeath(ActorDeath event) {
        Map<String, Object> data = new HashMap<>();
        Actor actor = event.getActor();

        if (actor instanceof NPC npc) {
            data.put("type", "npc");
            data.put("name", npc.getName());
            data.put("id", npc.getId());
        } else if (actor instanceof Player player) {
            data.put("type", "player");
            data.put("name", player.getName());
        }

        return new LuaEvent(Type.DEATH, data);
    }

    public static LuaEvent fromChat(ChatMessage event) {
        Map<String, Object> data = new HashMap<>();
        data.put("type", event.getType().getType());
        data.put("sender", event.getName());
        data.put("message", event.getMessage());
        return new LuaEvent(Type.CHAT, data);
    }

    public static LuaEvent fromItemSpawned(ItemSpawned event) {
        Map<String, Object> data = new HashMap<>();
        TileItem item = event.getItem();
        Tile tile = event.getTile();
        WorldPoint wp = tile.getWorldLocation();

        data.put("id", item.getId());
        data.put("quantity", item.getQuantity());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.ITEM_SPAWNED, data);
    }

    public static LuaEvent fromItemDespawned(ItemDespawned event) {
        Map<String, Object> data = new HashMap<>();
        TileItem item = event.getItem();
        Tile tile = event.getTile();
        WorldPoint wp = tile.getWorldLocation();

        data.put("id", item.getId());
        data.put("quantity", item.getQuantity());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.ITEM_DESPAWNED, data);
    }

    public static LuaEvent fromInventoryChanged(int slot, int oldId, int oldQty, int newId, int newQty) {
        Map<String, Object> data = new HashMap<>();
        data.put("slot", slot);
        data.put("old_id", oldId);
        data.put("old_qty", oldQty);
        data.put("new_id", newId);
        data.put("new_qty", newQty);
        return new LuaEvent(Type.INVENTORY_CHANGED, data);
    }

    public static LuaEvent fromStatChanged(StatChanged event) {
        Map<String, Object> data = new HashMap<>();
        data.put("skill", event.getSkill().ordinal());
        data.put("skill_name", event.getSkill().getName());
        data.put("xp", event.getXp());
        data.put("level", event.getLevel());
        data.put("boosted_level", event.getBoostedLevel());
        return new LuaEvent(Type.XP_DROP, data);
    }

    public static LuaEvent fromPlayerSpawned(PlayerSpawned event) {
        Map<String, Object> data = new HashMap<>();
        Player p = event.getPlayer();
        WorldPoint wp = p.getWorldLocation();

        data.put("name", p.getName());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("combat", p.getCombatLevel());

        return new LuaEvent(Type.PLAYER_SPAWNED, data);
    }

    public static LuaEvent fromPlayerDespawned(PlayerDespawned event) {
        Map<String, Object> data = new HashMap<>();
        data.put("name", event.getPlayer().getName());
        return new LuaEvent(Type.PLAYER_DESPAWNED, data);
    }

    public static LuaEvent fromNpcSpawned(NpcSpawned event) {
        Map<String, Object> data = new HashMap<>();
        NPC npc = event.getNpc();
        WorldPoint wp = npc.getWorldLocation();

        data.put("name", npc.getName());
        data.put("id", npc.getId());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("combat", npc.getCombatLevel());

        return new LuaEvent(Type.NPC_SPAWNED, data);
    }

    public static LuaEvent fromNpcDespawned(NpcDespawned event) {
        Map<String, Object> data = new HashMap<>();
        NPC npc = event.getNpc();

        data.put("name", npc.getName());
        data.put("id", npc.getId());

        return new LuaEvent(Type.NPC_DESPAWNED, data);
    }

    public static LuaEvent fromAnimation(Actor actor, int animationId) {
        Map<String, Object> data = new HashMap<>();
        data.put("animation", animationId);

        if (actor instanceof NPC npc) {
            data.put("type", "npc");
            data.put("name", npc.getName());
            data.put("id", npc.getId());
        } else if (actor instanceof Player player) {
            data.put("type", "player");
            data.put("name", player.getName());
        }

        return new LuaEvent(Type.ANIMATION, data);
    }

    public static LuaEvent fromGraphic(Actor actor, int graphicId) {
        Map<String, Object> data = new HashMap<>();
        data.put("graphic", graphicId);

        if (actor instanceof NPC npc) {
            data.put("type", "npc");
            data.put("name", npc.getName());
            data.put("id", npc.getId());
        } else if (actor instanceof Player player) {
            data.put("type", "player");
            data.put("name", player.getName());
        }

        return new LuaEvent(Type.GRAPHIC, data);
    }

    public static LuaEvent fromGameObjectSpawned(GameObjectSpawned event) {
        Map<String, Object> data = new HashMap<>();
        GameObject obj = event.getGameObject();
        WorldPoint wp = obj.getWorldLocation();

        data.put("id", obj.getId());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.GAME_OBJECT_SPAWNED, data);
    }

    public static LuaEvent fromGameObjectDespawned(GameObjectDespawned event) {
        Map<String, Object> data = new HashMap<>();
        GameObject obj = event.getGameObject();
        WorldPoint wp = obj.getWorldLocation();

        data.put("id", obj.getId());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.GAME_OBJECT_DESPAWNED, data);
    }

    public static LuaEvent fromVarpChanged(VarbitChanged event) {
        Map<String, Object> data = new HashMap<>();
        data.put("varp_id", event.getVarpId());
        data.put("varbit_id", event.getVarbitId());
        data.put("value", event.getValue());
        return new LuaEvent(Type.VARP_CHANGED, data);
    }

    public static LuaEvent fromLogin() {
        return new LuaEvent(Type.LOGIN, new HashMap<>());
    }

    public static LuaEvent fromLogout() {
        return new LuaEvent(Type.LOGOUT, new HashMap<>());
    }

    public static LuaEvent fromWorldChanged(int oldWorld, int newWorld) {
        Map<String, Object> data = new HashMap<>();
        data.put("old_world", oldWorld);
        data.put("new_world", newWorld);
        return new LuaEvent(Type.WORLD_CHANGED, data);
    }

    public static LuaEvent fromWidgetLoaded(WidgetLoaded event) {
        Map<String, Object> data = new HashMap<>();
        data.put("group_id", event.getGroupId());
        return new LuaEvent(Type.WIDGET_LOADED, data);
    }

    public static LuaEvent fromWidgetClosed(WidgetClosed event) {
        Map<String, Object> data = new HashMap<>();
        data.put("group_id", event.getGroupId());
        return new LuaEvent(Type.WIDGET_CLOSED, data);
    }

    public static LuaEvent fromMouseClick(java.awt.event.MouseEvent event) {
        Map<String, Object> data = new HashMap<>();
        data.put("x", event.getX());
        data.put("y", event.getY());
        data.put("button", event.getButton());
        data.put("shift", event.isShiftDown());
        data.put("ctrl", event.isControlDown());
        return new LuaEvent(Type.MOUSE_CLICK, data);
    }
}
