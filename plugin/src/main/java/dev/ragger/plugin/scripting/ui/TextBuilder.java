package dev.ragger.plugin.scripting.ui;

import dev.ragger.plugin.scripting.LuaUtils;
import dev.ragger.plugin.scripting.UiElement;
import dev.ragger.plugin.scripting.UiPanel;
import net.runelite.api.widgets.Widget;
import net.runelite.api.widgets.WidgetSizeMode;
import net.runelite.api.widgets.WidgetTextAlignment;
import net.runelite.api.widgets.WidgetType;

import java.util.Map;

/**
 * Builds a TEXT widget element within a panel.
 */
public final class TextBuilder {

    public static final int FONT_SMALL = 494;
    public static final int FONT_LARGE = 495;

    private TextBuilder() {}

    public static void build(final UiPanel panel, final UiElement elem) {
        if (panel.rootLayer == null) {
            return;
        }

        final Map<String, Object> c = elem.config;
        final int ex = LuaUtils.intVal(c, "x", 0);
        final int ey = LuaUtils.intVal(c, "y", 0) + panel.contentOffsetY();
        final String text = LuaUtils.strVal(c, "text", "");
        final int color = LuaUtils.intVal(c, "color", 0xFFFFFF);
        final int fontSize = LuaUtils.intVal(c, "font_size", 0);

        final Widget w = panel.rootLayer.createChild(-1, WidgetType.TEXT);
        w.setOriginalX(ex);
        w.setOriginalY(ey);
        w.setOriginalWidth(panel.width - ex);
        w.setOriginalHeight(16);
        w.setWidthMode(WidgetSizeMode.ABSOLUTE);
        w.setHeightMode(WidgetSizeMode.ABSOLUTE);
        w.setText(text);
        w.setTextColor(color);
        w.setTextShadowed(true);
        w.setFontId(fontSize > 0 ? FONT_LARGE : FONT_SMALL);
        w.setYTextAlignment(WidgetTextAlignment.CENTER);
        w.revalidate();

        elem.widget = w;
    }
}
