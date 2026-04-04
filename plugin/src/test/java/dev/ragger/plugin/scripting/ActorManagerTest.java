package dev.ragger.plugin.scripting;

import org.junit.Before;
import org.junit.Test;

import static org.junit.Assert.*;

public class ActorManagerTest {

    private ActorManager manager;

    @Before
    public void setUp() {
        // childName is a pure method — null deps are fine for these tests
        manager = new ActorManager(null, null, null);
    }

    @Test
    public void testChildNameBasic() {
        assertEquals("parent/child", manager.childName("parent", "child"));
    }

    @Test
    public void testChildNameNested() {
        assertEquals("parent/child/grandchild",
            manager.childName("parent/child", "grandchild"));
    }

    @Test(expected = IllegalArgumentException.class)
    public void testChildNameRejectsSlash() {
        manager.childName("parent", "bad/name");
    }

    @Test(expected = IllegalArgumentException.class)
    public void testChildNameRejectsDotDot() {
        manager.childName("parent", "..");
    }

    @Test(expected = IllegalArgumentException.class)
    public void testChildNameRejectsDotDotInName() {
        manager.childName("parent", "foo..bar");
    }

    @Test(expected = IllegalArgumentException.class)
    public void testChildNameRejectsEmpty() {
        manager.childName("parent", "");
    }

    @Test(expected = IllegalArgumentException.class)
    public void testChildNameRejectsNull() {
        manager.childName("parent", null);
    }

    @Test
    public void testChildNameAllowsDot() {
        // Single dots are fine (e.g. "timer.v2")
        assertEquals("parent/timer.v2", manager.childName("parent", "timer.v2"));
    }

    @Test
    public void testChildNameAllowsHyphens() {
        assertEquals("parent/npc-highlighter", manager.childName("parent", "npc-highlighter"));
    }
}
