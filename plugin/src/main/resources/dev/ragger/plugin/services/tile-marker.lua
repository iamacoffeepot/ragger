-- tile-marker: highlight world tiles with colored outlines
--
-- Mail API:
--   {action="add", x=N, y=N, color=0xRRGGBB}
--   {action="remove", x=N, y=N}
--   {action="clear"}
--   {action="list"}  -> mails back {tiles={{x,y,color},...}}

local tiles = {}

local function key(x, y) return x .. "," .. y end

return {
    on_mail = function(from, data)
        if data.action == "add" and data.x and data.y then
            tiles[key(data.x, data.y)] = {
                x = data.x, y = data.y,
                color = data.color or 0xFFFFFF
            }
        elseif data.action == "remove" and data.x and data.y then
            tiles[key(data.x, data.y)] = nil
        elseif data.action == "clear" then
            tiles = {}
        elseif data.action == "list" then
            local list = {}
            local i = 1
            for _, t in pairs(tiles) do
                list[i] = t
                i = i + 1
            end
            mail:send(from, { tiles = list })
        end
    end,

    on_render = function(g)
        for _, t in pairs(tiles) do
            local poly = coords:world_tile_poly(t.x, t.y)
            if poly and #poly >= 3 then
                for j = 1, #poly do
                    local nxt = j < #poly and j + 1 or 1
                    g:line(poly[j].x, poly[j].y, poly[nxt].x, poly[nxt].y, t.color)
                end
            end
        end
    end
}
