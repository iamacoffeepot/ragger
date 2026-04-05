package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.api.Point;
import net.runelite.api.widgets.InterfaceID;
import net.runelite.api.widgets.Widget;
import net.runelite.api.widgets.WidgetType;
import party.iroiro.luajava.Lua;

import java.awt.Rectangle;
import java.awt.Shape;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

/**
 * Lua binding for reading widget (interface) state.
 * Exposed as the global "widget" table in Lua scripts.
 *
 * Widgets are the UI elements drawn by the game client — bank interface,
 * inventory grid, dialog boxes, skill tab, prayer orbs, etc.
 */
@SuppressWarnings("deprecation") // widgets.InterfaceID has clean names; gameval has internal names
public class WidgetApi {

    private final Client client;

    public WidgetApi(final Client client) {
        this.client = client;
    }

    public void register(final Lua lua) {
        lua.createTable(0, 8);

        lua.push(this::get);
        lua.setField(-2, "get");

        lua.push(this::component);
        lua.setField(-2, "component");

        lua.push(this::roots);
        lua.setField(-2, "roots");

        lua.push(this::children);
        lua.setField(-2, "children");

        lua.push(this::text);
        lua.setField(-2, "text");

        // Register InterfaceID constants (BANK, INVENTORY, etc.)
        registerInterfaceConstants(lua);

        // Register WidgetType constants
        registerTypeConstants(lua);

        lua.setGlobal("widget");
    }

    /**
     * widget:get(groupId, childId) -> widget table or nil
     * Looks up a widget by interface group ID and child index.
     */
    private int get(final Lua lua) {
        final int groupId = (int) lua.toInteger(2);
        final int childId = (int) lua.toInteger(3);
        final Widget w = client.getWidget(groupId, childId);

        if (w == null || w.isHidden()) {
            lua.pushNil();
        } else {
            pushWidget(lua, w);
        }

        return 1;
    }

    /**
     * widget:component(componentId) -> widget table or nil
     * Looks up a widget by its packed component ID (groupId << 16 | childId).
     */
    private int component(final Lua lua) {
        final int componentId = (int) lua.toInteger(2);
        final Widget w = client.getWidget(componentId);

        if (w == null || w.isHidden()) {
            lua.pushNil();
        } else {
            pushWidget(lua, w);
        }

        return 1;
    }

    /**
     * widget:roots() -> array of widget tables
     * Returns all root widgets currently loaded.
     */
    private int roots(final Lua lua) {
        final Widget[] roots = client.getWidgetRoots();
        lua.createTable(roots != null ? roots.length : 0, 0);

        if (roots == null) {
            return 1;
        }

        int index = 1;
        for (final Widget w : roots) {
            if (w == null) {
                continue;
            }
            pushWidget(lua, w);
            lua.rawSetI(-2, index++);
        }

        return 1;
    }

    /**
     * widget:children(groupId, childId) -> array of widget tables
     * widget:children(componentId) -> array of widget tables
     * Returns all visible children of a widget.
     */
    private int children(final Lua lua) {
        final Widget parent;
        if (lua.getTop() >= 3) {
            final int groupId = (int) lua.toInteger(2);
            final int childId = (int) lua.toInteger(3);
            parent = client.getWidget(groupId, childId);
        } else {
            final int componentId = (int) lua.toInteger(2);
            parent = client.getWidget(componentId);
        }

        lua.createTable(0, 0);
        if (parent == null || parent.isHidden()) {
            return 1;
        }

        // Dynamic children first, then static, then nested
        int index = 1;
        index = pushChildArray(lua, parent.getDynamicChildren(), index);
        index = pushChildArray(lua, parent.getStaticChildren(), index);
        pushChildArray(lua, parent.getNestedChildren(), index);

        return 1;
    }

    /**
     * widget:text(groupId, childId) -> string or nil
     * widget:text(componentId) -> string or nil
     * Shortcut to get just the text content of a widget.
     */
    private int text(final Lua lua) {
        final Widget w;
        if (lua.getTop() >= 3) {
            final int groupId = (int) lua.toInteger(2);
            final int childId = (int) lua.toInteger(3);
            w = client.getWidget(groupId, childId);
        } else {
            final int componentId = (int) lua.toInteger(2);
            w = client.getWidget(componentId);
        }

        if (w == null || w.isHidden()) {
            lua.pushNil();
        } else {
            final String text = w.getText();
            if (text != null && !text.isEmpty()) {
                lua.push(text);
            } else {
                lua.pushNil();
            }
        }

        return 1;
    }

