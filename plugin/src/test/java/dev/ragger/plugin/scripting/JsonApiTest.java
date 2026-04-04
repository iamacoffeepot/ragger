package dev.ragger.plugin.scripting;

import com.google.gson.JsonParser;
import org.junit.Test;

import java.util.List;
import java.util.Map;

import static org.junit.Assert.*;

public class JsonApiTest {

    @Test
    public void testIntegerValues() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("42"));
        assertEquals(42, result);
    }

    @Test
    public void testLargeIntegerStaysDouble() {
        // Larger than Integer.MAX_VALUE — must not overflow to negative
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("3000000000"));
        assertInstanceOf(Double.class, result);
        assertEquals(3_000_000_000.0, (double) result, 0.0);
    }

    @Test
    public void testNegativeLargeIntegerStaysDouble() {
        // Smaller than Integer.MIN_VALUE
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("-3000000000"));
        assertInstanceOf(Double.class, result);
        assertEquals(-3_000_000_000.0, (double) result, 0.0);
    }

    @Test
    public void testIntMaxValue() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("2147483647"));
        assertEquals(Integer.MAX_VALUE, result);
    }

    @Test
    public void testIntMinValue() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("-2147483648"));
        assertEquals(Integer.MIN_VALUE, result);
    }

    @Test
    public void testJustOverIntMaxValue() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("2147483648"));
        assertInstanceOf(Double.class, result);
    }

    @Test
    public void testJustUnderIntMinValue() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("-2147483649"));
        assertInstanceOf(Double.class, result);
    }

    @Test
    public void testFloatingPoint() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("3.14"));
        assertInstanceOf(Double.class, result);
        assertEquals(3.14, (double) result, 0.001);
    }

    @Test
    public void testBoolean() {
        assertEquals(true, JsonApi.fromJsonElement(new JsonParser().parse("true")));
        assertEquals(false, JsonApi.fromJsonElement(new JsonParser().parse("false")));
    }

    @Test
    public void testString() {
        assertEquals("hello", JsonApi.fromJsonElement(new JsonParser().parse("\"hello\"")));
    }

    @Test
    public void testNull() {
        assertNull(JsonApi.fromJsonElement(new JsonParser().parse("null")));
    }

    @Test
    @SuppressWarnings("unchecked")
    public void testObject() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("{\"a\":1,\"b\":\"two\"}"));
        assertInstanceOf(Map.class, result);
        Map<String, Object> map = (Map<String, Object>) result;
        assertEquals(1, map.get("a"));
        assertEquals("two", map.get("b"));
    }

    @Test
    @SuppressWarnings("unchecked")
    public void testArray() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse("[1,2,3]"));
        assertInstanceOf(List.class, result);
        List<Object> list = (List<Object>) result;
        assertEquals(List.of(1, 2, 3), list);
    }

    @Test
    @SuppressWarnings("unchecked")
    public void testNestedObjectWithLargeNumber() {
        Object result = JsonApi.fromJsonElement(new JsonParser().parse(
            "{\"price\":3000000000,\"name\":\"Ely\"}"));
        Map<String, Object> map = (Map<String, Object>) result;
        assertInstanceOf(Double.class, map.get("price"));
        assertEquals(3_000_000_000.0, (double) map.get("price"), 0.0);
        assertEquals("Ely", map.get("name"));
    }

    private static void assertInstanceOf(Class<?> expected, Object actual) {
        assertNotNull("expected non-null value", actual);
        assertTrue("expected " + expected.getSimpleName() + " but was " + actual.getClass().getSimpleName(),
            expected.isInstance(actual));
    }
}
