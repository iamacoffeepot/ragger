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
local trail = {}
local ARRIVE_DIST = 5
local TRAIL_REFRESH = 10
local trail_tick = 0

local function clear()
    legs = {}
    leg_idx = 0
    requester = nil
    pending = false
    trail = {}
    trail_tick = 0
end

local function recompute_trail()
    trail = {}
    local leg = nil
    if leg_idx >= 1 and leg_idx <= #legs then
        leg = legs[leg_idx]
    end
    if not leg then return end
    local px = player:x()
    local py = player:y()
    local path = pathfinding:find_path_toward(px, py, leg.dst_x, leg.dst_y)
    if path then
        trail = path
    end
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
                question = "Run this Python code via Bash and mail the result back to svc/pathfinder:\n\n"
                    .. "```python\n"
                    .. "import sqlite3, json\n"
                    .. "from ragger.location import Location\n"
                    .. "from ragger.map import find_path\n"
                    .. "conn = sqlite3.connect('data/ragger.db')\n"
                    .. "nearest = Location.nearest(conn, " .. px .. ", " .. py .. ")\n"
                    .. "path = find_path(conn, nearest.name, '" .. data.destination .. "')\n"
                    .. "if path:\n"
                    .. "    legs = [{'dst_x': l.dst_x, 'dst_y': l.dst_y, 'type': l.link_type.name, "
                    .. "'instruction': l.description} for l in path]\n"
                    .. "    print(json.dumps(legs))\n"
                    .. "else:\n"
                    .. "    print('[]')\n"
                    .. "```\n\n"
                    .. "Then use MailSend to send to svc/pathfinder with:\n"
                    .. '{action="route", requester="' .. from .. '", legs=<the JSON array from above>}'
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
            recompute_trail()

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
            recompute_trail()
            trail_tick = 0
            return
        end
        trail_tick = trail_tick + 1
        if trail_tick >= TRAIL_REFRESH then
            recompute_trail()
            trail_tick = 0
        end
    end,

    on_render = function(g)
        local leg = current_leg()
        if not leg then return end

        -- find closest trail point to player and only render ahead of it
        local px = player:x()
        local py = player:y()
        local best_i = 1
        local best_dist = 999999
        for i, wp in ipairs(trail) do
            local d = math.max(math.abs(wp.x - px), math.abs(wp.y - py))
            if d < best_dist then
                best_dist = d
                best_i = i
            end
        end

        -- draw trail breadcrumbs from player onward
        for i = best_i, #trail do
            local wp = trail[i]
            local poly = coords:world_tile_poly(wp.x, wp.y)
            if poly and #poly >= 3 then
                g:fill_polygon(poly, 0x3000FF00)
            end
            -- minimap trail dots
            local mx, my = coords:world_to_minimap(wp.x, wp.y)
            if mx then
                g:fill_circle(mx, my, 2, 0x8000FF00)
            end
        end

        -- highlight destination tile
        local poly = coords:world_tile_poly(leg.dst_x, leg.dst_y)
        if poly and #poly >= 3 then
            g:fill_polygon(poly, 0x6000FF00)
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

        -- minimap destination dot
        local mx, my = coords:world_to_minimap(leg.dst_x, leg.dst_y)
        if mx then
            g:fill_circle(mx, my, 4, 0x00FF00)
        end
    end
}
