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
     * Convert a negative Lua stack index to a positive (absolute) index.
     * Positive indices and pseudo-indices are returned unchanged.
     */
    static int abs(final Lua lua, final int index) {
        return index >= 0 ? index : lua.getTop() + index + 1;
    }

    public static Map<String, Object> tableToMap(final Lua lua, final int index) {
        return tableToMapImpl(lua, abs(lua, index), 0);
    }

    private static Map<String, Object> tableToMapImpl(final Lua lua, final int absIndex, final int depth) {
        final Map<String, Object> map = new HashMap<>();

        lua.pushNil();
        while (lua.next(absIndex) != 0) {
            final String key = lua.toString(-2);
            map.put(key, readValue(lua, abs(lua, -1), depth));
            lua.pop(1);
        }

        return map;
    }

    private static List<Object> tableToListImpl(final Lua lua, final int absIndex, final int depth) {
        final List<Object> list = new ArrayList<>();

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
    static Object readValue(final Lua lua, final int absIndex, final int depth) {
        switch (lua.type(absIndex)) {
            case STRING:
                return lua.toString(absIndex);
            case NUMBER:
                final double num = lua.toNumber(absIndex);
                if (num == Math.floor(num) && !Double.isInfinite(num)
                        && num >= Integer.MIN_VALUE && num <= Integer.MAX_VALUE) {
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
    private static boolean isSequence(final Lua lua, final int absIndex) {
        final int len = lua.rawLength(absIndex);

        if (len == 0) {
            // Could be empty table — check if it has any keys at all
            lua.pushNil();
            if (lua.next(absIndex) != 0) {
                lua.pop(2); // pop key+value
                return false; // has keys but length 0 -> not a sequence
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
    public static void pushValue(final Lua lua, final Object value) {
        if (value instanceof String s) {
            lua.push(s);
        } else if (value instanceof Integer i) {
            lua.push(i);
        } else if (value instanceof Double d) {
            lua.push(d);
        } else if (value instanceof Boolean b) {
            lua.push(b);
        } else if (value instanceof Number n) {
            lua.push(n.doubleValue());
        } else if (value instanceof List<?> list) {
            final List<Object> typedList = (List<Object>) list;
            lua.createTable(typedList.size(), 0);
            for (int i = 0; i < typedList.size(); i++) {
                pushValue(lua, typedList.get(i));
                lua.rawSetI(-2, i + 1);
            }
        } else if (value instanceof Map<?, ?> map) {
            final Map<String, Object> typedMap = (Map<String, Object>) map;
            lua.createTable(0, typedMap.size());
            for (final Map.Entry<String, Object> entry : typedMap.entrySet()) {
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
    public static void pushArgsTable(final Lua lua, final Map<String, Object> map) {
        lua.createTable(0, map.size());

        for (final Map.Entry<String, Object> entry : map.entrySet()) {
            pushValue(lua, entry.getValue());
            lua.setField(-2, entry.getKey());
        }
    }
}
