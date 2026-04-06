package dev.ragger.plugin.scripting.ui;

import dev.ragger.plugin.scripting.LuaUtils;
import dev.ragger.plugin.scripting.UiElement;
import dev.ragger.plugin.scripting.UiPanel;
import net.runelite.api.widgets.Widget;
import net.runelite.api.widgets.WidgetSizeMode;
import net.runelite.api.widgets.WidgetType;

import java.util.Map;

/**
 * Builds an ITEM (GRAPHIC with item ID/quantity) widget element within a panel.
 */
public final class ItemBuilder {

    private ItemBuilder() {}

    public static void build(final UiPanel panel, final UiElement elem) {
        if (panel.rootLayer == null) {
            return;
        }

        final Map<String, Object> c = elem.config;
        final int ex = LuaUtils.intVal(c, "x", 0);
        final int ey = LuaUtils.intVal(c, "y", 0) + panel.contentOffsetY();
        final int ew = LuaUtils.intVal(c, "w", 36);
        final int eh = LuaUtils.intVal(c, "h", 32);
        final int itemId = LuaUtils.intVal(c, "item_id", 0);
        final int quantity = LuaUtils.intVal(c, "quantity", 1);

        final Widget w = panel.rootLayer.createChild(-1, WidgetType.GRAPHIC);
        w.setOriginalX(ex);
        w.setOriginalY(ey);
        w.setOriginalWidth(ew);
        w.setOriginalHeight(eh);
        w.setWidthMode(WidgetSizeMode.ABSOLUTE);
        w.setHeightMode(WidgetSizeMode.ABSOLUTE);
        w.setItemId(itemId);
        w.setItemQuantity(quantity);
        w.revalidate();

        elem.widget = w;
    }
}
