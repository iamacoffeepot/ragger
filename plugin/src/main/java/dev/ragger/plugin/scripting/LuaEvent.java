package dev.ragger.plugin.scripting;

import net.runelite.api.Actor;
import net.runelite.api.GameObject;
import net.runelite.api.Hitsplat;
import net.runelite.api.NPC;
import net.runelite.api.Player;
import net.runelite.api.Projectile;
import net.runelite.api.Scene;
import net.runelite.api.Tile;
import net.runelite.api.TileItem;
import net.runelite.api.coords.WorldPoint;
import net.runelite.api.events.ActorDeath;
import net.runelite.api.events.ChatMessage;
import net.runelite.api.events.GameObjectDespawned;
import net.runelite.api.events.GameObjectSpawned;
import net.runelite.api.events.HitsplatApplied;
import net.runelite.api.events.ItemDespawned;
import net.runelite.api.events.ItemSpawned;
import net.runelite.api.events.NpcDespawned;
import net.runelite.api.events.NpcSpawned;
import net.runelite.api.events.PlayerDespawned;
import net.runelite.api.events.PlayerSpawned;
import net.runelite.api.events.ProjectileMoved;
import net.runelite.api.events.StatChanged;
import net.runelite.api.events.VarbitChanged;
import net.runelite.api.events.WidgetClosed;
import net.runelite.api.events.WidgetLoaded;