    /**
     * Push a widget as a Lua table with all readable properties.
     */
    private void pushWidget(final Lua lua, final Widget w) {
        lua.createTable(0, 16);

        // Identity
        lua.push(w.getId());
        lua.setField(-2, "id");

        lua.push(w.getType());
        lua.setField(-2, "type");

        lua.push(w.getContentType());
        lua.setField(-2, "content_type");

        lua.push(w.getIndex());
        lua.setField(-2, "index");

        lua.push(w.getParentId());
        lua.setField(-2, "parent_id");

        // Text
        final String text = w.getText();
        if (text != null && !text.isEmpty()) {
            lua.push(text);
            lua.setField(-2, "text");
        }

        // Name (op base — tooltip label like "Quick-prayers")
        final String name = w.getName();
        if (name != null && !name.isEmpty()) {
            lua.push(name);
            lua.setField(-2, "name");
        }

        // Visibility
        lua.push(w.isHidden());
        lua.setField(-2, "hidden");

        lua.push(w.isSelfHidden());
        lua.setField(-2, "self_hidden");

        // Item data (for item-displaying widgets)
        final int itemId = w.getItemId();
        if (itemId > 0) {
            lua.push(itemId);
            lua.setField(-2, "item_id");

            lua.push(w.getItemQuantity());
            lua.setField(-2, "item_quantity");
        }

        // Sprite
        final int spriteId = w.getSpriteId();
        if (spriteId > 0) {
            lua.push(spriteId);
            lua.setField(-2, "sprite_id");
        }

        // Model
        final int modelId = w.getModelId();
        if (modelId > 0) {
            lua.push(modelId);
            lua.setField(-2, "model_id");

            lua.push(w.getModelType());
            lua.setField(-2, "model_type");
        }

        // Dimensions & position
        lua.push(w.getWidth());
        lua.setField(-2, "width");

        lua.push(w.getHeight());
        lua.setField(-2, "height");

        lua.push(w.getRelativeX());
        lua.setField(-2, "x");

        lua.push(w.getRelativeY());
        lua.setField(-2, "y");

        // Canvas (absolute screen) position
        final Point canvasPos = w.getCanvasLocation();
        if (canvasPos != null) {
            lua.push(canvasPos.getX());
            lua.setField(-2, "canvas_x");

            lua.push(canvasPos.getY());
            lua.setField(-2, "canvas_y");
        }

        // Scroll state
        final int scrollX = w.getScrollX();
        final int scrollY = w.getScrollY();
        if (scrollX != 0 || scrollY != 0) {
            lua.push(scrollX);
            lua.setField(-2, "scroll_x");

            lua.push(scrollY);
            lua.setField(-2, "scroll_y");

            lua.push(w.getScrollWidth());
            lua.setField(-2, "scroll_width");

            lua.push(w.getScrollHeight());
            lua.setField(-2, "scroll_height");
        }

        // Text styling
        final int textColor = w.getTextColor();
        if (textColor != 0) {
            lua.push(textColor);
            lua.setField(-2, "text_color");
        }

        lua.push(w.getOpacity());
        lua.setField(-2, "opacity");

        // Actions
        final String[] actions = w.getActions();
        if (actions != null) {
            lua.createTable(actions.length, 0);
            int ai = 1;
            for (final String action : actions) {
                if (action != null) {
                    lua.push(action);
                    lua.rawSetI(-2, ai);
                }
                ai++;
            }
            lua.setField(-2, "actions");
        }
    }

    private int pushChildArray(final Lua lua, final Widget[] children, final int index) {
        if (children == null) {
            return index;
        }

        int idx = index;
        for (final Widget child : children) {
            if (child == null || child.isHidden()) {
                continue;
            }
            pushWidget(lua, child);
            lua.rawSetI(-2, idx++);
        }

        return idx;
    }

    /**
     * Register well-known InterfaceID constants as widget.BANK, widget.INVENTORY, etc.
     * Uses reflection on InterfaceID to pick up all constants.
     */
    private void registerInterfaceConstants(final Lua lua) {
        for (final Field field : InterfaceID.class.getDeclaredFields()) {
            final boolean isStaticFinal = Modifier.isStatic(field.getModifiers())
                    && Modifier.isFinal(field.getModifiers());

            if (isStaticFinal && field.getType() == int.class) {
                try {
                    lua.push(field.getInt(null));
                    lua.setField(-2, field.getName());
                } catch (final IllegalAccessException ignored) {
                }
            }
        }
    }

    /**
     * Register WidgetType constants as widget.TYPE_LAYER, widget.TYPE_TEXT, etc.
     */
    private void registerTypeConstants(final Lua lua) {
        lua.push(WidgetType.LAYER);
        lua.setField(-2, "TYPE_LAYER");

        lua.push(WidgetType.RECTANGLE);
        lua.setField(-2, "TYPE_RECTANGLE");

        lua.push(WidgetType.TEXT);
        lua.setField(-2, "TYPE_TEXT");

        lua.push(WidgetType.GRAPHIC);
        lua.setField(-2, "TYPE_GRAPHIC");

        lua.push(WidgetType.MODEL);
        lua.setField(-2, "TYPE_MODEL");

        lua.push(WidgetType.TEXT_INVENTORY);
        lua.setField(-2, "TYPE_TEXT_INVENTORY");

        lua.push(WidgetType.LINE);
        lua.setField(-2, "TYPE_LINE");
    }
}
