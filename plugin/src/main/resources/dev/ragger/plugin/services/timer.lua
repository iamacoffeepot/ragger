-- timer: named countdown timers with on-screen display
--
-- Mail API:
--   {action="set", seconds=N, label="text"}
--   {action="cancel", label="text"}
--   {action="clear"}
-- Mails back {event="done", label="text"} to sender when timer expires.

local timers = {}
local tick_count = 0

return {
    on_mail = function(from, data)
        if data.action == "set" and data.seconds and data.label then
            local expire_tick = tick_count + math.ceil(data.seconds / 0.6)
            timers[data.label] = {
                label = data.label,
                expire = expire_tick,
                from = from
            }
        elseif data.action == "cancel" and data.label then
            timers[data.label] = nil
        elseif data.action == "clear" then
            timers = {}
        end
    end,

    on_tick = function()
        tick_count = tick_count + 1
        local expired = {}
        for label, t in pairs(timers) do
            if tick_count >= t.expire then
                chat:game("[Timer] " .. t.label .. " done!")
                mail:send(t.from, { event = "done", label = t.label })
                expired[#expired + 1] = label
            end
        end
        for _, label in ipairs(expired) do
            timers[label] = nil
        end
    end,

    on_render = function(g)
        if not next(timers) then return end
        local y = 80
        g:font("Arial", "bold", 12)
        for label, t in pairs(timers) do
            local remaining = math.max(0, math.ceil((t.expire - tick_count) * 0.6))
            local mins = math.floor(remaining / 60)
            local secs = remaining % 60
            local text = t.label .. ": " .. mins .. ":" .. string.format("%02d", secs)
            g:text(10, y, text, 0xFFFF00)
            y = y + 18
        end
    end
}