import java.awt.event.MouseEvent;
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

    private LuaEvent(final Type type, final Map<String, Object> data) {
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

    public static LuaEvent fromHitsplat(final HitsplatApplied event) {
        final Map<String, Object> data = new HashMap<>();
        final Hitsplat splat = event.getHitsplat();
        final Actor actor = event.getActor();

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

    public static LuaEvent fromProjectile(final ProjectileMoved event) {
        final Map<String, Object> data = new HashMap<>();
        final Projectile proj = event.getProjectile();

        data.put("id", proj.getId());
        data.put("src_x", (int) proj.getX1());
        data.put("src_y", (int) proj.getY1());
        data.put("dst_x", event.getPosition().getX());
        data.put("dst_y", event.getPosition().getY());
        data.put("start_cycle", proj.getStartCycle());
        data.put("end_cycle", proj.getEndCycle());
        data.put("remaining_cycles", proj.getRemainingCycles());

        final Actor target = proj.getInteracting();
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

    public static LuaEvent fromActorDeath(final ActorDeath event) {
        final Map<String, Object> data = new HashMap<>();
        final Actor actor = event.getActor();

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

    public static LuaEvent fromChat(final ChatMessage event) {
        final Map<String, Object> data = new HashMap<>();
        data.put("type", event.getType().getType());
        data.put("sender", event.getName());
        data.put("message", event.getMessage());
        return new LuaEvent(Type.CHAT, data);
    }

    public static LuaEvent fromItemSpawned(final ItemSpawned event) {
        final Map<String, Object> data = new HashMap<>();
        final TileItem item = event.getItem();
        final Tile tile = event.getTile();
        final WorldPoint wp = tile.getWorldLocation();

        data.put("id", item.getId());
        data.put("quantity", item.getQuantity());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.ITEM_SPAWNED, data);
    }

    public static LuaEvent fromItemDespawned(final ItemDespawned event) {
        final Map<String, Object> data = new HashMap<>();
        final TileItem item = event.getItem();
        final Tile tile = event.getTile();
        final WorldPoint wp = tile.getWorldLocation();

        data.put("id", item.getId());
        data.put("quantity", item.getQuantity());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.ITEM_DESPAWNED, data);
    }

    public static LuaEvent fromInventoryChanged(
            final int slot, final int oldId, final int oldQty, final int newId, final int newQty) {
        final Map<String, Object> data = new HashMap<>();
        data.put("slot", slot);
        data.put("old_id", oldId);
        data.put("old_qty", oldQty);
        data.put("new_id", newId);
        data.put("new_qty", newQty);
        return new LuaEvent(Type.INVENTORY_CHANGED, data);
    }

    public static LuaEvent fromStatChanged(final StatChanged event) {
        final Map<String, Object> data = new HashMap<>();
        data.put("skill", event.getSkill().ordinal());
        data.put("skill_name", event.getSkill().getName());
        data.put("xp", event.getXp());
        data.put("level", event.getLevel());
        data.put("boosted_level", event.getBoostedLevel());
        return new LuaEvent(Type.XP_DROP, data);
    }

    public static LuaEvent fromPlayerSpawned(final PlayerSpawned event) {
        final Map<String, Object> data = new HashMap<>();
        final Player p = event.getPlayer();
        final WorldPoint wp = p.getWorldLocation();

        data.put("name", p.getName());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("combat", p.getCombatLevel());

        return new LuaEvent(Type.PLAYER_SPAWNED, data);
    }

    public static LuaEvent fromPlayerDespawned(final PlayerDespawned event) {
        final Map<String, Object> data = new HashMap<>();
        data.put("name", event.getPlayer().getName());
        return new LuaEvent(Type.PLAYER_DESPAWNED, data);
    }

    public static LuaEvent fromNpcSpawned(final NpcSpawned event) {
        final Map<String, Object> data = new HashMap<>();
        final NPC npc = event.getNpc();
        final WorldPoint wp = npc.getWorldLocation();

        data.put("name", npc.getName());
        data.put("id", npc.getId());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("combat", npc.getCombatLevel());

        return new LuaEvent(Type.NPC_SPAWNED, data);
    }

    public static LuaEvent fromNpcDespawned(final NpcDespawned event) {
        final Map<String, Object> data = new HashMap<>();
        final NPC npc = event.getNpc();

        data.put("name", npc.getName());
        data.put("id", npc.getId());

        return new LuaEvent(Type.NPC_DESPAWNED, data);
    }

    public static LuaEvent fromAnimation(final Actor actor, final int animationId) {
        final Map<String, Object> data = new HashMap<>();
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

    public static LuaEvent fromGraphic(final Actor actor, final int graphicId) {
        final Map<String, Object> data = new HashMap<>();
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

    public static LuaEvent fromGameObjectSpawned(final GameObjectSpawned event) {
        final Map<String, Object> data = new HashMap<>();
        final GameObject obj = event.getGameObject();
        final WorldPoint wp = obj.getWorldLocation();

        data.put("id", obj.getId());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.GAME_OBJECT_SPAWNED, data);
    }

    public static LuaEvent fromGameObjectDespawned(final GameObjectDespawned event) {
        final Map<String, Object> data = new HashMap<>();
        final GameObject obj = event.getGameObject();
        final WorldPoint wp = obj.getWorldLocation();

        data.put("id", obj.getId());
        data.put("x", wp.getX());
        data.put("y", wp.getY());
        data.put("plane", wp.getPlane());

        return new LuaEvent(Type.GAME_OBJECT_DESPAWNED, data);
    }

    public static LuaEvent fromVarpChanged(final VarbitChanged event) {
        final Map<String, Object> data = new HashMap<>();
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

    public static LuaEvent fromWorldChanged(final int oldWorld, final int newWorld) {
        final Map<String, Object> data = new HashMap<>();
        data.put("old_world", oldWorld);
        data.put("new_world", newWorld);
        return new LuaEvent(Type.WORLD_CHANGED, data);
    }

    public static LuaEvent fromWidgetLoaded(final WidgetLoaded event) {
        final Map<String, Object> data = new HashMap<>();
        data.put("group_id", event.getGroupId());
        return new LuaEvent(Type.WIDGET_LOADED, data);
    }

    public static LuaEvent fromWidgetClosed(final WidgetClosed event) {
        final Map<String, Object> data = new HashMap<>();
        data.put("group_id", event.getGroupId());
        return new LuaEvent(Type.WIDGET_CLOSED, data);
    }

    public static LuaEvent fromMouseClick(final MouseEvent event) {
        final Map<String, Object> data = new HashMap<>();
        data.put("x", event.getX());
        data.put("y", event.getY());
        data.put("button", event.getButton());
        data.put("shift", event.isShiftDown());
        data.put("ctrl", event.isControlDown());
        return new LuaEvent(Type.MOUSE_CLICK, data);
    }
}
