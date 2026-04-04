-- npc-highlighter: draw labels and outlines on NPCs by name
--
-- Mail API:
--   {action="add", name="Goblin", color=0xRRGGBB}
--   {action="remove", name="Goblin"}
--   {action="clear"}
--   {action="list"}  -> mails back {targets={{name,color},...}}

local targets = {}

return {
    on_mail = function(from, data)
        if data.action == "add" and data.name then
            targets[string.lower(data.name)] = {
                name = data.name,
                color = data.color or 0x00FF00
            }
        elseif data.action == "remove" and data.name then
            targets[string.lower(data.name)] = nil
        elseif data.action == "clear" then
            targets = {}
        elseif data.action == "list" then
            local list = {}
            local i = 1
            for _, t in pairs(targets) do
                list[i] = t
                i = i + 1
            end
            mail:send(from, { targets = list })
        end
    end,

    on_render = function(g)
        if not next(targets) then return end
        local npcs = scene:npcs()
        for i = 1, #npcs do
            local npc = npcs[i]
            local entry = targets[string.lower(npc.name)]
            if entry then
                local sx, sy = coords:world_to_canvas(npc.x, npc.y)
                if sx then
                    g:text(sx - 20, sy - 15, npc.name, entry.color)
                    g:rect(sx - 25, sy - 20, 50, 25, entry.color)
                end
            end
        end
    end
}
