package dev.ragger.plugin.scripting.ui;

import dev.ragger.plugin.scripting.LuaUtils;
import dev.ragger.plugin.scripting.UiElement;
import dev.ragger.plugin.scripting.UiPanel;
import net.runelite.api.widgets.Widget;
import net.runelite.api.widgets.WidgetSizeMode;
import net.runelite.api.widgets.WidgetType;

import java.util.Map;

/**
 * Builds a RECTANGLE widget element within a panel.
 */
public final class RectBuilder {

    private RectBuilder() {}

    public static void build(final UiPanel panel, final UiElement elem) {
        if (panel.rootLayer == null) {
            return;
        }

        final Map<String, Object> c = elem.config;
        final int ex = LuaUtils.intVal(c, "x", 0);
        final int ey = LuaUtils.intVal(c, "y", 0) + panel.contentOffsetY();
        final int ew = LuaUtils.intVal(c, "w", panel.width);
        final int eh = LuaUtils.intVal(c, "h", 1);
        final int color = LuaUtils.intVal(c, "color", 0x333333);
        final boolean filled = LuaUtils.boolVal(c, "filled", true);
        final int opacity = LuaUtils.intVal(c, "opacity", 0);

        final Widget w = panel.rootLayer.createChild(-1, WidgetType.RECTANGLE);
        w.setOriginalX(ex);
        w.setOriginalY(ey);
        w.setOriginalWidth(ew);
        w.setOriginalHeight(eh);
        w.setWidthMode(WidgetSizeMode.ABSOLUTE);
        w.setHeightMode(WidgetSizeMode.ABSOLUTE);
        w.setTextColor(color);
        w.setFilled(filled);
        w.setOpacity(opacity);
        w.revalidate();

        elem.widget = w;
    }
}
