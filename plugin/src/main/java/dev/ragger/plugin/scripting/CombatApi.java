package dev.ragger.plugin.scripting;

import net.runelite.api.Actor;
import net.runelite.api.Client;
import net.runelite.api.NPC;
import net.runelite.api.Player;
import net.runelite.api.Prayer;
import party.iroiro.luajava.Lua;

/**
 * Lua binding for combat state — spec energy, prayers, attack style, target.
 * Exposed as the global "combat" table in Lua scripts.
 */
public class CombatApi {

    private static final int VARP_SPEC_ENERGY = 300;
    private static final int VARP_SPEC_ENABLED = 301;
    private static final int VARP_ATTACK_STYLE = 43;

    private final Client client;

    public CombatApi(final Client client) {
        this.client = client;
    }

    public void register(final Lua lua) {
        lua.createTable(0, 6);

        lua.push(this::spec);
        lua.setField(-2, "spec");

        lua.push(this::spec_enabled);
        lua.setField(-2, "spec_enabled");

        lua.push(this::attack_style);
        lua.setField(-2, "attack_style");

        lua.push(this::prayer_active);
        lua.setField(-2, "prayer_active");

        lua.push(this::active_prayers);
        lua.setField(-2, "active_prayers");

        lua.push(this::target);
        lua.setField(-2, "target");

        lua.setGlobal("combat");
    }

    /**
     * combat:spec() -> int (0-1000, divide by 10 for percentage)
     */
    private int spec(final Lua lua) {
        lua.push(client.getVarpValue(VARP_SPEC_ENERGY));
        return 1;
    }

    /**
     * combat:spec_enabled() -> bool (is spec orb toggled on)
     */
    private int spec_enabled(final Lua lua) {
        lua.push(client.getVarpValue(VARP_SPEC_ENABLED) == 1);
        return 1;
    }

    /**
     * combat:attack_style() -> int (0-3, weapon-dependent)
     */
    private int attack_style(final Lua lua) {
        lua.push(client.getVarpValue(VARP_ATTACK_STYLE));
        return 1;
    }

    /**
     * combat:prayer_active(prayer.PROTECT_FROM_MELEE) -> bool
     */
    private int prayer_active(final Lua lua) {
        final Object obj = lua.toJavaObject(2);
        if (!(obj instanceof Prayer)) {
            lua.push(false);
            return 1;
        }

        lua.push(client.isPrayerActive((Prayer) obj));
        return 1;
    }

    /**
     * combat:active_prayers() -> array of Prayer enum values
     */
    private int active_prayers(final Lua lua) {
        lua.createTable(0, 0);
        int index = 1;

        for (final Prayer prayer : Prayer.values()) {
            if (client.isPrayerActive(prayer)) {
                lua.pushJavaObject(prayer);
                lua.rawSetI(-2, index++);
            }
        }

        return 1;
    }

    /**
     * combat:target() -> table {name, type, hp_ratio, hp_scale, animation} or nil
     */
    private int target(final Lua lua) {
        final Player local = client.getLocalPlayer();
        if (local == null) {
            lua.pushNil();
            return 1;
        }

        final Actor interacting = local.getInteracting();
        if (interacting == null) {
            lua.pushNil();
            return 1;
        }

        lua.createTable(0, 5);

        final String name = interacting.getName();
        lua.push(name != null ? name : "Unknown");
        lua.setField(-2, "name");

        if (interacting instanceof NPC npc) {
            lua.push("npc");
            lua.setField(-2, "type");
            lua.push(npc.getId());
            lua.setField(-2, "id");
        } else if (interacting instanceof Player) {
            lua.push("player");
            lua.setField(-2, "type");
        }

        lua.push(interacting.getHealthRatio());
        lua.setField(-2, "hp_ratio");

        lua.push(interacting.getHealthScale());
        lua.setField(-2, "hp_scale");

        lua.push(interacting.getAnimation());
        lua.setField(-2, "animation");

        return 1;
    }
}
