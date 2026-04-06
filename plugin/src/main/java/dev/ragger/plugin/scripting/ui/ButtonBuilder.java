package dev.ragger.plugin.scripting.ui;

import dev.ragger.plugin.scripting.LuaUtils;
import dev.ragger.plugin.scripting.UiElement;
import dev.ragger.plugin.scripting.UiPanel;
import net.runelite.api.widgets.JavaScriptCallback;
import net.runelite.api.widgets.Widget;
import net.runelite.api.widgets.WidgetSizeMode;
import net.runelite.api.widgets.WidgetTextAlignment;
import net.runelite.api.widgets.WidgetType;

import java.util.List;
import java.util.Map;

/**
 * Builds a BUTTON widget element (background rect + clickable text) within a panel.
 */
public final class ButtonBuilder {

    public static final int BG_COLOR = 0x3E3529;
    public static final int FONT_ID = 494;

    private ButtonBuilder() {}

    /**
     * @param panel   the parent panel
     * @param elem    the element (must have clickRef/actionRefs already set)
     * @param onClick callback invoked with (panelId, elementId, opIndex) on click
     */
    @SuppressWarnings("unchecked")
    public static void build(final UiPanel panel, final UiElement elem,
                             final ClickCallback onClick) {
        if (panel.rootLayer == null) {
            return;
        }

        final Map<String, Object> c = elem.config;
        final int ex = LuaUtils.intVal(c, "x", 0);
        final int ey = LuaUtils.intVal(c, "y", 0) + panel.contentOffsetY();
        final int ew = LuaUtils.intVal(c, "w", 80);
        final int eh = LuaUtils.intVal(c, "h", 24);
        final String text = LuaUtils.strVal(c, "text", "Button");
        final int color = LuaUtils.intVal(c, "color", 0xFFFFFF);

        // Button background
        final Widget bg = panel.rootLayer.createChild(-1, WidgetType.RECTANGLE);
        bg.setOriginalX(ex);
        bg.setOriginalY(ey);
        bg.setOriginalWidth(ew);
        bg.setOriginalHeight(eh);
        bg.setWidthMode(WidgetSizeMode.ABSOLUTE);
        bg.setHeightMode(WidgetSizeMode.ABSOLUTE);
        bg.setTextColor(BG_COLOR);
        bg.setFilled(true);
        bg.setOpacity(0);
        bg.revalidate();

        // Button text (this is the clickable widget)
        final Widget w = panel.rootLayer.createChild(-1, WidgetType.TEXT);
        w.setOriginalX(ex);
        w.setOriginalY(ey);
        w.setOriginalWidth(ew);
        w.setOriginalHeight(eh);
        w.setWidthMode(WidgetSizeMode.ABSOLUTE);
        w.setHeightMode(WidgetSizeMode.ABSOLUTE);
        w.setText(text);
        w.setTextColor(color);
        w.setTextShadowed(true);
        w.setFontId(FONT_ID);
        w.setXTextAlignment(WidgetTextAlignment.CENTER);
        w.setYTextAlignment(WidgetTextAlignment.CENTER);

        // Set up actions
        final int pId = panel.id;
        final int eId = elem.id;

        if (elem.clickRef != UiElement.NO_REF) {
            w.setAction(0, text);
        }

        final Object actionLabelsObj = c.get("action_labels");
        if (actionLabelsObj instanceof List<?> actionLabels) {
            for (int i = 0; i < actionLabels.size(); i++) {
                w.setAction(i + 1, (String) actionLabels.get(i));
            }
        }

        w.setOnOpListener((JavaScriptCallback) ev -> onClick.onClick(pId, eId, ev.getOp()));
        w.setHasListener(true);
        w.revalidate();

        elem.widget = w;
    }

    @FunctionalInterface
    public interface ClickCallback {
        void onClick(int panelId, int elementId, int opIndex);
    }
}
