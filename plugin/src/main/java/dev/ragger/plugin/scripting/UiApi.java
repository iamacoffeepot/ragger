package dev.ragger.plugin.scripting;

import dev.ragger.plugin.scripting.ui.ButtonBuilder;
import dev.ragger.plugin.scripting.ui.ItemBuilder;
import dev.ragger.plugin.scripting.ui.RectBuilder;
import dev.ragger.plugin.scripting.ui.SpriteBuilder;
import dev.ragger.plugin.scripting.ui.TextBuilder;
import net.runelite.api.Client;
import net.runelite.api.Point;
import net.runelite.api.gameval.InterfaceID;
import net.runelite.api.widgets.JavaScriptCallback;
import net.runelite.api.widgets.Widget;
import net.runelite.api.widgets.WidgetPositionMode;
import net.runelite.api.widgets.WidgetSizeMode;
import net.runelite.api.widgets.WidgetTextAlignment;
import net.runelite.api.widgets.WidgetType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import party.iroiro.luajava.JFunction;
import party.iroiro.luajava.Lua;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * Lua binding for creating native Jagex widget-based HUD interfaces.
 * Exposed as the global "ui" table in Lua scripts.
 *
 * Panels are LAYER widgets created as dynamic children of VIEWPORT_TRACKER_BACK.
 * Each panel has a background, optional title bar, and user-added elements
 * (text, rectangles, buttons, sprites, items).
 *
 * Click callbacks are stored as Lua registry references and invoked
 * during tick via drainClicks().
 */
public class UiApi {

    private static final Logger log = LoggerFactory.getLogger(UiApi.class);

    private final Client client;
    private Lua lua;

    private final Map<Integer, UiPanel> panels = new LinkedHashMap<>();
    private final ConcurrentLinkedQueue<ClickEvent> clickQueue = new ConcurrentLinkedQueue<>();
    private int nextPanelId = 1;
    private UiPanel draggingPanel;

    private record ClickEvent(int panelId, int elementId, int actionIndex) {}

    public UiApi(final Client client, final Lua lua) {
        this.client = client;
        this.lua = lua;
    }

    public void register(final Lua lua) {
        lua.createTable(0, 4);

        lua.push(this::create);
        lua.setField(-2, "create");

        lua.push(this::listPanels);
        lua.setField(-2, "list");

        lua.push(this::destroyPanel);
        lua.setField(-2, "destroy");

        lua.setGlobal("ui");
    }

    // -----------------------------------------------------------------------
    // Lua methods — ui:create(), ui:list(), ui:destroy()
    // -----------------------------------------------------------------------

    /**
     * ui:create(opts) -> panel table
     * opts: { title, x, y, width, height, closeable, on_close }
     */
    private int create(final Lua lua) {
        if (lua.type(2) != Lua.LuaType.TABLE) {
            lua.pushNil();
            return 1;
        }

        final int optsIndex = 2;

        final String title = LuaUtils.getStringField(lua, optsIndex, "title");
        final int x = LuaUtils.getIntField(lua, optsIndex, "x", 0);
        final int y = LuaUtils.getIntField(lua, optsIndex, "y", 0);
        final int width = LuaUtils.getIntField(lua, optsIndex, "width", 200);
        final int height = LuaUtils.getIntField(lua, optsIndex, "height", 150);
        final boolean closeable = LuaUtils.getBoolField(lua, optsIndex, "closeable", false);
        final boolean draggable = LuaUtils.getBoolField(lua, optsIndex, "draggable", false);

        final int panelId = nextPanelId++;
        final UiPanel panel = new UiPanel(panelId, title, x, y, width, height, closeable, draggable);

        // Store on_close callback ref if provided
        lua.getField(optsIndex, "on_close");
        if (lua.type(-1) == Lua.LuaType.FUNCTION) {
            panel.closeCallbackRef = lua.ref();
        } else {
            lua.pop(1);
        }

        panels.put(panelId, panel);

        // Build the native widgets for this panel only (appends to shared parent)
        buildPanel(panel);

        // Return a Lua table with panel methods (closures over panelId)
        pushPanelTable(lua, panelId);

        return 1;
    }

