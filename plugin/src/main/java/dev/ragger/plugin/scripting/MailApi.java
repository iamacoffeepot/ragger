package dev.ragger.plugin.scripting;

import party.iroiro.luajava.Lua;

import java.util.Map;

/**
 * Lua binding for inter-script messaging.
 * Exposed as the global "mail" table in Lua scripts.
 *
 * Usage in Lua:
 *   mail:send("target-script", { key = "value" })
 */
public class MailApi {

    private final String senderName;
    private final ScriptManager manager;

    public MailApi(String senderName, ScriptManager manager) {
        this.senderName = senderName;
        this.manager = manager;
    }

    public void register(Lua lua) {
        lua.createTable(0, 1);

        lua.push(this::send);
        lua.setField(-2, "send");

        lua.setGlobal("mail");
    }

    /**
     * mail:send(target, data)
     * arg 2 = target script name (string)
     * arg 3 = data table
     */
    private int send(Lua lua) {
        String target = lua.toString(2);
        if (target == null || target.isEmpty()) {
            lua.error("mail:send requires a target name");
            return 0;
        }

        Map<String, Object> data;
        if (lua.type(3) == Lua.LuaType.TABLE) {
            data = LuaUtils.tableToMap(lua, 3);
        } else {
            lua.error("mail:send requires a table as second argument");
            return 0;
        }

        manager.enqueueMail(senderName, target, data);
        return 0;
    }
}
