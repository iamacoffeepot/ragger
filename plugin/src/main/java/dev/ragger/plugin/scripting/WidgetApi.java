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
        lua.createTable(0, 16);

        lua.push(this::get);
        lua.setField(-2, "get");

        lua.push(this::component);
        lua.setField(-2, "component");

        lua.push(this::roots);
        lua.setField(-2, "roots");

        lua.push(this::children);
        lua.setField(-2, "children");

        lua.push(this::parent);
        lua.setField(-2, "parent");

        lua.push(this::child);
        lua.setField(-2, "child");

        lua.push(this::descendants);
        lua.setField(-2, "descendants");

        lua.push(this::find);
        lua.setField(-2, "find");

        lua.push(this::text);
        lua.setField(-2, "text");

        lua.push(this::set_text);
        lua.setField(-2, "set_text");

        lua.push(this::set_width);
        lua.setField(-2, "set_width");

        lua.push(this::set_height);
        lua.setField(-2, "set_height");

        lua.push(this::set_scroll_height);
        lua.setField(-2, "set_scroll_height");

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
     * widget:parent(componentId) -> widget table or nil
     * widget:parent(groupId, childId) -> widget table or nil
     * Returns the parent widget, or nil if it's a root.
     */
    private int parent(final Lua lua) {
        final Widget w = resolveWidget(lua);
        if (w == null) {
            lua.pushNil();
            return 1;
        }

        final Widget p = w.getParent();
        if (p == null) {
            lua.pushNil();
        } else {
            pushWidget(lua, p);
        }

        return 1;
    }

    /**
     * widget:child(componentId, childIndex) -> widget table or nil
     * widget:child(groupId, childId, childIndex) -> widget table or nil
     * Returns a specific child by its widget index. Works for dynamic,
     * static, and nested children.
     */
    private int child(final Lua lua) {
        final int top = lua.getTop();
        final Widget parent;
        final int childIndex;
        if (top >= 4) {
            final int groupId = (int) lua.toInteger(2);
            final int childId = (int) lua.toInteger(3);
            parent = client.getWidget(groupId, childId);
            childIndex = (int) lua.toInteger(4);
        } else {
            final int componentId = (int) lua.toInteger(2);
            parent = client.getWidget(componentId);
            childIndex = (int) lua.toInteger(3);
        }

        if (parent == null) {
            lua.pushNil();
            return 1;
        }

        final Widget found = findChildByWidgetIndex(parent, childIndex);
        if (found == null || found.isHidden()) {
            lua.pushNil();
        } else {
            pushWidget(lua, found);
        }

        return 1;
    }

    /**
     * widget:descendants(componentId) -> array of widget tables
     * widget:descendants(groupId, childId) -> array of widget tables
     * Recursively collects all descendant widgets into a flat array.
     * Includes dynamic, static, and nested children at every level.
     */
    private int descendants(final Lua lua) {
        final Widget root = resolveWidget(lua);
        lua.createTable(0, 0);
        if (root == null || root.isHidden()) {
            return 1;
        }

        final int[] index = {1};
        collectDescendants(lua, root, index, 0);

        return 1;
    }

    private static final int MAX_DESCENDANT_DEPTH = 16;

    private void collectDescendants(final Lua lua, final Widget parent, final int[] index, final int depth) {
        if (depth > MAX_DESCENDANT_DEPTH) {
            return;
        }

        final Widget[][] groups = {
            parent.getDynamicChildren(),
            parent.getStaticChildren(),
            parent.getNestedChildren()
        };

        for (final Widget[] group : groups) {
            if (group == null) {
                continue;
            }
            for (final Widget child : group) {
                if (child == null || child.isHidden()) {
                    continue;
                }
                pushWidget(lua, child);
                lua.rawSetI(-2, index[0]++);
                collectDescendants(lua, child, index, depth + 1);
            }
        }
    }

    /**
     * widget:find(componentId, opts) -> array of widget tables
     * widget:find(groupId, childId, opts) -> array of widget tables
     * Searches descendants matching filter criteria. opts is a table:
     *   text     = "substring"   -- text contains (case-insensitive)
     *   name     = "substring"   -- name contains (case-insensitive)
     *   type     = 4             -- exact widget type match
     *   item_id  = 4151          -- exact item ID match
     *   has_text = true           -- has any non-empty text
     *   has_item = true           -- has any item (item_id > 0)
     *   has_action = "Withdraw"   -- has an action containing this string
     *   limit    = 10            -- max results (default unlimited)
     */
    private int find(final Lua lua) {
        final int top = lua.getTop();
        final Widget root;
        final int optsIdx;
        if (top >= 4) {
            final int groupId = (int) lua.toInteger(2);
            final int childId = (int) lua.toInteger(3);
            root = client.getWidget(groupId, childId);
            optsIdx = 4;
        } else {
            final int componentId = (int) lua.toInteger(2);
            root = client.getWidget(componentId);
            optsIdx = 3;
        }

        lua.createTable(0, 0);
        if (root == null || root.isHidden()) {
            return 1;
        }

        // Parse filter options
        String textFilter = null;
        String nameFilter = null;
        String actionFilter = null;
        int typeFilter = -1;
        int itemIdFilter = -1;
        boolean hasText = false;
        boolean hasItem = false;
        int limit = Integer.MAX_VALUE;

        if (lua.type(optsIdx) == Lua.LuaType.TABLE) {
            lua.getField(optsIdx, "text");
            if (lua.type(-1) == Lua.LuaType.STRING) {
                textFilter = lua.toString(-1).toLowerCase();
            }
            lua.pop(1);

            lua.getField(optsIdx, "name");
            if (lua.type(-1) == Lua.LuaType.STRING) {
                nameFilter = lua.toString(-1).toLowerCase();
            }
            lua.pop(1);

            lua.getField(optsIdx, "has_action");
            if (lua.type(-1) == Lua.LuaType.STRING) {
                actionFilter = lua.toString(-1).toLowerCase();
            }
            lua.pop(1);

            lua.getField(optsIdx, "type");
            if (lua.type(-1) == Lua.LuaType.NUMBER) {
                typeFilter = (int) lua.toInteger(-1);
            }
            lua.pop(1);

            lua.getField(optsIdx, "item_id");
            if (lua.type(-1) == Lua.LuaType.NUMBER) {
                itemIdFilter = (int) lua.toInteger(-1);
            }
            lua.pop(1);

            lua.getField(optsIdx, "has_text");
            if (lua.type(-1) == Lua.LuaType.BOOLEAN) {
                hasText = lua.toBoolean(-1);
            }
            lua.pop(1);

            lua.getField(optsIdx, "has_item");
            if (lua.type(-1) == Lua.LuaType.BOOLEAN) {
                hasItem = lua.toBoolean(-1);
            }
            lua.pop(1);

            lua.getField(optsIdx, "limit");
            if (lua.type(-1) == Lua.LuaType.NUMBER) {
                limit = (int) lua.toInteger(-1);
            }
            lua.pop(1);
        }

        final int[] index = {1};
        findDescendants(lua, root, textFilter, nameFilter, actionFilter,
                typeFilter, itemIdFilter, hasText, hasItem, limit, index, 0);

        return 1;
    }

    private void findDescendants(final Lua lua, final Widget parent,
            final String textFilter, final String nameFilter, final String actionFilter,
            final int typeFilter, final int itemIdFilter,
            final boolean hasText, final boolean hasItem,
            final int limit, final int[] index, final int depth) {
        if (depth > MAX_DESCENDANT_DEPTH || index[0] > limit) {
            return;
        }

        final Widget[][] groups = {
            parent.getDynamicChildren(),
            parent.getStaticChildren(),
            parent.getNestedChildren()
        };

        for (final Widget[] group : groups) {
            if (group == null) {
                continue;
            }
            for (final Widget child : group) {
                if (child == null || child.isHidden() || index[0] > limit) {
                    continue;
                }

                if (matchesFilters(child, textFilter, nameFilter, actionFilter,
                        typeFilter, itemIdFilter, hasText, hasItem)) {
                    pushWidget(lua, child);
                    lua.rawSetI(-2, index[0]++);
                }

                findDescendants(lua, child, textFilter, nameFilter, actionFilter,
                        typeFilter, itemIdFilter, hasText, hasItem, limit, index, depth + 1);
            }
        }
    }

    private boolean matchesFilters(final Widget w, final String textFilter,
            final String nameFilter, final String actionFilter,
            final int typeFilter, final int itemIdFilter,
            final boolean hasText, final boolean hasItem) {

        if (typeFilter >= 0 && w.getType() != typeFilter) {
            return false;
        }

        if (itemIdFilter >= 0 && w.getItemId() != itemIdFilter) {
            return false;
        }

        if (hasText) {
            final String t = w.getText();
            if (t == null || t.isEmpty()) {
                return false;
            }
        }

        if (hasItem && w.getItemId() <= 0) {
            return false;
        }

        if (textFilter != null) {
            final String t = w.getText();
            if (t == null || !t.toLowerCase().contains(textFilter)) {
                return false;
            }
        }

        if (nameFilter != null) {
            final String n = w.getName();
            if (n == null || !n.toLowerCase().contains(nameFilter)) {
                return false;
            }
        }

        if (actionFilter != null) {
            final String[] actions = w.getActions();
            if (actions == null) {
                return false;
            }
            boolean found = false;
            for (final String a : actions) {
                if (a != null && a.toLowerCase().contains(actionFilter)) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                return false;
            }
        }

        return true;
    }

    /**
     * Resolve a widget from Lua args — supports (componentId) or (groupId, childId).
     */
    private Widget resolveWidget(final Lua lua) {
        if (lua.getTop() >= 3 && lua.type(3) == Lua.LuaType.NUMBER) {
            final int groupId = (int) lua.toInteger(2);
            final int childId = (int) lua.toInteger(3);
            return client.getWidget(groupId, childId);
        }
        final int componentId = (int) lua.toInteger(2);
        return client.getWidget(componentId);
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
     * widget:set_text(groupId, childId, text)
     * widget:set_text(componentId, text)
     * widget:set_text(componentId, text, childIndex)
     * Sets the text content of a widget. When childIndex is provided,
     * addresses a dynamic/static/nested child by its merged index
     * (same ordering as widget:children()).
     */
    private int set_text(final Lua lua) {
        final int top = lua.getTop();

        if (top >= 4 && lua.type(4) != Lua.LuaType.NUMBER) {
            // widget:set_text(groupId, childId, text)
            final int groupId = (int) lua.toInteger(2);
            final int childId = (int) lua.toInteger(3);
            final Widget w = client.getWidget(groupId, childId);
            final String text = lua.toString(4);
            if (w != null && text != null) {
                w.setText(text);
                w.revalidate();
            }
        } else if (top >= 4) {
            // widget:set_text(componentId, text, childIndex)
            final int componentId = (int) lua.toInteger(2);
            final String text = lua.toString(3);
            final int childIndex = (int) lua.toInteger(4);
            final Widget parent = client.getWidget(componentId);
            if (parent != null && text != null) {
                final Widget child = findChildByWidgetIndex(parent, childIndex);
                if (child != null) {
                    child.setText(text);
                    child.revalidate();
                }
            }
        } else {
            // widget:set_text(componentId, text)
            final int componentId = (int) lua.toInteger(2);
            final Widget w = client.getWidget(componentId);
            final String text = lua.toString(3);
            if (w != null && text != null) {
                w.setText(text);
                w.revalidate();
            }
        }

        return 0;
    }

    /**
     * widget:set_width(componentId, width)
     * widget:set_width(componentId, width, childIndex)
     * Sets the original width of a widget and revalidates layout.
     */
    private int set_width(final Lua lua) {
        final int top = lua.getTop();

        if (top >= 4) {
            // widget:set_width(componentId, width, childIndex)
            final int componentId = (int) lua.toInteger(2);
            final int width = (int) lua.toInteger(3);
            final int childIndex = (int) lua.toInteger(4);
            final Widget parent = client.getWidget(componentId);
            if (parent != null) {
                final Widget child = findChildByWidgetIndex(parent, childIndex);
                if (child != null) {
                    child.setOriginalWidth(width);
                    child.revalidate();
                }
            }
        } else {
            // widget:set_width(componentId, width)
            final int componentId = (int) lua.toInteger(2);
            final int width = (int) lua.toInteger(3);
            final Widget w = client.getWidget(componentId);
            if (w != null) {
                w.setOriginalWidth(width);
                w.revalidate();
            }
        }

        return 0;
    }

    /**
     * widget:set_height(componentId, height)
     * widget:set_height(componentId, height, childIndex)
     * Sets the original height of a widget and revalidates layout.
     */
    private int set_height(final Lua lua) {
        final int top = lua.getTop();

        if (top >= 4) {
            // widget:set_height(componentId, height, childIndex)
            final int componentId = (int) lua.toInteger(2);
            final int height = (int) lua.toInteger(3);
            final int childIndex = (int) lua.toInteger(4);
            final Widget parent = client.getWidget(componentId);
            if (parent != null) {
                final Widget child = findChildByWidgetIndex(parent, childIndex);
                if (child != null) {
                    child.setOriginalHeight(height);
                    child.revalidate();
                }
            }
        } else {
            // widget:set_height(componentId, height)
            final int componentId = (int) lua.toInteger(2);
            final int height = (int) lua.toInteger(3);
            final Widget w = client.getWidget(componentId);
            if (w != null) {
                w.setOriginalHeight(height);
                w.revalidate();
            }
        }

        return 0;
    }

    /**
     * widget:set_scroll_height(componentId, height)
     * widget:set_scroll_height(componentId, height, childIndex)
     * Sets the scroll height of a scrollable widget and revalidates scroll.
     */
    private int set_scroll_height(final Lua lua) {
        final int top = lua.getTop();

        if (top >= 4) {
            // widget:set_scroll_height(componentId, height, childIndex)
            final int componentId = (int) lua.toInteger(2);
            final int height = (int) lua.toInteger(3);
            final int childIndex = (int) lua.toInteger(4);
            final Widget parent = client.getWidget(componentId);
            if (parent != null) {
                final Widget child = findChildByWidgetIndex(parent, childIndex);
                if (child != null) {
                    child.setScrollHeight(height);
                    child.revalidateScroll();
                }
            }
        } else {
            // widget:set_scroll_height(componentId, height)
            final int componentId = (int) lua.toInteger(2);
            final int height = (int) lua.toInteger(3);
            final Widget w = client.getWidget(componentId);
            if (w != null) {
                w.setScrollHeight(height);
                w.revalidateScroll();
            }
        }

        return 0;
    }

    /**
     * Find a child widget by its Widget.getIndex() value, searching
     * dynamic, static, and nested children (same order as widget:children()).
     */
    private Widget findChildByWidgetIndex(final Widget parent, final int targetIndex) {
        final Widget[][] groups = {
            parent.getDynamicChildren(),
            parent.getStaticChildren(),
            parent.getNestedChildren()
        };

        for (final Widget[] group : groups) {
            if (group == null) {
                continue;
            }
            for (final Widget child : group) {
                if (child != null && child.getIndex() == targetIndex) {
                    return child;
                }
            }
        }

        return null;
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

        // Child count (dynamic + static + nested, including hidden)
        int childCount = 0;
        final Widget[] dc = w.getDynamicChildren();
        final Widget[] sc = w.getStaticChildren();
        final Widget[] nc = w.getNestedChildren();
        if (dc != null) { childCount += dc.length; }
        if (sc != null) { childCount += sc.length; }
        if (nc != null) { childCount += nc.length; }
        if (childCount > 0) {
            lua.push(childCount);
            lua.setField(-2, "child_count");
        }

        // Text styling
        final int textColor = w.getTextColor();
        if (textColor != 0) {
            lua.push(textColor);
            lua.setField(-2, "text_color");
        }

        final int fontId = w.getFontId();
        if (fontId > 0) {
            lua.push(fontId);
            lua.setField(-2, "font_id");
        }

        if (w.getTextShadowed()) {
            lua.push(true);
            lua.setField(-2, "text_shadowed");
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
