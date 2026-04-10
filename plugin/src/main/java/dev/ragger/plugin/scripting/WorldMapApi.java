package dev.ragger.plugin.scripting;

import net.runelite.api.coords.WorldPoint;
import net.runelite.client.ui.overlay.worldmap.WorldMapPoint;
import net.runelite.client.ui.overlay.worldmap.WorldMapPointManager;
import party.iroiro.luajava.Lua;

import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/**
 * Lua binding for placing markers on the world map.
 * Exposed as the global "worldmap" table in Lua scripts.
 *
 * Markers are tracked per-actor and cleaned up automatically on actor stop.
 */
public class WorldMapApi {

    private static final int MARKER_SIZE = 10;

    private final WorldMapPointManager worldMapPointManager;
    private final List<WorldMapPoint> ownedPoints = new ArrayList<>();

    public WorldMapApi(final WorldMapPointManager worldMapPointManager) {
        this.worldMapPointManager = worldMapPointManager;
    }

    public void register(final Lua lua) {
        lua.createTable(0, 3);

        lua.push(this::add);
        lua.setField(-2, "add");

        lua.push(this::remove);
        lua.setField(-2, "remove");

        lua.push(this::clear);
        lua.setField(-2, "clear");

        lua.setGlobal("worldmap");
    }

    /**
     * worldmap:add(x, y, tooltip?, color?) -> nil
     * Places a marker at the given world coordinates.
     * Color is an optional RGB int (default red).
     */
    private int add(final Lua lua) {
        final int x = (int) lua.toInteger(2);
        final int y = (int) lua.toInteger(3);
        final String tooltip = lua.getTop() >= 4 && lua.isString(4) ? lua.toString(4) : null;
        final int rgb = lua.getTop() >= 5 ? (int) lua.toInteger(5) : 0xFF0000;

        final WorldPoint wp = new WorldPoint(x, y, 0);
        final BufferedImage icon = createMarkerIcon(new Color(rgb));
        final String name = tooltip != null ? tooltip : (x + "," + y);

        final WorldMapPoint point = new WorldMapPoint(wp, icon);
        point.setName(name);
        point.setTooltip(name);
        point.setSnapToEdge(true);
        point.setJumpOnClick(true);

        worldMapPointManager.add(point);
        ownedPoints.add(point);
        return 0;
    }

    /**
     * worldmap:remove(x, y) -> nil
     * Removes all markers at the given coordinates owned by this actor.
     */
    private int remove(final Lua lua) {
        final int x = (int) lua.toInteger(2);
        final int y = (int) lua.toInteger(3);

        final Iterator<WorldMapPoint> it = ownedPoints.iterator();
        while (it.hasNext()) {
            final WorldMapPoint point = it.next();
            final WorldPoint wp = point.getWorldPoint();
            if (wp.getX() == x && wp.getY() == y) {
                worldMapPointManager.remove(point);
                it.remove();
            }
        }

        return 0;
    }

    /**
     * worldmap:clear() -> nil
     * Removes all markers owned by this actor.
     */
    private int clear(final Lua lua) {
        destroy();
        return 0;
    }

    /**
     * Cleanup all owned markers. Called on actor stop.
     */
    public void destroy() {
        for (final WorldMapPoint point : ownedPoints) {
            worldMapPointManager.remove(point);
        }
        ownedPoints.clear();
    }

    private static BufferedImage createMarkerIcon(final Color color) {
        final BufferedImage img = new BufferedImage(MARKER_SIZE, MARKER_SIZE, BufferedImage.TYPE_INT_ARGB);
        final Graphics2D g = img.createGraphics();
        g.setColor(color);
        g.fillOval(0, 0, MARKER_SIZE, MARKER_SIZE);
        g.setColor(color.darker());
        g.drawOval(0, 0, MARKER_SIZE - 1, MARKER_SIZE - 1);
        g.dispose();
        return img;
    }
}
