"""SubAlign CLI - AI-powered subtitle auto-alignment tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from subalign.models.config import AlignConfig

console = Console()


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


if __name__ == "__main__":
    main()
