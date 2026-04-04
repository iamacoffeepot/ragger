-- stat-monitor: track XP gains and display on screen
--
-- Mail API:
--   {action="watch", skill="mining"}
--   {action="unwatch", skill="mining"}
--   {action="clear"}
--   {action="report"}  -> mails back {gains={{skill,start_xp,current_xp,gained},...}}

local skill_ids = {
    attack=0, defence=1, strength=2, hitpoints=3, ranged=4,
    prayer=5, magic=6, cooking=7, woodcutting=8, fletching=9,
    fishing=10, firemaking=11, crafting=12, smithing=13, mining=14,
    herblore=15, agility=16, thieving=17, slayer=18, farming=19,
    runecraft=20, hunter=21, construction=22
}
local watching = {}
local baselines = {}

return {
    on_mail = function(from, data)
        if data.action == "watch" and data.skill then
            local sk = string.lower(data.skill)
            local sid = skill_ids[sk]
            if sid then
                watching[sk] = sid
                baselines[sk] = player:xp(sid)
            end
        elseif data.action == "unwatch" and data.skill then
            local sk = string.lower(data.skill)
            watching[sk] = nil
            baselines[sk] = nil
        elseif data.action == "clear" then
            watching = {}
            baselines = {}
        elseif data.action == "report" then
            local gains = {}
            local i = 1
            for sk, sid in pairs(watching) do
                local current = player:xp(sid)
                gains[i] = {
                    skill = sk,
                    start_xp = baselines[sk],
                    current_xp = current,
                    gained = current - baselines[sk]
                }
                i = i + 1
            end
            mail:send(from, { gains = gains })
        end
    end,

    on_render = function(g)
        if not next(watching) then return end
        g:font("Arial", "bold", 11)
        local y = 120
        g:text(10, y, "[XP Tracker]", 0x00CCFF)
        y = y + 16
        g:font("Arial", 11)
        for sk, sid in pairs(watching) do
            local gained = player:xp(sid) - (baselines[sk] or 0)
            if gained > 0 then
                local text = sk .. ": +" .. gained .. " xp"
                g:text(10, y, text, 0x00CCFF)
                y = y + 14
            end
        end
    end
}
