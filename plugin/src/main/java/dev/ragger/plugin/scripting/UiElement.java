package dev.ragger.plugin.scripting;

import net.runelite.api.widgets.Widget;

import java.util.HashMap;
import java.util.Map;

/**
 * Tracks a single UI element (text, rect, button, sprite, item) within a panel.
 * Stores the widget reference, callback refs, and config for viewport rebuild.
 */
public final class UiElement {

    /** Element types matching Lua API method names. */
    public static final int TEXT = 0;
    public static final int RECT = 1;
    public static final int BUTTON = 2;
    public static final int SPRITE = 3;
    public static final int ITEM = 4;

    public static final int NO_REF = 0;

    public final int id;
    public final int elementType;
    public final Map<String, Object> config;

    public Widget widget;
    public int clickRef = NO_REF;
    public final Map<Integer, Integer> actionRefs = new HashMap<>();

    public UiElement(final int id, final int elementType, final Map<String, Object> config) {
        this.id = id;
        this.elementType = elementType;
        this.config = config;
    }
}