    /**
     * ui:list() -> array of panel IDs
     */
    private int listPanels(final Lua lua) {
        lua.createTable(panels.size(), 0);
        int i = 1;
        for (final int id : panels.keySet()) {
            lua.push(id);
            lua.rawSetI(-2, i++);
        }
        return 1;
    }

    /**
     * ui:destroy(panelId)
     */
    private int destroyPanel(final Lua lua) {
        final int panelId = (int) lua.toInteger(2);
        destroyPanelById(panelId);
        return 0;
    }

    // -----------------------------------------------------------------------
    // Panel methods — called from Lua panel table closures
    // -----------------------------------------------------------------------

    private int addText(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null || lua.type(2) != Lua.LuaType.TABLE) {
            lua.push(-1);
            return 1;
        }

        final int optsIndex = 2;
        final Map<String, Object> config = LuaUtils.tableToMap(lua, optsIndex);

        final int elemId = panel.nextElementId++;
        final UiElement elem = new UiElement(elemId, UiElement.TEXT, config);
        panel.elements.put(elemId, elem);

        TextBuilder.build(panel, elem);

        lua.push(elemId);
        return 1;
    }

    private int addRect(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null || lua.type(2) != Lua.LuaType.TABLE) {
            lua.push(-1);
            return 1;
        }

        final int optsIndex = 2;
        final Map<String, Object> config = LuaUtils.tableToMap(lua, optsIndex);

        final int elemId = panel.nextElementId++;
        final UiElement elem = new UiElement(elemId, UiElement.RECT, config);
        panel.elements.put(elemId, elem);

        RectBuilder.build(panel, elem);

        lua.push(elemId);
        return 1;
    }

    private int addButton(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null || lua.type(2) != Lua.LuaType.TABLE) {
            lua.push(-1);
            return 1;
        }

        final int optsIndex = 2;

        // Read config but handle callback refs manually before tableToMap
        // (tableToMap would stringify functions)
        final Map<String, Object> config = new LinkedHashMap<>();
        config.put("x", LuaUtils.getIntField(lua, optsIndex, "x", 0));
        config.put("y", LuaUtils.getIntField(lua, optsIndex, "y", 0));
        config.put("w", LuaUtils.getIntField(lua, optsIndex, "w", 80));
        config.put("h", LuaUtils.getIntField(lua, optsIndex, "h", 24));
        config.put("text", LuaUtils.getStringField(lua, optsIndex, "text"));
        config.put("color", LuaUtils.getIntField(lua, optsIndex, "color", 0xFFFFFF));

        final int elemId = panel.nextElementId++;
        final UiElement elem = new UiElement(elemId, UiElement.BUTTON, config);

        // Store on_click callback ref
        lua.getField(optsIndex, "on_click");
        if (lua.type(-1) == Lua.LuaType.FUNCTION) {
            elem.clickRef = lua.ref();
        } else {
            lua.pop(1);
        }

        // Store action callback refs
        lua.getField(optsIndex, "actions");
        if (lua.type(-1) == Lua.LuaType.TABLE) {
            final int actionsIndex = LuaUtils.abs(lua, -1);
            final int len = lua.rawLength(actionsIndex);
            final List<String> actionLabels = new ArrayList<>();

            for (int i = 1; i <= len; i++) {
                lua.rawGetI(actionsIndex, i);
                if (lua.type(-1) == Lua.LuaType.TABLE) {
                    final int actionIndex = LuaUtils.abs(lua, -1);

                    lua.getField(actionIndex, "label");
                    final String label = lua.type(-1) == Lua.LuaType.STRING
                            ? lua.toString(-1) : "Action " + i;
                    lua.pop(1);
                    actionLabels.add(label);

                    lua.getField(actionIndex, "on_click");
                    if (lua.type(-1) == Lua.LuaType.FUNCTION) {
                        // Action indices are 1-based in Lua, but widget ops start at 2
                        // (op 1 is reserved for left-click/on_click)
                        elem.actionRefs.put(i + 1, lua.ref());
                    } else {
                        lua.pop(1);
                    }
                }
                lua.pop(1); // pop action table
            }

            config.put("action_labels", actionLabels);
        }
        lua.pop(1); // pop actions field

        panel.elements.put(elemId, elem);

        ButtonBuilder.build(panel, elem, (pId, eId, op) -> clickQueue.add(new ClickEvent(pId, eId, op)));

        lua.push(elemId);
        return 1;
    }

    private int addSprite(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null || lua.type(2) != Lua.LuaType.TABLE) {
            lua.push(-1);
            return 1;
        }

        final Map<String, Object> config = LuaUtils.tableToMap(lua, 2);

        final int elemId = panel.nextElementId++;
        final UiElement elem = new UiElement(elemId, UiElement.SPRITE, config);
        panel.elements.put(elemId, elem);

        SpriteBuilder.build(panel, elem);

        lua.push(elemId);
        return 1;
    }

    private int addItem(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null || lua.type(2) != Lua.LuaType.TABLE) {
            lua.push(-1);
            return 1;
        }

        final Map<String, Object> config = LuaUtils.tableToMap(lua, 2);

        final int elemId = panel.nextElementId++;
        final UiElement elem = new UiElement(elemId, UiElement.ITEM, config);
        panel.elements.put(elemId, elem);

        ItemBuilder.build(panel, elem);

        lua.push(elemId);
        return 1;
    }

    /**
     * panel:set(elemId, opts) — update element properties.
     */
    private int setElement(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null) {
            return 0;
        }

        final int elemId = (int) lua.toInteger(2);
        final UiElement elem = panel.elements.get(elemId);
        if (elem == null || elem.widget == null) {
            return 0;
        }

        if (lua.type(3) != Lua.LuaType.TABLE) {
            return 0;
        }

        final int optsIndex = 3;

        // Update text
        lua.getField(optsIndex, "text");
        if (lua.type(-1) == Lua.LuaType.STRING) {
            final String text = lua.toString(-1);
            elem.widget.setText(text);
            elem.config.put("text", text);
        }
        lua.pop(1);

        // Update color
        lua.getField(optsIndex, "color");
        if (lua.type(-1) == Lua.LuaType.NUMBER) {
            final int color = (int) lua.toInteger(-1);
            elem.widget.setTextColor(color);
            elem.config.put("color", color);
        }
        lua.pop(1);

        // Update position
        lua.getField(optsIndex, "x");
        if (lua.type(-1) == Lua.LuaType.NUMBER) {
            final int ex = (int) lua.toInteger(-1);
            elem.widget.setOriginalX(ex);
            elem.config.put("x", ex);
        }
        lua.pop(1);

        lua.getField(optsIndex, "y");
        if (lua.type(-1) == Lua.LuaType.NUMBER) {
            final int ey = (int) lua.toInteger(-1) + panel.contentOffsetY();
            elem.widget.setOriginalY(ey);
            elem.config.put("y", (int) lua.toInteger(-1));
        }
        lua.pop(1);

        elem.widget.revalidate();
        return 0;
    }

    private int hideElement(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null) {
            return 0;
        }

        final int elemId = (int) lua.toInteger(2);
        final UiElement elem = panel.elements.get(elemId);
        if (elem != null && elem.widget != null) {
            elem.widget.setHidden(true);
            elem.widget.revalidate();
        }
        return 0;
    }

    private int showElement(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null) {
            return 0;
        }

        final int elemId = (int) lua.toInteger(2);
        final UiElement elem = panel.elements.get(elemId);
        if (elem != null && elem.widget != null) {
            elem.widget.setHidden(false);
            elem.widget.revalidate();
        }
        return 0;
    }

    private int removeElement(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null) {
            return 0;
        }

        final int elemId = (int) lua.toInteger(2);
        final UiElement elem = panel.elements.remove(elemId);
        if (elem != null) {
            unrefElement(elem);
            if (elem.widget != null) {
                elem.widget.setHidden(true);
                elem.widget.revalidate();
            }
        }
        return 0;
    }

    private int movePanel(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null) {
            return 0;
        }

        panel.x = (int) lua.toInteger(2);
        panel.y = (int) lua.toInteger(3);

        if (panel.rootLayer != null) {
            panel.rootLayer.setOriginalX(panel.x);
            panel.rootLayer.setOriginalY(panel.y);
            panel.rootLayer.revalidate();
        }
        return 0;
    }

    private int resizePanel(final Lua lua, final int panelId) {
        final UiPanel panel = panels.get(panelId);
        if (panel == null) {
            return 0;
        }

        panel.width = (int) lua.toInteger(2);
        panel.height = (int) lua.toInteger(3);

        // Rebuild the entire panel to resize background, title, etc.
        destroyPanelWidgets(panel);
        buildPanel(panel);
        for (final UiElement elem : panel.elementList()) {
            buildElementWidget(panel, elem);
        }
        return 0;
    }

    private int closePanel(final Lua lua, final int panelId) {
        destroyPanelById(panelId);
        return 0;
    }

    private int panelId(final Lua lua, final int panelId) {
        lua.push(panelId);
        return 1;
    }

    // -----------------------------------------------------------------------
    // Widget building
    // -----------------------------------------------------------------------

    /**
     * Parent widget candidates for HUD panels, in priority order.
     * VIEWPORT_TRACKER_BACK is a full-size overlay layer on top of the game viewport.
     * POPOUT is a narrow popup layer (fallback).
     */
    private static final int[] HUD_PARENT_CANDIDATES = {
        InterfaceID.ToplevelOsrsStretch.VIEWPORT_TRACKER_BACK,  // resizable modern
        InterfaceID.ToplevelOsrsStretch.POPOUT,
        InterfaceID.ToplevelPreEoc.VIEWPORT_TRACKER_BACK,       // resizable classic
        InterfaceID.ToplevelPreEoc.POPOUT,
        InterfaceID.Toplevel.POPOUT,                             // fixed mode (no tracker layer)
    };

    private static final int[] HUD_GROUP_IDS = {
        InterfaceID.TOPLEVEL_OSRS_STRETCH,
        InterfaceID.TOPLEVEL_PRE_EOC,
        InterfaceID.TOPLEVEL,
    };

    private Widget findHudParent() {
        // Try known viewport candidates — must be LAYER type for createChild
        for (final int id : HUD_PARENT_CANDIDATES) {
            final Widget w = client.getWidget(id);
            if (w != null && !w.isHidden() && w.getType() == WidgetType.LAYER) {
                return w;
            }
        }

        // Fallback: walk all roots and their direct children looking for a large LAYER
        final Widget[] roots = client.getWidgetRoots();
        if (roots == null) {
            return null;
        }

        Widget best = null;
        int bestArea = 0;

        for (final Widget root : roots) {
            if (root == null || root.isHidden()) {
                continue;
            }

            // Check root itself
            if (root.getType() == WidgetType.LAYER) {
                final int area = root.getWidth() * root.getHeight();
                if (area > bestArea) {
                    bestArea = area;
                    best = root;
                }
            }

            // Check static children (dynamic/nested less likely to be stable)
            final Widget[] children = root.getStaticChildren();
            if (children == null) {
                continue;
            }

            for (final Widget child : children) {
                if (child == null || child.isHidden() || child.getType() != WidgetType.LAYER) {
                    continue;
                }

                final int area = child.getWidth() * child.getHeight();
                if (area > bestArea) {
                    bestArea = area;
                    best = child;
                }
            }
        }

        if (best != null) {
            log.info("HUD parent fallback: id=0x{} ({}x{}, type={})",
                    Integer.toHexString(best.getId()), best.getWidth(), best.getHeight(),
                    best.getType());
        }

        return best;
    }

    private void buildPanel(final UiPanel panel) {
        final Widget parent = findHudParent();
        if (parent == null) {
            log.warn("No viewport parent found for panel {}", panel.id);
            return;
        }

        // Root LAYER (append to parent as dynamic child)
        final Widget root = parent.createChild(-1, WidgetType.LAYER);
        root.setOriginalX(panel.x);
        root.setOriginalY(panel.y);
        root.setOriginalWidth(panel.width);
        root.setOriginalHeight(panel.height);
        root.setXPositionMode(WidgetPositionMode.ABSOLUTE_LEFT);
        root.setYPositionMode(WidgetPositionMode.ABSOLUTE_TOP);
        root.setWidthMode(WidgetSizeMode.ABSOLUTE);
        root.setHeightMode(WidgetSizeMode.ABSOLUTE);
        root.setNoClickThrough(true);
        root.setNoScrollThrough(true);
        root.revalidate();
        panel.rootLayer = root;

        // Background rectangle
        final Widget bg = root.createChild(WidgetType.RECTANGLE);
        bg.setOriginalX(0);
        bg.setOriginalY(0);
        bg.setOriginalWidth(panel.width);
        bg.setOriginalHeight(panel.height);
        bg.setWidthMode(WidgetSizeMode.ABSOLUTE);
        bg.setHeightMode(WidgetSizeMode.ABSOLUTE);
        bg.setTextColor(UiPanel.BG_COLOR);
        bg.setFilled(true);
        bg.setOpacity(255 - UiPanel.BG_OPACITY);
        bg.revalidate();
        panel.background = bg;

        // Title bar
        if (panel.title != null) {
            // Title background
            final Widget titleBg = root.createChild(WidgetType.RECTANGLE);
            titleBg.setOriginalX(0);
            titleBg.setOriginalY(0);
            titleBg.setOriginalWidth(panel.width);
            titleBg.setOriginalHeight(UiPanel.TITLE_HEIGHT);
            titleBg.setWidthMode(WidgetSizeMode.ABSOLUTE);
            titleBg.setHeightMode(WidgetSizeMode.ABSOLUTE);
            titleBg.setTextColor(UiPanel.TITLE_BG_COLOR);
            titleBg.setFilled(true);
            titleBg.setOpacity(0);
            titleBg.revalidate();
            panel.titleBg = titleBg;

            // Start drag on mouse-down in title bar. Ongoing tracking and
            // release detection happen in tickDrag() every frame.
            if (panel.draggable) {
                titleBg.setOnMouseRepeatListener((JavaScriptCallback) ev -> {
                    if (draggingPanel == null && client.getMouseCurrentButton() == 1) {
                        final Point mouse = client.getMouseCanvasPosition();
                        panel.dragOffsetX = mouse.getX() - panel.x;
                        panel.dragOffsetY = mouse.getY() - panel.y;
                        draggingPanel = panel;
                    }
                });
                titleBg.setHasListener(true);
            }

            // Title text
            final Widget titleText = root.createChild(WidgetType.TEXT);
            titleText.setOriginalX(0);
            titleText.setOriginalY(2);
            titleText.setOriginalWidth(panel.width);
            titleText.setOriginalHeight(UiPanel.TITLE_HEIGHT);
            titleText.setWidthMode(WidgetSizeMode.ABSOLUTE);
            titleText.setHeightMode(WidgetSizeMode.ABSOLUTE);
            titleText.setText(panel.title);
            titleText.setTextColor(UiPanel.TITLE_TEXT_COLOR);
            titleText.setTextShadowed(true);
            titleText.setFontId(495);
            titleText.setXTextAlignment(WidgetTextAlignment.CENTER);
            titleText.setYTextAlignment(WidgetTextAlignment.CENTER);
            titleText.revalidate();
            panel.titleText = titleText;

            // Divider line
            final Widget div = root.createChild(WidgetType.RECTANGLE);
            div.setOriginalX(0);
            div.setOriginalY(UiPanel.TITLE_HEIGHT);
            div.setOriginalWidth(panel.width);
            div.setOriginalHeight(1);
            div.setWidthMode(WidgetSizeMode.ABSOLUTE);
            div.setHeightMode(WidgetSizeMode.ABSOLUTE);
            div.setTextColor(UiPanel.DIVIDER_COLOR);
            div.setFilled(true);
            div.setOpacity(0);
            div.revalidate();
            panel.divider = div;

            // Close button
            if (panel.closeable) {
                final Widget closeBtn = root.createChild(WidgetType.TEXT);
                closeBtn.setOriginalX(panel.width - UiPanel.CLOSE_BTN_SIZE - 2);
                closeBtn.setOriginalY(2);
                closeBtn.setOriginalWidth(UiPanel.CLOSE_BTN_SIZE);
                closeBtn.setOriginalHeight(UiPanel.CLOSE_BTN_SIZE);
                closeBtn.setWidthMode(WidgetSizeMode.ABSOLUTE);
                closeBtn.setHeightMode(WidgetSizeMode.ABSOLUTE);
                closeBtn.setText("X");
                closeBtn.setTextColor(UiPanel.CLOSE_COLOR);
                closeBtn.setTextShadowed(true);
                closeBtn.setFontId(495);
                closeBtn.setXTextAlignment(WidgetTextAlignment.CENTER);
                closeBtn.setYTextAlignment(WidgetTextAlignment.CENTER);
                closeBtn.setAction(0, "Close");
                closeBtn.setOnOpListener((JavaScriptCallback) ev -> {
                    // Queue close callback
                    if (panel.closeCallbackRef != UiElement.NO_REF) {
                        clickQueue.add(new ClickEvent(panel.id, -1, -1));
                    }
                    destroyPanelById(panel.id);
                });
                closeBtn.setHasListener(true);
                closeBtn.revalidate();
                panel.closeBtn = closeBtn;
            }
        }
    }

    private void buildElementWidget(final UiPanel panel, final UiElement elem) {
        switch (elem.elementType) {
            case UiElement.TEXT -> TextBuilder.build(panel, elem);
            case UiElement.RECT -> RectBuilder.build(panel, elem);
            case UiElement.BUTTON -> ButtonBuilder.build(panel, elem,
                    (pId, eId, op) -> clickQueue.add(new ClickEvent(pId, eId, op)));
            case UiElement.SPRITE -> SpriteBuilder.build(panel, elem);
            case UiElement.ITEM -> ItemBuilder.build(panel, elem);
        }
    }

    // -----------------------------------------------------------------------
    // Drag tracking
    // -----------------------------------------------------------------------

    /**
     * Update the actively dragged panel's position, or end the drag if the
     * mouse button was released. Called every frame from LuaActor.frame().
     */
    public void tickDrag() {
        if (draggingPanel == null) {
            return;
        }

        if (client.getMouseCurrentButton() != 1) {
            draggingPanel = null;
            return;
        }

        final Point mouse = client.getMouseCanvasPosition();
        int newX = mouse.getX() - draggingPanel.dragOffsetX;
        int newY = mouse.getY() - draggingPanel.dragOffsetY;

        // Clamp to parent bounds
        if (draggingPanel.rootLayer != null) {
            final Widget parent = draggingPanel.rootLayer.getParent();
            if (parent != null) {
                final int maxX = parent.getWidth() - draggingPanel.width;
                final int maxY = parent.getHeight() - draggingPanel.height;
                newX = Math.max(0, Math.min(newX, maxX));
                newY = Math.max(0, Math.min(newY, maxY));
            }

            draggingPanel.x = newX;
            draggingPanel.y = newY;
            draggingPanel.rootLayer.setOriginalX(newX);
            draggingPanel.rootLayer.setOriginalY(newY);
            draggingPanel.rootLayer.revalidate();
        }
    }

    // -----------------------------------------------------------------------
    // Click queue processing
    // -----------------------------------------------------------------------

    /**
     * Drain pending click events and invoke Lua callbacks.
     * Called from LuaActor.tick() before on_tick.
     */
    public void drainClicks() {
        ClickEvent event;
        while ((event = clickQueue.poll()) != null) {
            try {
                if (event.elementId() == -1) {
                    // Close button click
                    final UiPanel panel = panels.get(event.panelId());
                    if (panel != null && panel.closeCallbackRef != UiElement.NO_REF) {
                        lua.refGet(panel.closeCallbackRef);
                        lua.pCall(0, 0);
                    }
                    continue;
                }

                final UiPanel panel = panels.get(event.panelId());
                if (panel == null) {
                    continue;
                }

                final UiElement elem = panel.elements.get(event.elementId());
                if (elem == null) {
                    continue;
                }

                final int op = event.actionIndex();

                if (op == 1 && elem.clickRef != UiElement.NO_REF) {
                    // Left-click (op 1 = first action)
                    lua.refGet(elem.clickRef);
                    lua.pCall(0, 0);
                } else if (elem.actionRefs.containsKey(op)) {
                    // Right-click action
                    final int ref = elem.actionRefs.get(op);
                    lua.refGet(ref);
                    lua.pCall(0, 0);
                }
            } catch (final Exception e) {
                log.error("UI click callback error: {}", e.getMessage());
            }
        }
    }

    // -----------------------------------------------------------------------
    // Lifecycle and cleanup
    // -----------------------------------------------------------------------

    /**
     * Check if a widget group ID is a viewport interface and rebuild panels if so.
     * Called from LuaActor.deliverEvent() on widget_loaded events.
     */
    public void onViewportReloaded(final int groupId) {
        if (panels.isEmpty()) {
            return;
        }

        boolean isViewport = false;
        for (final int vgId : HUD_GROUP_IDS) {
            if (groupId == vgId) {
                isViewport = true;
                break;
            }
        }

        if (isViewport) {
            rebuildAll();
        }
    }

    /**
     * Rebuild all panels after viewport parent change (e.g. fixed/resizable switch).
     */
    public void rebuildAll() {
        // Destroy only this instance's panel root layers (not the entire parent)
        for (final UiPanel panel : panels.values()) {
            destroyPanelWidgets(panel);
        }

        // Rebuild all panels as new children of the parent
        for (final UiPanel panel : panels.values()) {
            buildPanel(panel);
            for (final UiElement elem : panel.elementList()) {
                buildElementWidget(panel, elem);
            }
        }
    }

    /**
     * Destroy all panels and unref all callbacks. Called on actor stop.
     */
    public void destroyAll() {
        for (final UiPanel panel : panels.values()) {
            destroyPanelWidgets(panel);
            unrefPanel(panel);
        }
        panels.clear();
        clickQueue.clear();
    }

    private void destroyPanelById(final int panelId) {
        final UiPanel panel = panels.remove(panelId);
        if (panel != null) {
            if (draggingPanel == panel) {
                draggingPanel = null;
            }
            destroyPanelWidgets(panel);
            unrefPanel(panel);
        }
    }

    private void destroyPanelWidgets(final UiPanel panel) {
        if (panel.rootLayer != null) {
            panel.rootLayer.deleteAllChildren();
            panel.rootLayer.setHidden(true);
            panel.rootLayer.revalidate();
            panel.rootLayer = null;
        }

        panel.background = null;
        panel.titleBg = null;
        panel.titleText = null;
        panel.closeBtn = null;
        panel.divider = null;

        for (final UiElement elem : panel.elements.values()) {
            elem.widget = null;
        }
    }

    private void unrefPanel(final UiPanel panel) {
        if (lua == null) {
            return;
        }

        if (panel.closeCallbackRef != UiElement.NO_REF) {
            lua.unref(panel.closeCallbackRef);
            panel.closeCallbackRef = UiElement.NO_REF;
        }

        for (final UiElement elem : panel.elements.values()) {
            unrefElement(elem);
        }
    }

    private void unrefElement(final UiElement elem) {
        if (lua == null) {
            return;
        }

        if (elem.clickRef != UiElement.NO_REF) {
            lua.unref(elem.clickRef);
            elem.clickRef = UiElement.NO_REF;
        }

        for (final int ref : elem.actionRefs.values()) {
            lua.unref(ref);
        }
        elem.actionRefs.clear();
    }

    // -----------------------------------------------------------------------
    // Lua panel table construction
    // -----------------------------------------------------------------------

    /**
     * Push a Lua table representing a panel with method closures.
     * Each method captures the panelId as an upvalue.
     */
    private void pushPanelTable(final Lua lua, final int panelId) {
        lua.createTable(0, 16);

        pushClosureMethod(lua, panelId, "text", this::addText);
        pushClosureMethod(lua, panelId, "rect", this::addRect);
        pushClosureMethod(lua, panelId, "button", this::addButton);
        pushClosureMethod(lua, panelId, "sprite", this::addSprite);
        pushClosureMethod(lua, panelId, "item", this::addItem);
        pushClosureMethod(lua, panelId, "set", this::setElement);
        pushClosureMethod(lua, panelId, "hide", this::hideElement);
        pushClosureMethod(lua, panelId, "show", this::showElement);
        pushClosureMethod(lua, panelId, "remove", this::removeElement);
        pushClosureMethod(lua, panelId, "move", this::movePanel);
        pushClosureMethod(lua, panelId, "resize", this::resizePanel);
        pushClosureMethod(lua, panelId, "close", this::closePanel);
        pushClosureMethod(lua, panelId, "id", this::panelId);
    }

    private interface PanelMethod {
        int call(Lua lua, int panelId);
    }

    private void pushClosureMethod(final Lua lua, final int panelId,
                                   final String name, final PanelMethod method) {
        lua.push((JFunction) l -> method.call(l, panelId));
        lua.setField(-2, name);
    }

    // -----------------------------------------------------------------------
    // Helpers for reading opts tables
    // -----------------------------------------------------------------------

}
