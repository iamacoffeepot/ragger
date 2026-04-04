-- loot-tracker: track personal ground item drops and accumulate value
--
-- Mail API:
--   {action="start"}    -- begin tracking
--   {action="stop"}     -- stop tracking
--   {action="report"}   -> mails back {loot={{name,qty,value},...}, total=N}
--   {action="reset"}    -- clear accumulated loot

local tracking = false
local loot = {}
local seen = {}

local function item_key(id, x, y) return id .. ":" .. x .. ":" .. y end

return {
    on_mail = function(from, data)
        if data.action == "start" then
            tracking = true
            chat:game("[Loot] Tracking started.")
        elseif data.action == "stop" then
            tracking = false
            chat:game("[Loot] Tracking stopped.")
        elseif data.action == "report" then
            local list = {}
            local total = 0
            local i = 1
            for _, entry in pairs(loot) do
                list[i] = entry
                total = total + entry.value
                i = i + 1
            end
            mail:send(from, { loot = list, total = total })
        elseif data.action == "reset" then
            loot = {}
            seen = {}
            chat:game("[Loot] Reset.")
        end
    end,

    on_tick = function()
        if not tracking then return end
        local ground = scene:ground_items()
        for i = 1, #ground do
            local gi = ground[i]
            local k = item_key(gi.id, gi.x, gi.y)
            if gi.ownership == 1 and not seen[k] then
                seen[k] = true
                local name = items:name(gi.id) or ("Item " .. gi.id)
                local price = items:grand_exchange_price(gi.id) or 0
                local total_val = price * gi.quantity
                if loot[gi.id] then
                    loot[gi.id].qty = loot[gi.id].qty + gi.quantity
                    loot[gi.id].value = loot[gi.id].value + total_val
                else
                    loot[gi.id] = { name = name, qty = gi.quantity, value = total_val }
                end
            end
        end
    end,

    on_render = function(g)
        if not tracking then return end
        g:font("Arial", 11)
        g:text(10, 60, "[Loot Tracking]", 0x00FF88)
    end
}
