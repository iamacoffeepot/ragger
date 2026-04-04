package dev.ragger.plugin.scripting;

import party.iroiro.luajava.Lua;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Lua binding for managing child scripts.
 * Exposed as the global "scripts" table in Lua scripts.
 *
 * All operations are scoped to the caller's namespace — a script can only
 * manage its own children, not siblings or parents.
 *
 * Usage in Lua:
 *   scripts:run("child-name", source)
 *   scripts:stop("child-name")
 *   scripts:list()
 *   scripts:source("child-name")
 *   scripts:is_running("child-name")
 *   scripts:define("template-name", source)
 *   scripts:create("child-name", "template-name")
 *   scripts:create("child-name", "template-name", { key = value })
 *   scripts:templates()
 */
public class ScriptsApi {

    private final String parentName;
    private final ScriptManager manager;

    public ScriptsApi(String parentName, ScriptManager manager) {
        this.parentName = parentName;
        this.manager = manager;
    }

    public void register(Lua lua) {
        lua.createTable(0, 9);

        lua.push(this::run);
        lua.setField(-2, "run");

        lua.push(this::stop);
        lua.setField(-2, "stop");

        lua.push(this::list);
        lua.setField(-2, "list");

        lua.push(this::source);
        lua.setField(-2, "source");

        lua.push(this::is_running);
        lua.setField(-2, "is_running");

        lua.push(this::define);
        lua.setField(-2, "define");

        lua.push(this::create);
        lua.setField(-2, "create");

        lua.push(this::templates);
        lua.setField(-2, "templates");

        lua.setGlobal("scripts");
    }

    /**
     * scripts:run("child-name", source) -> name, or throws on limit
     */
    private int run(Lua lua) {
        String childName = lua.toString(2);
        String source = lua.toString(3);
        String fullName = manager.childName(parentName, childName);
        String result = manager.load(fullName, source);
        lua.push(result);
        return 1;
    }

    /**
     * scripts:stop("child-name")
     */
    private int stop(Lua lua) {
        String childName = lua.toString(2);
        String fullName = manager.childName(parentName, childName);
        manager.unload(fullName);
        return 0;
    }

    /**
     * scripts:list() -> array of child names
     */
    private int list(Lua lua) {
        List<String> children = manager.listChildren(parentName);
        lua.createTable(children.size(), 0);
        for (int i = 0; i < children.size(); i++) {
            lua.push(children.get(i));
            lua.rawSetI(-2, i + 1);
        }
        return 1;
    }

    /**
     * scripts:source("child-name") -> source string or nil
     */
    private int source(Lua lua) {
        String childName = lua.toString(2);
        String fullName = manager.childName(parentName, childName);
        String src = manager.getSource(fullName);
        if (src != null) {
            lua.push(src);
        } else {
            lua.pushNil();
        }
        return 1;
    }

    /**
     * scripts:is_running("child-name") -> boolean
     */
    private int is_running(Lua lua) {
        String childName = lua.toString(2);
        String fullName = manager.childName(parentName, childName);
        lua.push(manager.isRunning(fullName));
        return 1;
    }

    /**
     * scripts:define("template-name", source)
     */
    private int define(Lua lua) {
        String templateName = lua.toString(2);
        String source = lua.toString(3);
        manager.defineTemplate(templateName, source);
        return 0;
    }

    /**
     * scripts:create("child-name", "template-name" [, args_table]) -> name, or throws on limit
     */
    private int create(Lua lua) {
        String childName = lua.toString(2);
        String templateName = lua.toString(3);

        Map<String, Object> args = null;
        if (lua.type(4) == Lua.LuaType.TABLE) {
            args = LuaUtils.tableToMap(lua, 4);
        }

        String source = manager.getTemplate(templateName);
        if (source == null) {
            lua.error("template not found: " + templateName);
            return 0;
        }

        String fullName = manager.childName(parentName, childName);
        String result = manager.load(fullName, source, args);
        lua.push(result);
        return 1;
    }

    /**
     * scripts:templates() -> array of template names
     */
    private int templates(Lua lua) {
        List<String> names = manager.listTemplates();
        lua.createTable(names.size(), 0);
        for (int i = 0; i < names.size(); i++) {
            lua.push(names.get(i));
            lua.rawSetI(-2, i + 1);
        }
        return 1;
    }

}
