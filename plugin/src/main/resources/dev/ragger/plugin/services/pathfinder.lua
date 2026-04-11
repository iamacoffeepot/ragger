-- pathfinder: cross-region navigation with waypoint rendering
--
-- Mail API:
--   {action="navigate", destination="Place Name"}
--     -> asks claude:agent to compute a route from the player's current
--        position, then renders waypoints as the player walks
--   {action="route", requester="actor", legs={{dst_x, dst_y, type, instruction}, ...}}
--     -> received from claude:agent with the computed route
--   {action="stop"}
--     -> clears the current route
--   {action="status"}
--     -> mails back {active=bool, leg=N, total=N, instruction="..."}

local legs = {}
local leg_idx = 0
local requester = nil
local pending = false
local ARRIVE_DIST = 5

local function clear()
    legs = {}
    leg_idx = 0
    requester = nil
    pending = false
end

local function current_leg()
    if leg_idx >= 1 and leg_idx <= #legs then
        return legs[leg_idx]
    end
    return nil
end

local function advance()
    leg_idx = leg_idx + 1
    if leg_idx > #legs then
        chat:game("[pathfinder] Arrived at destination.")
        if requester then
            mail:send(requester, { event = "arrived" })
        end
        clear()
    else
        local leg = current_leg()
        if leg and leg.instruction then
            chat:game("[pathfinder] " .. leg.instruction)
        end
    end
end

return {
    on_mail = function(from, data)
        if data.action == "navigate" and data.destination then
            clear()
            pending = true
            requester = from
            local px = player:x()
            local py = player:y()
            mail:send("claude:agent", {
                question = "Find a path from coordinates ("
                    .. px .. ", " .. py
                    .. ") to " .. data.destination
                    .. ". Reply by mailing svc/pathfinder with: "
                    .. "{action=\"route\", requester=\"" .. from .. "\", "
                    .. "legs={{dst_x=N, dst_y=N, type=\"TYPE\", instruction=\"text\"}, ...}}. "
                    .. "Each leg needs dst_x, dst_y (the tile to walk/teleport to), "
                    .. "type (WALKABLE, TELEPORT, FAIRY_RING, ENTRANCE, EXIT, CHARTER_SHIP, QUETZAL, or SPIRIT_TREE), "
                    .. "and instruction (what the player should do). "
                    .. "Use the Python find_path API to compute the route."
            })
            chat:game("[pathfinder] Computing route to " .. data.destination .. "...")

        elseif data.action == "route" and data.legs then
            legs = data.legs
            leg_idx = 1
            pending = false
            if data.requester then
                requester = data.requester
            end
            chat:game("[pathfinder] Route loaded: " .. #legs .. " legs.")
            local leg = current_leg()
            if leg and leg.instruction then
                chat:game("[pathfinder] " .. leg.instruction)
            end

        elseif data.action == "stop" then
            clear()
            chat:game("[pathfinder] Navigation stopped.")

        elseif data.action == "status" then
            local leg = current_leg()
            mail:send(from, {
                active = leg_idx >= 1,
                pending = pending,
                leg = leg_idx,
                total = #legs,
                instruction = leg and leg.instruction or nil
            })
        end
    end,

    on_tick = function()
        local leg = current_leg()
        if not leg then return end
        local px = player:x()
        local py = player:y()
        local dx = math.abs(px - leg.dst_x)
        local dy = math.abs(py - leg.dst_y)
        if math.max(dx, dy) <= ARRIVE_DIST then
            advance()
        end
    end,

    on_render = function(g)
        local leg = current_leg()
        if not leg then return end

        -- highlight destination tile
        local poly = coords:world_tile_poly(leg.dst_x, leg.dst_y)
        if poly and #poly >= 3 then
            g:fill_polygon(poly, 0x4000FF00)
            for j = 1, #poly do
                local nxt = j < #poly and j + 1 or 1
                g:line(poly[j].x, poly[j].y, poly[nxt].x, poly[nxt].y, 0x00FF00)
            end
        end

        -- label above tile
        local tx, ty = coords:world_text_pos(leg.dst_x, leg.dst_y, 200)
        if tx then
            g:font("Arial", "bold", 12)
            if leg.instruction then
                g:text(tx, ty, leg.instruction, 0x00FF00)
            end
            g:text(tx, ty + 14, "Leg " .. leg_idx .. "/" .. #legs, 0xFFFF00)
        end

        -- minimap dot
        local mx, my = coords:world_to_minimap(leg.dst_x, leg.dst_y)
        if mx then
            g:fill_circle(mx, my, 4, 0x00FF00)
        end
    end
}
