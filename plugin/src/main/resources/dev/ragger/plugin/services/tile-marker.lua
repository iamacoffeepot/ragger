-- tile-marker: highlight world tiles with colored outlines and optional labels
--
-- Mail API:
--   {action="add", x=N, y=N, color=0xRRGGBB, label="text", label_color=0xRRGGBB}
--   {action="remove", x=N, y=N}
--   {action="clear"}
--   {action="list"}  -> mails back {tiles={{x,y,color,label,label_color},...}}

local tiles = {}

local function key(x, y) return x .. "," .. y end

return {
    on_mail = function(from, data)
        if data.action == "add" and data.x and data.y then
            tiles[key(data.x, data.y)] = {
                x = data.x, y = data.y,
                color = data.color or 0xFFFFFF,
                label = data.label,
                label_color = data.label_color
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
                if t.label then
                    local tx, ty = coords:world_text_pos(t.x, t.y, 150)
                    if tx then
                        g:text(tx, ty, t.label, t.label_color or t.color)
                    end
                end
            end
        end
    end
}
