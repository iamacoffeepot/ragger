-- translator: Scans visible widget text, batches to Claude for translation,
-- applies translations back to widgets. Supports language switching and debug
-- toggle via mail.
--
-- Mail API:
--   {language="French"}     — switch target language, clears cache
--   {debug=true/false}      — set debug mode
--   {debug="toggle"}        — toggle debug mode
--
-- Config (via args table when spawned from template):
--   args.language            — initial target language (default "French")
--   args.debug               — initial debug state (default false)

local DEBUG = args and args.debug or false
local language = args and args.language or "French"

local cache = {}
local reverse = {}
local originals = {}
local applied = {}
local pending = {}
local pending_frame = {}
local sent_order = {}
local batch = {}
local widget_refs = {}
local known_groups = {}
local fitted = {}

local PREFIX = "[translator]"
local MIN_LEN = 4
local BATCH_MAX = 50
local BATCH_DELAY = 150
local PENDING_TIMEOUT = 6000
local RESCAN_INTERVAL = 150
local frame = 0
local last_scan_frame = 0
local batch_in_flight = false
local batch_started_frame = 0
local needs_full_scan = false
local prev_root_set = {}

local function dbg(msg)
    if DEBUG then
        chat:game(PREFIX .. " " .. msg)
    end
end

local TRANSLIT_PATTERNS = {
    {"\195\160", "a"}, {"\195\161", "a"}, {"\195\162", "a"}, {"\195\163", "a"}, {"\195\164", "a"}, {"\195\165", "a"},
    {"\195\168", "e"}, {"\195\169", "e"}, {"\195\170", "e"}, {"\195\171", "e"},
    {"\195\172", "i"}, {"\195\173", "i"}, {"\195\174", "i"}, {"\195\175", "i"},
    {"\195\178", "o"}, {"\195\179", "o"}, {"\195\180", "o"}, {"\195\181", "o"}, {"\195\182", "o"},
    {"\195\185", "u"}, {"\195\186", "u"}, {"\195\187", "u"}, {"\195\188", "u"},
    {"\195\177", "n"}, {"\195\167", "c"}, {"\195\189", "y"}, {"\195\191", "y"},
    {"\195\128", "A"}, {"\195\129", "A"}, {"\195\130", "A"}, {"\195\131", "A"}, {"\195\132", "A"}, {"\195\133", "A"},
    {"\195\136", "E"}, {"\195\137", "E"}, {"\195\138", "E"}, {"\195\139", "E"},
    {"\195\140", "I"}, {"\195\141", "I"}, {"\195\142", "I"}, {"\195\143", "I"},
    {"\195\146", "O"}, {"\195\147", "O"}, {"\195\148", "O"}, {"\195\149", "O"}, {"\195\150", "O"},
    {"\195\153", "U"}, {"\195\154", "U"}, {"\195\155", "U"}, {"\195\156", "U"},
    {"\195\145", "N"}, {"\195\135", "C"}, {"\195\157", "Y"},
    {"\197\147", "oe"}, {"\197\146", "OE"},
    {"\195\166", "ae"}, {"\195\134", "AE"},
    {"\195\159", "ss"},
}

local function transliterate(text)
    local result = text
    for _, pair in ipairs(TRANSLIT_PATTERNS) do
        result = result:gsub(pair[1], pair[2])
    end
    result = result:gsub("[\128-\255]+", "?")
    return result
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

local function restore_all()
    local restored = 0
    for key, orig in pairs(originals) do
        if applied[key] then
            local ref = widget_refs[key]
            if ref then
                set_widget_text(ref, orig)
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

