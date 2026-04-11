-- translator: Scans visible widget text, batches to Claude for translation,
-- applies translations back to widgets. Supports language switching and
-- log level control via mail.
--
-- Mail API:
--   {language="French"}           — switch target language, clears cache
--   {log_level="info"}            — set log level: "silent", "info", "debug"
--   {action="ignore", id=N}       — add component ID to ignore list
--   {action="unignore", id=N}     — remove component ID from ignore list
--
-- Config (via args table when spawned from template):
--   args.language                  — initial target language (default "UwU")
--   args.log_level                 — initial log level (default "info")

local LOG_SILENT = 0
local LOG_INFO = 1
local LOG_DEBUG = 2
local LOG_NAMES = { silent = LOG_SILENT, info = LOG_INFO, debug = LOG_DEBUG }

local function parse_log_level(val)
    if type(val) == "number" then return val end
    if type(val) == "string" then return LOG_NAMES[val] or LOG_INFO end
    return LOG_INFO
end

local log_level = parse_log_level(args and args.log_level)
local language = args and args.language or "UwU"

local cache = {}
local reverse = {}
local originals = {}
local applied = {}
local pending = {}
local pending_frame = {}
local batch = {}
local widget_refs = {}
local original_widths = {}
local known_groups = {}
local in_flight = {}
local ignore_ids = {
    [162 * 65536 + 57] = true,  -- CHATBOX chat input line
}

local PREFIX = "[translator]"
local MIN_LEN = 4
local BATCH_MAX = 50
local BATCH_DELAY = 2
local PENDING_TIMEOUT = 6000
local RESCAN_INTERVAL = 150
local frame = 0
local last_scan_frame = 0
local next_batch_id = 1
local batch_started_frame = 0
local needs_full_scan = false
local prev_root_set = {}

local function info(msg)
    if log_level >= LOG_INFO then
        chat:game(PREFIX .. " " .. msg)
    end
end

local function dbg(msg)
    if log_level >= LOG_DEBUG then
        chat:game(PREFIX .. " " .. msg)
    end
end

local function widget_key(k)
    if k.index and k.index >= 0 then
        return k.id .. ":" .. k.index
    end
    return tostring(k.id)
end

