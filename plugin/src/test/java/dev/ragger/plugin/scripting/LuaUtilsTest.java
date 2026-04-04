package dev.ragger.plugin.scripting;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import party.iroiro.luajava.Lua;
import party.iroiro.luajava.luaj.LuaJ;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.*;

public class LuaUtilsTest {

    private Lua lua;

    @Before
    public void setUp() {
        lua = new LuaJ();
        lua.openLibraries();
    }

    @After
    public void tearDown() {
        if (lua != null) lua.close();
    }

    // -- readValue number handling --

    @Test
    public void testReadValueSmallInteger() {
        lua.push(42);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertEquals(42, result);
    }

    @Test
    public void testReadValueFloat() {
        lua.push(3.14);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertInstanceOf(Double.class, result);
        assertEquals(3.14, (double) result, 0.001);
    }

    @Test
    public void testReadValueLargeNumberStaysDouble() {
        lua.push(3_000_000_000.0);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertInstanceOf(Double.class, result);
        assertEquals(3_000_000_000.0, (double) result, 0.0);
    }

    @Test
    public void testReadValueIntMaxBoundary() {
        lua.push((double) Integer.MAX_VALUE);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertEquals(Integer.MAX_VALUE, result);
    }

    @Test
    public void testReadValueIntMinBoundary() {
        lua.push((double) Integer.MIN_VALUE);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertEquals(Integer.MIN_VALUE, result);
    }

    @Test
    public void testReadValueOverIntMax() {
        lua.push((double) Integer.MAX_VALUE + 1);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertInstanceOf(Double.class, result);
    }

    @Test
    public void testReadValueUnderIntMin() {
        lua.push((double) Integer.MIN_VALUE - 1);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertInstanceOf(Double.class, result);
    }

    // -- readValue other types --

    @Test
    public void testReadValueString() {
        lua.push("hello");
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertEquals("hello", result);
    }

    @Test
    public void testReadValueBoolean() {
        lua.push(true);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertEquals(true, result);
    }

    // -- tableToMap --

    @Test
    @SuppressWarnings("unchecked")
    public void testTableToMapBasic() {
        lua.run("return {a = 1, b = 'two', c = true}");
        Map<String, Object> map = LuaUtils.tableToMap(lua, lua.getTop());
        assertEquals(1, map.get("a"));
        assertEquals("two", map.get("b"));
        assertEquals(true, map.get("c"));
    }

    @Test
    @SuppressWarnings("unchecked")
    public void testTableToMapNested() {
        lua.run("return {outer = {inner = 42}}");
        Map<String, Object> map = LuaUtils.tableToMap(lua, lua.getTop());
        assertInstanceOf(Map.class, map.get("outer"));
        Map<String, Object> inner = (Map<String, Object>) map.get("outer");
        assertEquals(42, inner.get("inner"));
    }

    // -- pushValue round-trip --

    @Test
    public void testPushValueInteger() {
        LuaUtils.pushValue(lua, 42);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertEquals(42, result);
    }

    @Test
    @SuppressWarnings("unchecked")
    public void testPushValueMap() {
        Map<String, Object> input = new HashMap<>();
        input.put("name", "test");
        input.put("count", 5);
        LuaUtils.pushValue(lua, input);

        Map<String, Object> result = LuaUtils.tableToMap(lua, lua.getTop());
        assertEquals("test", result.get("name"));
        assertEquals(5, result.get("count"));
    }

    @Test
    @SuppressWarnings("unchecked")
    public void testPushValueList() {
        List<Object> input = List.of(1, "two", 3);
        LuaUtils.pushValue(lua, input);

        // Should be read back as a list (sequence detection)
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertInstanceOf(List.class, result);
        List<Object> list = (List<Object>) result;
        assertEquals(3, list.size());
        assertEquals(1, list.get(0));
        assertEquals("two", list.get(1));
        assertEquals(3, list.get(2));
    }

    @Test
    public void testPushValueLargeDouble() {
        LuaUtils.pushValue(lua, 3_000_000_000.0);
        Object result = LuaUtils.readValue(lua, lua.getTop(), 0);
        assertInstanceOf(Double.class, result);
        assertEquals(3_000_000_000.0, (double) result, 0.0);
    }

    private static void assertInstanceOf(Class<?> expected, Object actual) {
        assertNotNull("expected non-null value", actual);
        assertTrue("expected " + expected.getSimpleName() + " but was " + actual.getClass().getSimpleName(),
            expected.isInstance(actual));
    }
}
