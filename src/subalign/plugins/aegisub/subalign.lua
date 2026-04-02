-- SubAlign - Aegisub Automation Plugin
-- Calls the subalign CLI tool via io.popen() and applies results
--
-- Installation: Copy this file to Aegisub's automation/autoload directory
-- Requires: subalign CLI installed and available in PATH

local tr = aegisub.gettext

script_name = tr"SubAlign"
script_description = tr"AI-powered subtitle auto-alignment"
script_author = "SubAlign"
script_version = "0.1.0"

-- Utility: run subalign CLI and capture output
local function run_subalign(args)
    local cmd = "subalign " .. args .. " 2>&1"
    local handle = io.popen(cmd)
    if not handle then
        aegisub.debug.out("Failed to run subalign command\n")
        return nil
    end
    local output = handle:read("*a")
    handle:close()
    return output
end

-- Utility: get video path from Aegisub project
local function get_video_path()
    local props = aegisub.project_properties()
    if props and props.video_file and props.video_file ~= "" then
        return props.video_file
    end
    return nil
end

-- Utility: save current subtitles to temp file
local function save_temp_subs(subs)
    local tmpfile = os.tmpname() .. ".ass"
    local f = io.open(tmpfile, "w")
    if not f then return nil end
    -- Write a minimal ASS header + events
    f:write("[Script Info]\n")
    f:write("ScriptType: v4.00+\n")
    f:write("PlayResX: 1920\n")
    f:write("PlayResY: 1080\n\n")
    f:write("[V4+ Styles]\n")
    f:write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
    f:write("Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n")
    f:write("[Events]\n")
    f:write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

    for i = 1, #subs do
        local line = subs[i]
        if line.class == "dialogue" then
            local dtype = line.comment and "Comment" or "Dialogue"
            f:write(string.format("%s: %d,%s,%s,%s,%s,%04d,%04d,%04d,%s,%s\n",
                dtype, line.layer,
                line.start_time and aegisub.ms_to_ass(line.start_time) or "0:00:00.00",
                line.end_time and aegisub.ms_to_ass(line.end_time) or "0:00:00.00",
                line.style or "Default",
                line.actor or "",
                line.margin_l or 0, line.margin_r or 0, line.margin_t or 0,
                line.effect or "",
                line.text or ""))
        end
    end
    f:close()
    return tmpfile
end

