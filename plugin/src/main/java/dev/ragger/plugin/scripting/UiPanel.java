package dev.ragger.plugin.scripting;

import net.runelite.api.widgets.Widget;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Tracks a single HUD panel — a LAYER widget on the viewport container
 * with child widgets for background, title bar, and user elements.
 */
public final class UiPanel {

    public static final int TITLE_HEIGHT = 22;
    public static final int CLOSE_BTN_SIZE = 16;
    public static final int BG_COLOR = 0x2E2B25;
    public static final int BG_OPACITY = 200;
    public static final int TITLE_BG_COLOR = 0x3E3529;
    public static final int TITLE_TEXT_COLOR = 0xFF981F;
    public static final int DIVIDER_COLOR = 0xFF981F;
    public static final int CLOSE_COLOR = 0xFF0000;

    public final int id;
    public String title;
    public int x;
    public int y;
    public int width;
    public int height;
    public boolean closeable;
    public boolean draggable;
    public int closeCallbackRef = UiElement.NO_REF;

    // Drag offset (set when drag starts, used by UiApi.tickDrag)
    public int dragOffsetX;
    public int dragOffsetY;

    // Widget references (null before build or after viewport destroy)
    public Widget rootLayer;
    public Widget background;
    public Widget titleBg;
    public Widget titleText;
    public Widget closeBtn;
    public Widget divider;

    // Elements in insertion order for stable child indices
    public final Map<Integer, UiElement> elements = new LinkedHashMap<>();
    public int nextElementId = 1;

    public UiPanel(final int id, final String title, final int x, final int y,
                   final int width, final int height, final boolean closeable,
                   final boolean draggable) {
        this.id = id;
        this.title = title;
        this.x = x;
        this.y = y;
        this.width = width;
        this.height = height;
        this.closeable = closeable;
        this.draggable = draggable;
    }

    /**
     * Y offset for content elements (below title bar if present).
     */
    public int contentOffsetY() {
        return title != null ? TITLE_HEIGHT + 1 : 0;
    }

    /**
     * Get all elements as a list for iteration.
     */
    public List<UiElement> elementList() {
        return new ArrayList<>(elements.values());
    }
}