local function is_translatable(text)
    if text:sub(1, #PREFIX) == PREFIX then return false end
    local stripped = text:gsub("<[^>]+>", "")
    stripped = stripped:match("^%s*(.-)%s*$")
    if not stripped or #stripped < MIN_LEN then return false end
    if not stripped:match("[a-zA-Z]") then return false end
    return true
end

local function set_widget_text(ref, text)
    if ref.index and ref.index >= 0 then
        widget:set_text(ref.id, text, ref.index)
    else
        widget:set_text(ref.id, text)
    end
end

local function set_widget_width(ref, w)
    if ref.index and ref.index >= 0 then
        widget:set_width(ref.id, w, ref.index)
    else
        widget:set_width(ref.id, w)
    end
end

local function restore_all()
    local restored = 0
    for key, orig in pairs(originals) do
        if applied[key] then
            local ref = widget_refs[key]
            if ref then
                set_widget_text(ref, orig)
                if original_widths[key] then
                    set_widget_width(ref, original_widths[key])
                end
                restored = restored + 1
            end
        end
    end
    return restored
end

local function scan_group(gid, all)
    local w = widget:get(gid, 0)
    if w and not w.hidden then
        local texts = widget:find(gid, 0, { has_text = true, type = widget.TYPE_TEXT })
        if texts then
            for j = 1, #texts do all[#all + 1] = texts[j] end
        end
    end
end

local function find_text_widgets()
    local all = {}
    local scanned = {}
    local roots = widget:roots()
    if roots then
        for i = 1, #roots do
            local r = roots[i]
            if r and r.id and not r.hidden then
                local gid = math.floor(r.id / 65536)
                scanned[gid] = true
                local texts = widget:find(r.id, { has_text = true, type = widget.TYPE_TEXT })
                if texts then
                    for j = 1, #texts do all[#all + 1] = texts[j] end
                end
            end
        end
    end
    for gid, _ in pairs(known_groups) do
        if not scanned[gid] then
            scan_group(gid, all)
        end
    end
    return all
end

local function is_ignored(k)
    if ignore_ids[k.id] then return true end
    if k.parent_id and ignore_ids[k.parent_id] then return true end
    return false
end

local function process_widget(k, queue_new)
    local text = k.text
    if not text then return end
    if is_ignored(k) then return end
    local key = widget_key(k)

    widget_refs[key] = {
        id = k.id,
        index = k.index,
        width = k.width,
        height = k.height,
        font_id = k.font_id
    }

    if reverse[text] then return end
    applied[key] = nil

    if cache[text] then
        originals[key] = text
        return
    end

    if originals[key] and cache[originals[key]] then
        return
    end

    if queue_new and is_translatable(text) and not pending[text] then
        originals[key] = text
        local found = false
        for j = 1, #batch do
            if batch[j] == text then found = true; break end
        end
        if not found and #batch < BATCH_MAX then
            batch[#batch + 1] = text
            if batch_started_frame == 0 then
                batch_started_frame = frame
            end
        end
    end
end

local function full_scan()
    local widgets = find_text_widgets()
    for i = 1, #widgets do
        process_widget(widgets[i], true)
    end
    last_scan_frame = frame
end

local function apply_scan()
    local widgets = find_text_widgets()
    for i = 1, #widgets do
        process_widget(widgets[i], false)
    end
    last_scan_frame = frame
end

local function send_batch()
    if #batch == 0 then return end
    local bid = next_batch_id
    next_batch_id = next_batch_id + 1

    local order = {}
    for i = 1, #batch do
        order[i] = batch[i]
        pending[batch[i]] = true
        pending_frame[batch[i]] = frame
    end
    in_flight[bid] = { order = order, frame = frame }
    batch_started_frame = 0

    dbg("Sending batch #" .. bid .. " (" .. #order .. " texts)")
    info("Translating " .. #order .. " texts (batch " .. bid .. ")...")

    mail:send("claude:agent", {
        question = "Translate these texts to " .. language .. ". Return ONLY a JSON object: {\"batch_id\":" .. bid .. ",\"translations\":[...]} where translations is an array of translated strings in the same order. Preserve any <col=hex> or <br> tags and escape sequences (\\n, \\r, etc.) exactly as they appear. Do not add extra tags. Texts:\n" .. json.encode(order)
    })

    batch = {}
end

local function expire_pending()
    local expired = 0
    for bid, flight in pairs(in_flight) do
        if frame - flight.frame > PENDING_TIMEOUT then
            for _, text in ipairs(flight.order) do
                pending[text] = nil
                pending_frame[text] = nil
            end
            in_flight[bid] = nil
            expired = expired + 1
        end
    end
    if expired > 0 then
        dbg("Expired " .. expired .. " batch(es)")
        needs_full_scan = true
    end
end

local function check_roots()
    local roots = widget:roots()
    if not roots then return end
    local cur = {}
    for i = 1, #roots do
        local r = roots[i]
        if r and r.id then
            local gid = math.floor(r.id / 65536)
            cur[gid] = true
            if not prev_root_set[gid] then
                known_groups[gid] = true
                needs_full_scan = true
            end
        end
    end
    prev_root_set = cur
end

local function parse_translations(data)
    if data.batch_id and data.translations and type(data.translations) == "table" then
        return data.batch_id, data.translations
    end
    if not data.batch_id and type(data[1]) == "string" then
        return nil, data
    end
    return nil, nil
end

return {
    on_start = function()
        local level_name = "info"
        for name, val in pairs(LOG_NAMES) do
            if val == log_level then level_name = name end
        end
        info("Active - language: " .. language .. " [" .. level_name .. "]")
        for gid = 0, 900 do
            local w = widget:get(gid, 0)
            if w then
                known_groups[gid] = true
            end
        end
        full_scan()
    end,

    on_frame = function()
        frame = frame + 1

        check_roots()

        if needs_full_scan then
            needs_full_scan = false
            full_scan()
        elseif frame - last_scan_frame >= RESCAN_INTERVAL then
            apply_scan()
        end

        if #batch > 0 then
            local elapsed = frame - batch_started_frame
            if #batch >= BATCH_MAX or elapsed >= BATCH_DELAY then
                send_batch()
            end
        end

        if frame % 300 == 0 then
            expire_pending()
        end
    end,

    on_post_frame = function()
        for key, orig in pairs(originals) do
            local translated = cache[orig]
            if not translated then goto continue end

            local ref = widget_refs[key]
            if not ref then goto continue end

            local font = ref.font_id or 495
            local orig_w = original_widths[key] or ref.width

            -- Resize widget if translated text is wider (single-line only)
            local multiline = translated:find("<br>") or (ref.height and ref.height >= 2 * text:height(font))
            if orig_w and orig_w > 0 and not multiline then
                local tw = text:width(translated, font)
                if tw > orig_w then
                    if not original_widths[key] then
                        original_widths[key] = orig_w
                    end
                    set_widget_width(ref, tw)
                end
            end

            if ref.index and ref.index >= 0 then
                local cw = widget:child(ref.id, ref.index)
                if not cw then goto continue end
                local current = cw.text
                if current == translated then
                    applied[key] = translated
                elseif current == orig then
                    widget:set_text(ref.id, translated, ref.index)
                    applied[key] = translated
                else
                    originals[key] = nil
                    applied[key] = nil
                    widget_refs[key] = nil
                    if current and cache[current] then
                        originals[key] = current
                        widget_refs[key] = ref
                        widget:set_text(ref.id, cache[current], ref.index)
                        applied[key] = cache[current]
                    end
                end
            else
                local w = widget:component(ref.id)
                if not w then goto continue end
                local current = w.text
                if current == translated then
                    applied[key] = translated
                elseif current == orig then
                    set_widget_text(ref, translated)
                    applied[key] = translated
                else
                    originals[key] = nil
                    applied[key] = nil
                    widget_refs[key] = nil
                    if current and cache[current] then
                        originals[key] = current
                        widget_refs[key] = ref
                        set_widget_text(ref, cache[current])
                        applied[key] = cache[current]
                    end
                end
            end
            ::continue::
        end
    end,

    on_widget_loaded = function(data)
        known_groups[data.group_id] = true
        needs_full_scan = true
    end,

    on_chat = function(data)
        needs_full_scan = true
    end,

    on_mail = function(from, data)
        dbg("Mail from: " .. tostring(from))

        if data and data.log_level ~= nil then
            log_level = parse_log_level(data.log_level)
            local level_name = "info"
            for name, val in pairs(LOG_NAMES) do
                if val == log_level then level_name = name end
            end
            chat:game(PREFIX .. " Log level: " .. level_name)
            return
        end

        if data and data.action == "ignore" and data.id then
            ignore_ids[data.id] = true
            info("Ignoring component " .. data.id)
            return
        end

        if data and data.action == "unignore" and data.id then
            ignore_ids[data.id] = nil
            info("Unignored component " .. data.id)
            return
        end

        if data and data.language then
            restore_all()
            language = data.language
            cache = {}
            reverse = {}
            applied = {}
            originals = {}
            original_widths = {}
            pending = {}
            pending_frame = {}
            in_flight = {}
            batch = {}
            batch_started_frame = 0
            widget_refs = {}
            needs_full_scan = true
            info("Language changed to: " .. language)
            return
        end

        local bid, translations = parse_translations(data)
        if translations then
            local order
            if bid and in_flight[bid] then
                order = in_flight[bid].order
                in_flight[bid] = nil
            else
                -- Fallback: find oldest in-flight batch
                local oldest_bid, oldest_frame = nil, math.huge
                for k, flight in pairs(in_flight) do
                    if flight.frame < oldest_frame then
                        oldest_bid = k
                        oldest_frame = info.frame
                    end
                end
                if oldest_bid then
                    order = in_flight[oldest_bid].order
                    in_flight[oldest_bid] = nil
                    dbg("No batch_id, matched to oldest batch #" .. oldest_bid)
                end
            end

            if order then
                local matched = 0
                for i = 1, math.min(#translations, #order) do
                    local orig = order[i]
                    if orig and translations[i] and type(translations[i]) == "string" then
                        local clean = text:ascii(translations[i])
                        cache[orig] = clean
                        reverse[clean] = orig
                        pending[orig] = nil
                        pending_frame[orig] = nil
                        matched = matched + 1
                    end
                end
                info(matched .. " translated" .. (bid and " (batch " .. bid .. ")" or ""))
            end
        else
            dbg("Ignoring non-translation mail")
        end
    end,

    on_stop = function()
        local restored = restore_all()
        info("Stopped. Restored " .. restored .. " widgets.")
    end
}