-- Utility: load aligned results back into Aegisub
local function load_aligned_subs(subs, aligned_path)
    local f = io.open(aligned_path, "r")
    if not f then
        aegisub.debug.out("Cannot read aligned file: " .. aligned_path .. "\n")
        return
    end

    local in_events = false
    local event_index = 0
    local dialogue_indices = {}

    -- Find all dialogue line indices
    for i = 1, #subs do
        if subs[i].class == "dialogue" then
            table.insert(dialogue_indices, i)
        end
    end

    local new_times = {}
    for line in f:lines() do
        if line:match("^%[Events%]") then
            in_events = true
        elseif in_events and (line:match("^Dialogue:") or line:match("^Comment:")) then
            event_index = event_index + 1
            local start_str = line:match(",(%d+:%d+:%d+%.%d+),")
            local end_str = line:match(",%d+:%d+:%d+%.%d+,(%d+:%d+:%d+%.%d+),")
            if start_str and end_str then
                table.insert(new_times, {
                    start = aegisub.ass_to_ms(start_str),
                    ["end"] = aegisub.ass_to_ms(end_str),
                })
            end
        end
    end
    f:close()

    -- Apply new times
    local applied = 0
    for i, idx in ipairs(dialogue_indices) do
        if i <= #new_times then
            subs[idx] = subs[idx]  -- trigger copy
            local line = subs[idx]
            line.start_time = new_times[i].start
            line.end_time = new_times[i]["end"]
            subs[idx] = line
            applied = applied + 1
        end
    end

    aegisub.debug.out(string.format("Applied timing to %d/%d lines\n", applied, #dialogue_indices))
end

-------------------------------------------------------------------
-- Menu actions
-------------------------------------------------------------------

-- [S2] Quick re-align
local function do_sync(subs, sel)
    local video = get_video_path()
    if not video then
        aegisub.debug.out("No video loaded. Please load a video first.\n")
        return
    end

    local btn, config = aegisub.dialog.display({
        {class = "label", x = 0, y = 0, label = "Backend:"},
        {class = "dropdown", name = "backend", x = 1, y = 0,
         items = {"ffsubsync", "alass"}, value = "ffsubsync"},
        {class = "checkbox", name = "refine", x = 0, y = 1,
         label = "Refine with ASR", value = false},
    }, {"OK", "Cancel"})

    if btn ~= "OK" then return end

    local tmpfile = save_temp_subs(subs)
    if not tmpfile then return end

    local outfile = os.tmpname() .. ".ass"
    local args = string.format('sync "%s" "%s" -o "%s" --backend %s',
        video, tmpfile, outfile, config.backend)
    if config.refine then args = args .. " --refine" end

    aegisub.progress.title("SubAlign: Syncing...")
    local output = run_subalign(args)
    aegisub.debug.out(output or "")

    load_aligned_subs(subs, outfile)
    os.remove(tmpfile)
    os.remove(outfile)

    aegisub.set_undo_point(tr"SubAlign: Re-align")
end

-- [S3] Full alignment
local function do_align(subs, sel)
    local video = get_video_path()
    if not video then
        aegisub.debug.out("No video loaded.\n")
        return
    end

    local btn, config = aegisub.dialog.display({
        {class = "label", x = 0, y = 0, label = "Language:"},
        {class = "dropdown", name = "lang", x = 1, y = 0,
         items = {"auto", "ja", "en", "zh"}, value = "auto"},
        {class = "label", x = 0, y = 1, label = "Model:"},
        {class = "dropdown", name = "model", x = 1, y = 1,
         items = {"tiny", "base", "small", "medium", "large-v3"}, value = "medium"},
        {class = "checkbox", name = "detect_missing", x = 0, y = 2,
         label = "Detect missing segments", value = true},
    }, {"OK", "Cancel"})

    if btn ~= "OK" then return end

    local tmpfile = save_temp_subs(subs)
    if not tmpfile then return end

    local outfile = os.tmpname() .. ".ass"
    local lang_arg = config.lang ~= "auto" and ("--lang " .. config.lang) or ""
    local args = string.format('align "%s" "%s" -o "%s" --model %s %s%s',
        video, tmpfile, outfile, config.model, lang_arg,
        config.detect_missing and " --detect-missing" or "")

    aegisub.progress.title("SubAlign: Aligning with ASR...")
    local output = run_subalign(args)
    aegisub.debug.out(output or "")

    load_aligned_subs(subs, outfile)
    os.remove(tmpfile)
    os.remove(outfile)

    aegisub.set_undo_point(tr"SubAlign: Full align")
end

-- [S4] OP/ED snap
local function do_snap(subs, sel)
    local video = get_video_path()
    if not video then
        aegisub.debug.out("No video loaded.\n")
        return
    end

    local tmpfile = save_temp_subs(subs)
    if not tmpfile then return end

    local outfile = os.tmpname() .. ".ass"
    local args = string.format('snap "%s" "%s" -o "%s"', video, tmpfile, outfile)

    aegisub.progress.title("SubAlign: Snapping to keyframes...")
    local output = run_subalign(args)
    aegisub.debug.out(output or "")

    load_aligned_subs(subs, outfile)
    os.remove(tmpfile)
    os.remove(outfile)

    aegisub.set_undo_point(tr"SubAlign: OP/ED snap")
end

-- [S6] BD split detect
local function do_split_detect(subs, sel)
    local video = get_video_path()
    if not video then
        aegisub.debug.out("No video loaded.\n")
        return
    end

    local args = string.format('split-bd "%s" --detect-only', video)

    aegisub.progress.title("SubAlign: Detecting episodes...")
    local output = run_subalign(args)

    aegisub.debug.out("Episode boundaries:\n")
    aegisub.debug.out(output or "No output")
end

-------------------------------------------------------------------
-- Register macros
-------------------------------------------------------------------

aegisub.register_macro(
    script_name .. "/" .. tr"Re-align timing (S2)",
    tr"Quick re-align subtitles using audio fingerprinting",
    do_sync)

aegisub.register_macro(
    script_name .. "/" .. tr"Full ASR alignment (S3)",
    tr"Full alignment using speech recognition",
    do_align)

aegisub.register_macro(
    script_name .. "/" .. tr"OP/ED frame snap (S4)",
    tr"Snap subtitle timing to keyframes and beats",
    do_snap)

aegisub.register_macro(
    script_name .. "/" .. tr"Detect BD episodes (S6)",
    tr"Detect episode boundaries in BD video",
    do_split_detect)
