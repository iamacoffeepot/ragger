package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import party.iroiro.luajava.Lua;

/**
 * Lua bindings for reading game variables.
 *
 * Registers two globals:
 *   varp — player variables (varps and varbits)
 *   varc — client variables (integers and strings)
 */
public class VarApi {

    private final Client client;

    public VarApi(Client client) {
        this.client = client;
    }

    public void register(Lua lua) {
        // varp: player variables
        lua.createTable(0, 2);

        lua.push(this::varpGet);
        lua.setField(-2, "get");

        lua.push(this::varpBit);
        lua.setField(-2, "bit");

        lua.setGlobal("varp");

        // varc: client variables
        lua.createTable(0, 2);

        lua.push(this::varcInt);
        lua.setField(-2, "int");

        lua.push(this::varcStr);
        lua.setField(-2, "str");

        lua.setGlobal("varc");
    }

    /**
     * varp:get(id) -> int
     * Read a raw varp (variable player) slot value.
     */
    private int varpGet(Lua lua) {
        int id = (int) lua.toInteger(2);
        lua.push(client.getVarpValue(id));
        return 1;
    }

    /**
     * varp:bit(id) -> int
     * Read a varbit value. RuneLite extracts the bit range from the
     * appropriate varp slot automatically.
     */
    private int varpBit(Lua lua) {
        int id = (int) lua.toInteger(2);
        lua.push(client.getVarbitValue(id));
        return 1;
    }

    /**
     * varc:int(id) -> int
     * Read a client integer variable.
     */
    private int varcInt(Lua lua) {
        int id = (int) lua.toInteger(2);
        lua.push(client.getVarcIntValue(id));
        return 1;
    }

    /**
     * varc:str(id) -> string | nil
     * Read a client string variable.
     */
    private int varcStr(Lua lua) {
        int id = (int) lua.toInteger(2);
        String value = client.getVarcStrValue(id);
        if (value == null) {
            lua.pushNil();
        } else {
            lua.push(value);
        }
        return 1;
    }
}