local function process_widget(k, queue_new)
    local text = k.text
    if not text then return end
    local key = widget_key(k)

    widget_refs[key] = {
        id = k.id,
        index = k.index,
        width = k.width,
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
    if #batch == 0 or batch_in_flight then return end
    sent_order = {}
    for i = 1, #batch do
        sent_order[i] = batch[i]
        pending[batch[i]] = true
        pending_frame[batch[i]] = frame
    end
    batch_in_flight = true
    batch_started_frame = 0

    dbg("Sending batch of " .. #batch)
    chat:game(PREFIX .. " Translating " .. #batch .. " texts...")

    mail:send("claude:agent", {
        question = "Translate these texts to " .. language .. ". Return ONLY a JSON array of translated strings in the same order. Preserve any <col=hex> or <br> tags exactly. Do not add extra tags. Texts:\n" .. json.encode(sent_order)
    })

    batch = {}
end

local function expire_pending()
    local expired = 0
    for text, f in pairs(pending_frame) do
        if frame - f > PENDING_TIMEOUT then
            pending[text] = nil
            pending_frame[text] = nil
            expired = expired + 1
        end
    end
    if expired > 0 then
        batch_in_flight = false
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
    if type(data.result) == "table" then
        if data.result[1] ~= nil and type(data.result[1]) == "string" then
            return data.result
        end
    end

    local text = data.text
    if not text and type(data.result) == "string" then
        text = data.result
    end
    if not text then return nil end

    local depth = 0
    local arr_start = nil
    local arr_end = nil

    for i = 1, #text do
        local c = text:sub(i, i)
        if c == "[" then
            if depth == 0 then arr_start = i end
            depth = depth + 1
        elseif c == "]" then
            depth = depth - 1
            if depth == 0 then
                arr_end = i
                break
            end
        end
    end

    if arr_start and arr_end then
        local ok, result = pcall(json.decode, text:sub(arr_start, arr_end))
        if ok and type(result) == "table" then
            return result
        end
    end

    return nil
end

local FONTS = {
    [494] = {"RuneScape Small", "plain", 11},
    [495] = {"RuneScape", "plain", 14},
    [496] = {"RuneScape Bold", "bold", 14},
    [497] = {"RuneScape Large", "plain", 20},
}

return {
    on_start = function()
        chat:game(PREFIX .. " Active - language: " .. language .. (DEBUG and " [DEBUG]" or ""))
        for gid = 0, 900 do
            local w = widget:get(gid, 0)
            if w then
                known_groups[gid] = true
            end
        end
        full_scan()
    end,

    on_render = function(g)
        for key, orig in pairs(originals) do
            local translated = cache[orig]
            if not translated then goto continue end

            local ref = widget_refs[key]
            if not ref or not ref.width or ref.width <= 0 then goto continue end

            local w = ref.width
            local f = ref.font_id or 495
            local fit_key = orig .. "|" .. w .. "|" .. f

            if fitted[fit_key] ~= nil then goto continue end

            local font = FONTS[f] or FONTS[495]
            g:font(font[1], font[2], font[3])
            local plain = translated:gsub("<[^>]+>", "")
            local tw = g:text_width(plain)

            if tw <= w then
                fitted[fit_key] = translated
            else
                local dots_w = g:text_width("...")
                local target = w - dots_w
                if target <= 0 then
                    fitted[fit_key] = "..."
                else
                    local lo, hi = 1, #plain
                    while lo < hi do
                        local mid = math.floor((lo + hi + 1) / 2)
                        if g:text_width(plain:sub(1, mid)) <= target then
                            lo = mid
                        else
                            hi = mid - 1
                        end
                    end

                    local count = 0
                    local cut_pos = #translated
                    for i = 1, #translated do
                        local c = translated:sub(i, i)
                        if c == "<" then
                            local tag_end = translated:find(">", i)
                            if tag_end then end
                        elseif count < lo then
                            local in_tag = false
                            for j = i, 1, -1 do
                                local ch = translated:sub(j, j)
                                if ch == ">" then break end
                                if ch == "<" then in_tag = true; break end
                            end
                            if not in_tag then
                                count = count + 1
                            end
                            if count >= lo then
                                cut_pos = i
                                break
                            end
                        end
                    end
                    fitted[fit_key] = translated:sub(1, cut_pos) .. "..."
                end
            end
            ::continue::
        end
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

        if #batch > 0 and not batch_in_flight then
            local elapsed = frame - batch_started_frame
            if #batch >= BATCH_MAX or elapsed >= BATCH_DELAY then
                send_batch()
            end
        end

        if frame % 300 == 0 then
            expire_pending()
        end

        for key, orig in pairs(originals) do
            local translated = cache[orig]
            if not translated then goto continue end

            local ref = widget_refs[key]
            if not ref then goto continue end

            local text_to_apply
            local w = ref.width
            local f = ref.font_id or 495

            if w and w > 0 then
                local fit_key = orig .. "|" .. w .. "|" .. f
                text_to_apply = fitted[fit_key]
                if not text_to_apply then goto continue end
            else
                text_to_apply = translated
            end

            if ref.index and ref.index >= 0 then
                local cw = widget:child(ref.id, ref.index)
                if not cw then goto continue end
                local current = cw.text
                if current == text_to_apply then
                    applied[key] = text_to_apply
                elseif current == orig then
                    widget:set_text(ref.id, text_to_apply, ref.index)
                    applied[key] = text_to_apply
                else
                    originals[key] = nil
                    applied[key] = nil
                    widget_refs[key] = nil
                    if current and cache[current] then
                        originals[key] = current
                        widget_refs[key] = ref
                        local refit_key = current .. "|" .. w .. "|" .. f
                        local refit = fitted[refit_key]
                        if refit then
                            widget:set_text(ref.id, refit, ref.index)
                            applied[key] = refit
                        end
                    end
                end
            else
                if applied[key] ~= text_to_apply then
                    set_widget_text(ref, text_to_apply)
                    applied[key] = text_to_apply
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

        if data and data.debug ~= nil then
            if data.debug == "toggle" then
                DEBUG = not DEBUG
            else
                DEBUG = data.debug and true or false
            end
            chat:game(PREFIX .. " Debug " .. (DEBUG and "ON" or "OFF"))
            return
        end

        if data and data.language then
            restore_all()
            language = data.language
            cache = {}
            reverse = {}
            applied = {}
            originals = {}
            pending = {}
            pending_frame = {}
            sent_order = {}
            batch = {}
            batch_in_flight = false
            batch_started_frame = 0
            widget_refs = {}
            fitted = {}
            needs_full_scan = true
            chat:game(PREFIX .. " Language changed to: " .. language)
            return
        end

        local translations = parse_translations(data)
        if translations then
            batch_in_flight = false
            local matched = 0
            for i = 1, math.min(#translations, #sent_order) do
                local orig = sent_order[i]
                if orig and translations[i] and type(translations[i]) == "string" then
                    local clean = transliterate(translations[i])
                    cache[orig] = clean
                    reverse[clean] = orig
                    pending[orig] = nil
                    pending_frame[orig] = nil
                    matched = matched + 1
                end
            end
            sent_order = {}
            chat:game(PREFIX .. " " .. matched .. " translated")
        else
            dbg("Ignoring non-translation mail, keeping batch in flight")
        end
    end,

    on_stop = function()
        local restored = restore_all()
        chat:game(PREFIX .. " Stopped. Restored " .. restored .. " widgets.")
    end
}
