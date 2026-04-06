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
final class UiPanel {

    static final int TITLE_HEIGHT = 22;
    static final int CLOSE_BTN_SIZE = 16;
    static final int BG_COLOR = 0x2E2B25;
    static final int BG_OPACITY = 200;
    static final int TITLE_BG_COLOR = 0x3E3529;
    static final int TITLE_TEXT_COLOR = 0xFF981F;
    static final int DIVIDER_COLOR = 0xFF981F;
    static final int CLOSE_COLOR = 0xFF0000;

    final int id;
    String title;
    int x;
    int y;
    int width;
    int height;
    boolean closeable;
    boolean draggable;
    int closeCallbackRef = UiElement.NO_REF;

    // Drag offset (set when drag starts, used by UiApi.tickDrag)
    int dragOffsetX;
    int dragOffsetY;

    // Widget references (null before build or after viewport destroy)
    Widget rootLayer;
    Widget background;
    Widget titleBg;
    Widget titleText;
    Widget closeBtn;
    Widget divider;

    // Elements in insertion order for stable child indices
    final Map<Integer, UiElement> elements = new LinkedHashMap<>();
    int nextElementId = 1;

    UiPanel(final int id, final String title, final int x, final int y,
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
    int contentOffsetY() {
        return title != null ? TITLE_HEIGHT + 1 : 0;
    }

    /**
     * Get all elements as a list for iteration.
     */
    List<UiElement> elementList() {
        return new ArrayList<>(elements.values());
    }
}
