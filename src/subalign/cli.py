"""SubAlign CLI - AI-powered subtitle auto-alignment tool."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from subalign.models.config import AlignConfig

console = Console()


def _check_deps():
    """Check required external dependencies at startup."""
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("ffprobe"):
        missing.append("ffprobe")
    if missing:
        console.print(f"[red]缺少必要依赖:[/red] {', '.join(missing)}")
        console.print("[dim]安装方法: winget install ffmpeg (Windows) / brew install ffmpeg (macOS)[/dim]")
        sys.exit(1)


def _make_config(ctx: click.Context) -> AlignConfig:
    """Build AlignConfig from CLI context parameters."""
    params = ctx.ensure_object(dict)
    kwargs = {}
    if params.get("lang"):
        kwargs["language"] = params["lang"]
    if params.get("model"):
        kwargs["model_size"] = params["model"]
    if params.get("device"):
        kwargs["device"] = params["device"]
    if params.get("confidence_threshold"):
        kwargs["confidence_threshold"] = params["confidence_threshold"]
    if params.get("output_format"):
        kwargs["output_format"] = params["output_format"]
    if params.get("bilingual_style"):
        kwargs["bilingual_style"] = params["bilingual_style"]
    if params.get("primary_lang"):
        kwargs["primary_lang"] = params["primary_lang"]
    if params.get("secondary_lang"):
        kwargs["secondary_lang"] = params["secondary_lang"]
    if params.get("audio_track") is not None:
        kwargs["audio_track"] = params["audio_track"]
    return AlignConfig(**kwargs)


@click.group()
@click.option("--lang", type=str, default=None, help="Language code (ja/en/zh/auto)")
@click.option("--model", type=click.Choice(["tiny", "base", "small", "medium", "large-v3"]), default="medium")
@click.option("--device", type=click.Choice(["auto", "cuda", "cpu"]), default="auto")
@click.option("--confidence-threshold", type=float, default=0.7)
@click.option("--output-format", type=click.Choice(["ass", "srt"]), default="ass")
@click.option("--audio-track", type=int, default=None, help="Audio track index")
@click.pass_context
def main(ctx, **kwargs):
    """SubAlign - AI-powered subtitle auto-alignment tool."""
    _check_deps()
    ctx.ensure_object(dict)
    ctx.obj.update(kwargs)


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.argument("subtitle", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), required=True)
@click.option("--reference", type=click.Path(exists=True), default=None, help="Reference subtitle for faster sync")
@click.option("--backend", type=click.Choice(["ffsubsync", "alass"]), default="ffsubsync")
@click.option("--refine/--no-refine", default=False, help="Refine with ASR after sync")
@click.pass_context
def sync(ctx, video, subtitle, output, reference, backend, refine):
    """[S2] Re-align subtitles with shifted timing."""
    from subalign.core.align import quick_realign, refine_with_asr

    config = _make_config(ctx)
    console.print(f"[bold]Syncing[/bold] {subtitle} → {output}")

    ref = Path(reference) if reference else None
    result = quick_realign(Path(video), Path(subtitle), Path(output), config, ref, backend)

    if refine:
        console.print("[dim]Refining with ASR...[/dim]")
        result = refine_with_asr(Path(video), result, Path(output), config)

    console.print(f"[green]Done:[/green] {result}")


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.argument("subtitle", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), required=True)
@click.option("--detect-missing/--no-detect-missing", default=False, help="Detect and mark missing segments")
@click.option("--report", type=click.Path(), default=None, help="Save alignment report as JSON")
@click.pass_context
def align(ctx, video, subtitle, output, detect_missing, report):
    """[S3] Full alignment with ASR (text without timing or partial timing)."""
    from subalign.core.matcher import full_align, generate_alignment_report

    config = _make_config(ctx)
    console.print(f"[bold]Aligning[/bold] {subtitle} → {output}")
    console.print(f"[dim]Model: {config.model_size} | Device: {config.resolve_device()}[/dim]")

    result_path, matches = full_align(Path(video), Path(subtitle), Path(output), config, detect_missing)

    report_data = generate_alignment_report(matches)

    table = Table(title="Alignment Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total alignments", str(report_data["total_alignments"]))
    table.add_row("Matched", str(report_data["matched"]))
    table.add_row("Low confidence", str(report_data["low_confidence"]))
    table.add_row("Missing in subtitle", str(report_data["missing_in_subtitle"]))
    table.add_row("Missing in ASR", str(report_data["missing_in_asr"]))
    table.add_row("Avg confidence", f"{report_data['average_confidence']:.1%}")
    console.print(table)

    if report:
        Path(report).write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
        console.print(f"[dim]Report saved to {report}[/dim]")

    console.print(f"[green]Done:[/green] {result_path}")


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.argument("subtitle", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), required=True)
@click.option("--keyframe/--no-keyframe", default=True, help="Snap to keyframes")
@click.option("--beats/--no-beats", default=True, help="Snap to audio beats")
@click.option("--tolerance", type=float, default=0.08, help="Snap tolerance in seconds")
@click.pass_context
def snap(ctx, video, subtitle, output, keyframe, beats, tolerance):
    """[S4] Snap OP/ED subtitle timing to keyframes/beats."""
    from subalign.core.audio import extract_audio
    from subalign.core.keyframe import snap_to_keyframes

    config = _make_config(ctx)
    console.print(f"[bold]Snapping[/bold] {subtitle} → {output}")

    audio_path = None
    if beats:
        audio_path = extract_audio(Path(video), config)

    snap_to_keyframes(
        Path(video), Path(subtitle), Path(output),
        audio_path=audio_path,
        use_scene_changes=keyframe,
        use_beats=beats,
        frame_tolerance=tolerance,
    )
    console.print(f"[green]Done:[/green] {output}")


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.option("--primary", type=click.Path(exists=True), required=True, help="Primary language subtitle")
@click.option("--secondary", type=click.Path(exists=True), required=True, help="Secondary language subtitle")
@click.option("--primary-lang", type=str, default="ja", help="Primary language code")
@click.option("--secondary-lang", type=str, default="zh", help="Secondary language code")
@click.option("--bilingual-style", type=click.Choice(["merged", "split", "comment"]), default="split")
@click.option("-o", "--output", type=click.Path(), required=True)
@click.pass_context
def bilingual(ctx, video, primary, secondary, primary_lang, secondary_lang, bilingual_style, output):
    """[S5] Align bilingual subtitles."""
    from subalign.core.bilingual import align_bilingual

    ctx.obj["primary_lang"] = primary_lang
    ctx.obj["secondary_lang"] = secondary_lang
    ctx.obj["bilingual_style"] = bilingual_style
    config = _make_config(ctx)

    console.print(f"[bold]Bilingual align[/bold] {primary_lang}+{secondary_lang} → {output}")

    align_bilingual(Path(video), Path(primary), Path(secondary), Path(output), config)
    console.print(f"[green]Done:[/green] {output}")


@main.command("split-bd")
@click.argument("video", type=click.Path(exists=True))
@click.option("--subs", type=click.Path(exists=True), multiple=True, help="Episode subtitle files in order")
@click.option("-o", "--output", type=click.Path(), default=None)
@click.option("--detect-only", is_flag=True, help="Only detect boundaries, don't concatenate")
@click.option("--ep-min", type=int, default=1200, help="Min episode duration in seconds (default 20min)")
@click.option("--ep-max", type=int, default=1800, help="Max episode duration in seconds (default 30min)")
@click.pass_context
def split_bd(ctx, video, subs, output, detect_only, ep_min, ep_max):
    """[S6] Detect episode boundaries in BD video and concatenate subtitles."""
    from subalign.core.splitter import (
        concatenate_subtitles,
        detect_episode_boundaries,
        format_boundaries_report,
    )

    config = _make_config(ctx)
    config.ep_duration_range = (ep_min, ep_max)

    console.print(f"[bold]Detecting episodes[/bold] in {video}")

    result = detect_episode_boundaries(Path(video), config)
    console.print(format_boundaries_report(result))

    if detect_only:
        return

    if not subs:
        console.print("[red]Error:[/red] Provide subtitle files with --subs")
        sys.exit(1)

    if not output:
        console.print("[red]Error:[/red] Provide output path with -o")
        sys.exit(1)

    sub_paths = [Path(s) for s in subs]
    concatenate_subtitles(result.boundaries, sub_paths, Path(output), config=config)
    console.print(f"[green]Done:[/green] {output}")


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.argument("subtitle", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), required=True)
@click.pass_context
def auto(ctx, video, subtitle, output):
    """Auto-detect scenario and apply appropriate alignment."""
    from subalign.core.subtitle import SubtitleStatus, analyze_subtitles, load_subtitles

    config = _make_config(ctx)
    subs = load_subtitles(Path(subtitle))
    info = analyze_subtitles(subs, Path(subtitle))

    console.print(f"[dim]Detected: {info.line_count} lines, {info.timed_count} timed, status={info.status.name}[/dim]")

    if info.status == SubtitleStatus.TIMED_OK:
        console.print("[green]Subtitles appear correctly timed. Copying as-is.[/green]")
        from subalign.core.subtitle import save_subtitles
        save_subtitles(subs, Path(output))

    elif info.status == SubtitleStatus.TIMED_SHIFTED:
        console.print("[yellow]Timing detected but may be shifted. Running quick sync...[/yellow]")
        ctx.invoke(sync, video=video, subtitle=subtitle, output=output)

    elif info.status in (SubtitleStatus.UNTIMED, SubtitleStatus.PARTIAL):
        console.print("[yellow]No/partial timing. Running full ASR alignment...[/yellow]")
        ctx.invoke(align, video=video, subtitle=subtitle, output=output, detect_missing=True)

    console.print(f"[green]Done:[/green] {output}")


@main.command()
@click.pass_context
def config(ctx):
    """查看和修改配置（API Key、默认模型、语言等）。"""
    from subalign.models.config import (
        ASR_BACKENDS,
        LANG_NAMES,
        MODEL_NAMES,
        load_user_config,
        save_user_config,
    )

    current = load_user_config()

    console.print("[bold]当前配置[/bold]")
    console.print()

    # ASR backend
    backend_names = {
        "local": "本地模型 (faster-whisper/WhisperX)",
        "openai": "OpenAI Whisper API (在线)",
    }
    console.print(f"  ASR 引擎:     {backend_names.get(current['asr_backend'], current['asr_backend'])}")
    console.print(f"  本地模型:     {MODEL_NAMES.get(current['local_model'], current['local_model'])}")
    console.print(f"  计算设备:     {current['local_device']}")
    console.print(f"  默认语言:     {LANG_NAMES.get(current.get('default_language') or 'auto', 'auto')}")
    console.print(f"  OpenAI Key:   {'已配置' if current.get('openai_api_key') else '[red]未配置[/red]'}")
    if current.get("openai_base_url"):
        console.print(f"  OpenAI 端点:  {current['openai_base_url']}")
    console.print(f"  OpenAI 模型:  {current.get('openai_model', 'whisper-1')}")
    console.print()

    # Interactive edit
    console.print("[bold]修改配置[/bold]（直接回车保持当前值）")
    console.print()

    new_cfg = dict(current)

    # Backend
    console.print("ASR 引擎选项: local=本地模型, openai=OpenAI API")
    val = click.prompt("  ASR 引擎", default=current["asr_backend"], show_default=True)
    new_cfg["asr_backend"] = val

    if val == "openai" or current.get("openai_api_key"):
        key = click.prompt(
            "  OpenAI API Key",
            default=current.get("openai_api_key") or "",
            show_default=False,
            hide_input=True,
        )
        if key:
            new_cfg["openai_api_key"] = key

        base_url = click.prompt(
            "  OpenAI 端点 (留空=官方, 或填自定义兼容地址)",
            default=current.get("openai_base_url") or "",
            show_default=False,
        )
        new_cfg["openai_base_url"] = base_url

        model = click.prompt(
            "  OpenAI 模型",
            default=current.get("openai_model") or "whisper-1",
        )
        new_cfg["openai_model"] = model

    # Language
    lang_options = ", ".join(f"{k}={v}" for k, v in list(LANG_NAMES.items())[:6])
    console.print(f"  语言选项: {lang_options}")
    lang = click.prompt("  默认语言", default=current.get("default_language") or "auto")
    new_cfg["default_language"] = None if lang == "auto" else lang

    # Local model
    model_options = ", ".join(f"{k}" for k in MODEL_NAMES)
    console.print(f"  本地模型选项: {model_options}")
    local_model = click.prompt("  本地模型", default=current.get("local_model") or "medium")
    new_cfg["local_model"] = local_model

    save_user_config(new_cfg)
    console.print()
    console.print(f"[green]配置已保存到[/green] {current.get('config_file', '~/.config/subalign/config.json')}")


if __name__ == "__main__":
    main()
