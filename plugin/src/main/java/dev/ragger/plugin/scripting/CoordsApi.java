package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.api.Perspective;
import net.runelite.api.Point;
import net.runelite.api.coords.LocalPoint;
import net.runelite.api.coords.WorldPoint;
import party.iroiro.luajava.Lua;

import java.awt.*;

/**
 * Lua binding for coordinate system conversions.
 * Exposed as the global "coords" table in Lua scripts.
 *
 * Coordinate systems:
 * - world: absolute game tile coordinates
 * - local: tile offset within loaded 104x104 scene (0-103)
 * - canvas: screen pixel coordinates
 */
public class CoordsApi {

    private final Client client;

    public CoordsApi(Client client) {
        this.client = client;
    }

    public void register(Lua lua) {
        lua.createTable(0, 5);

        lua.push(this::world_to_canvas);
        lua.setField(-2, "world_to_canvas");

        lua.push(this::local_to_canvas);
        lua.setField(-2, "local_to_canvas");

        lua.push(this::world_to_local);
        lua.setField(-2, "world_to_local");

        lua.push(this::world_to_minimap);
        lua.setField(-2, "world_to_minimap");

        lua.push(this::world_tile_poly);
        lua.setField(-2, "world_tile_poly");

        lua.setGlobal("coords");
    }

    /**
     * coords:world_to_canvas(worldX, worldY) -> x, y or nil
     */
    private int world_to_canvas(Lua lua) {
        int worldX = (int) lua.toInteger(2);
        int worldY = (int) lua.toInteger(3);

        LocalPoint lp = LocalPoint.fromWorld(client, worldX, worldY);
        if (lp == null) {
            lua.pushNil();
            return 1;
        }

        Point canvas = Perspective.localToCanvas(client, lp, client.getPlane());
        if (canvas == null) {
            lua.pushNil();
            return 1;
        }

        lua.push(canvas.getX());
        lua.push(canvas.getY());
        return 2;
    }

    /**
     * coords:local_to_canvas(localTileX, localTileY) -> x, y or nil
     */
    private int local_to_canvas(Lua lua) {
        int tileX = (int) lua.toInteger(2);
        int tileY = (int) lua.toInteger(3);

        LocalPoint lp = LocalPoint.fromScene(tileX, tileY);
        Point canvas = Perspective.localToCanvas(client, lp, client.getPlane());
        if (canvas == null) {
            lua.pushNil();
            return 1;
        }

        lua.push(canvas.getX());
        lua.push(canvas.getY());
        return 2;
    }

    /**
     * coords:world_to_local(worldX, worldY) -> localTileX, localTileY or nil
     */
    private int world_to_local(Lua lua) {
        int worldX = (int) lua.toInteger(2);
        int worldY = (int) lua.toInteger(3);

        LocalPoint lp = LocalPoint.fromWorld(client, worldX, worldY);
        if (lp == null) {
            lua.pushNil();
            return 1;
        }

        lua.push(lp.getSceneX());
        lua.push(lp.getSceneY());
        return 2;
    }

    /**
     * coords:world_to_minimap(worldX, worldY) -> x, y or nil
     */
    private int world_to_minimap(Lua lua) {
        int worldX = (int) lua.toInteger(2);
        int worldY = (int) lua.toInteger(3);

        LocalPoint lp = LocalPoint.fromWorld(client, worldX, worldY);
        if (lp == null) {
            lua.pushNil();
            return 1;
        }

        Point minimap = Perspective.localToMinimap(client, lp);
        if (minimap == null) {
            lua.pushNil();
            return 1;
        }

        lua.push(minimap.getX());
        lua.push(minimap.getY());
        return 2;
    }

    /**
     * coords:world_tile_poly(worldX, worldY) -> array of {x, y} points or nil
     */
    private int world_tile_poly(Lua lua) {
        int worldX = (int) lua.toInteger(2);
        int worldY = (int) lua.toInteger(3);

        LocalPoint lp = LocalPoint.fromWorld(client, worldX, worldY);
        if (lp == null) {
            lua.pushNil();
            return 1;
        }

        Polygon poly = Perspective.getCanvasTilePoly(client, lp);
        if (poly == null) {
            lua.pushNil();
            return 1;
        }

        lua.createTable(poly.npoints, 0);
        for (int i = 0; i < poly.npoints; i++) {
            lua.createTable(0, 2);
            lua.push(poly.xpoints[i]);
            lua.setField(-2, "x");
            lua.push(poly.ypoints[i]);
            lua.setField(-2, "y");
            lua.rawSetI(-2, i + 1);
        }

        return 1;
    }
}
