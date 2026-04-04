package dev.ragger.plugin.scripting;

import party.iroiro.luajava.Lua;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Shared utilities for converting data between Java and Lua states.
 */
public final class LuaUtils {

    private static final int MAX_DEPTH = 8;

    private LuaUtils() {}

    /**
     * Convert a Lua table at the given stack index to a Java Map or List.
     * Indexed tables (consecutive integer keys starting at 1) become List&lt;Object&gt;.
     * Mixed/string-keyed tables become Map&lt;String, Object&gt;.
     * Nested tables are recursed up to MAX_DEPTH.
     */
    /**
     * Convert a negative Lua stack index to a positive (absolute) index.
     * Positive indices and pseudo-indices are returned unchanged.
     */
    private static int abs(Lua lua, int index) {
        return index >= 0 ? index : lua.getTop() + index + 1;
    }

    public static Map<String, Object> tableToMap(Lua lua, int index) {
        return tableToMapImpl(lua, abs(lua, index), 0);
    }

    private static Map<String, Object> tableToMapImpl(Lua lua, int absIndex, int depth) {
        Map<String, Object> map = new HashMap<>();
        lua.pushNil();
        while (lua.next(absIndex) != 0) {
            String key = lua.toString(-2);
            map.put(key, readValue(lua, abs(lua, -1), depth));
            lua.pop(1);
        }
        return map;
    }

    private static List<Object> tableToListImpl(Lua lua, int absIndex, int depth) {
        List<Object> list = new ArrayList<>();
        lua.pushNil();
        while (lua.next(absIndex) != 0) {
            list.add(readValue(lua, abs(lua, -1), depth));
            lua.pop(1);
        }
        return list;
    }

    /**
     * Read a Lua value at the given absolute stack index, recursing into tables.
     */
    static Object readValue(Lua lua, int absIndex, int depth) {
        switch (lua.type(absIndex)) {
            case STRING:
                return lua.toString(absIndex);
            case NUMBER:
                double num = lua.toNumber(absIndex);
                if (num == Math.floor(num) && !Double.isInfinite(num)) {
                    return (int) num;
                }
                return num;
            case BOOLEAN:
                return lua.toBoolean(absIndex);
            case TABLE:
                if (depth >= MAX_DEPTH) {
                    return lua.toString(absIndex);
                }
                if (isSequence(lua, absIndex)) {
                    return tableToListImpl(lua, absIndex, depth + 1);
                }
                return tableToMapImpl(lua, absIndex, depth + 1);
            default:
                return lua.toString(absIndex);
        }
    }

    /**
     * Check if a Lua table is a sequence (consecutive integer keys starting at 1).
     */
    private static boolean isSequence(Lua lua, int absIndex) {
        int len = lua.rawLength(absIndex);
        if (len == 0) {
            // Could be empty table — check if it has any keys at all
            lua.pushNil();
            if (lua.next(absIndex) != 0) {
                lua.pop(2); // pop key+value
                return false; // has keys but length 0 → not a sequence
            }
            return true; // empty table, treat as empty list
        }
        // Verify no extra keys beyond 1..len
        int count = 0;
        lua.pushNil();
        while (lua.next(absIndex) != 0) {
            lua.pop(1);
            count++;
            if (count > len) {
                // Pop the remaining key so the iterator is cleaned up
                lua.pop(1);
                return false;
            }
        }
        return count == len;
    }

    /**
     * Push a Java value onto the Lua stack.
     * Handles String, Integer, Double, Boolean, Number, List, and Map.
     */
    @SuppressWarnings("unchecked")
    public static void pushValue(Lua lua, Object value) {
        if (value instanceof String) {
            lua.push((String) value);
        } else if (value instanceof Integer) {
            lua.push((int) value);
        } else if (value instanceof Double) {
            lua.push((double) value);
        } else if (value instanceof Boolean) {
            lua.push((boolean) value);
        } else if (value instanceof Number) {
            lua.push(((Number) value).doubleValue());
        } else if (value instanceof List) {
            List<Object> list = (List<Object>) value;
            lua.createTable(list.size(), 0);
            for (int i = 0; i < list.size(); i++) {
                pushValue(lua, list.get(i));
                lua.rawSetI(-2, i + 1);
            }
        } else if (value instanceof Map) {
            Map<String, Object> map = (Map<String, Object>) value;
            lua.createTable(0, map.size());
            for (Map.Entry<String, Object> entry : map.entrySet()) {
                pushValue(lua, entry.getValue());
                lua.setField(-2, entry.getKey());
            }
        } else {
            lua.push(String.valueOf(value));
        }
    }

    /**
     * Push a Java Map as a Lua table onto the stack.
     * Handles nested Maps, Lists, and primitive values.
     */
    public static void pushArgsTable(Lua lua, Map<String, Object> map) {
        lua.createTable(0, map.size());
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            pushValue(lua, entry.getValue());
            lua.setField(-2, entry.getKey());
        }
    }
}
