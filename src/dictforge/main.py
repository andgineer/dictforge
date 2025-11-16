import sys
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import rich_click as click
from rich.console import Console
from rich.text import Text

from dictforge import __version__

from .builder import (
    Builder,
    KaikkiDownloadError,
    KaikkiParseError,
    KindleBuildError,
    get_available_formats,
)
from .config import DEFAULTS, config_path, load_config, save_config
from .export_base import ExportError
from .kaikki_utils import lang_meta, make_defaults, normalize_input_name
from .kindlegen import guess_kindlegen_path

# rich-click styling
click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.MAX_WIDTH = 100
click.rich_click.STYLE_HELPTEXT = "dim"
click.rich_click.STYLE_OPTION = "bold"
click.rich_click.STYLE_SWITCH = "bold"
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True


try:  # Populate help defaults without failing the CLI if config loading breaks.
    _help_config_store = {"config": load_config()}
except Exception:  # noqa: BLE001  # pragma: no cover - defensive fallback for corrupted config
    _help_config_store = {"config": DEFAULTS.copy()}


def _show_config_default(key: str, *, empty_label: str = '"" (empty)') -> str:
    """Format the current config value for ``key`` for Click help output."""
    value = _help_config_store["config"].get(key)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return empty_label
    if isinstance(value, str):
        return value or empty_label
    return str(value)


def _get_format_choices() -> str:
    """Return comma-separated list of available export formats."""
    return ", ".join(get_available_formats().keys())


@click.group(invoke_without_command=True, context_settings={"ignore_unknown_options": False})
@click.argument("in_lang", required=False)
@click.argument("out_lang", required=False)
@click.option(
    "--format",
    "export_format",
    default="mobi",
    help=f"Output format ({_get_format_choices()})",
    show_default=True,
)
@click.option(
    "--merge-in-langs",
    default=None,
    help="Comma-separated extra input languages to merge (overrides config)",
    show_default=_show_config_default("merge_in_langs"),
)
@click.option("--title", default="", help="Override auto title", show_default="auto")
@click.option("--shortname", default="", help="Override auto short name", show_default="auto")
@click.option("--outdir", default="", help="Override auto output directory", show_default="auto")
@click.option(
    "--kindlegen-path",
    default="",
    help="Path to kindlegen (auto-detect if empty, required for MOBI format)",
    show_default="auto-detect",
)
@click.option(
    "--max-entries",
    type=int,
    default=0,
    help="Debug: limit number of entries",
    show_default=True,
)
@click.option(
    "--include-pos",
    is_flag=True,
    default=None,
    help="Include part-of-speech headers",
    show_default=_show_config_default("include_pos"),
)
@click.option(
    "--try-fix-inflections",
    is_flag=True,
    default=None,
    help=(
        "Much slower, but vastly improves the lookup"
        "of words that are not recognized by default due to the buggy algorithm that "
        "does not look at inflections if a fitting base word exists"
    ),
    show_default=_show_config_default("try_fix_inflections"),
)
@click.option(
    "--kindle-lang",
    default="",
    help="Override Kindle dictionary language code if your target language is unsupported",
    show_default="auto",
)
@click.option(
    "--cache-dir",
    default=None,
    help="Cache directory for downloaded JSONL",
    show_default=_show_config_default("cache_dir"),
)
@click.option(
    "--reset-cache",
    is_flag=True,
    default=False,
    help="Force re-download of sources",
    show_default=True,
)
@click.option(
    "--compress/--no-compress",
    default=True,
    help="Compress StarDict dictionary file (only for StarDict format)",
    show_default=True,
)
@click.option(
    "--version",
    "version",
    is_flag=True,
    default=False,
    help="Show version.",
    nargs=1,
)
@click.pass_context
def cli(  # noqa: PLR0913,PLR0915,C901,PLR0912,ARG001
    ctx: click.Context,
    in_lang: str | None,
    out_lang: str | None,
    export_format: str,
    merge_in_langs: str | None,
    title: str,
    shortname: str,
    outdir: str,
    kindlegen_path: str,
    max_entries: int,  # noqa: ARG001  # reserved for future use
    include_pos: bool | None,
    try_fix_inflections: bool | None,
    kindle_lang: str,
    cache_dir: str | None,
    reset_cache: bool,
    compress: bool,
    version: bool,
) -> None:
    """
    DictForge build a dictionary from Wiktionary (Wiktextract/Kaikki) in one go.

    Usage:
      \b
      dictforge IN_LANG [OUT_LANG] [OPTIONS...]
      dictforge init
    """
    # If subcommand is invoked (init), do nothing here.
    if ctx.invoked_subcommand is not None:
        return

    if in_lang == "init" and out_lang is None:
        ctx.invoke(cmd_init)
        return

    console = Console(stderr=True)

    if version:
        print(f"{__version__}")
        sys.exit(0)

    cfg = load_config()

    if not in_lang:
        raise click.UsageError(
            "Input language is required. "
            "Example: 'dictforge sr' or 'dictforge \"Serbo-Croatian\" en'",
        )

    # Validate export format
    available_formats = get_available_formats()
    if export_format not in available_formats:
        available_list = ", ".join(available_formats.keys())
        raise click.UsageError(
            f"Unknown export format '{export_format}'. Available: {available_list}",
        )

    in_lang_norm = normalize_input_name(in_lang)
    out_lang_norm = normalize_input_name(out_lang) if out_lang else cfg["default_out_lang"]

    # Build export options based on format
    export_options: dict[str, Any] = {}

    if export_format == "mobi":
        # MOBI-specific setup
        config_kindlegen = str(cfg.get("kindlegen_path") or "")
        kindlegen_input = kindlegen_path or config_kindlegen
        kindlegen = kindlegen_input or guess_kindlegen_path()
        if not kindlegen:
            error_message = Text("kindlegen not found; install ", style="bold red")
            error_message.append(
                "Kindle Previewer 3",
                style="link https://kdp.amazon.com/en_US/help/topic/G202131170",
            )
            error_message.append(" or pass --kindlegen-path", style="bold red")
            console.print(error_message)
            raise SystemExit(1)

        include_pos_val = cfg["include_pos"] if include_pos is None else True
        try_fix_val = cfg["try_fix_inflections"] if try_fix_inflections is None else True

        kindle_lang_code: str | None = None
        if kindle_lang:
            kindle_lang_name = normalize_input_name(kindle_lang)
            kindle_lang_code, _ = lang_meta(kindle_lang_name)

        export_options = {
            "kindlegen_path": kindlegen,
            "try_fix_inflections": try_fix_val,
            "kindle_lang_override": kindle_lang_code,
            "include_pos": include_pos_val,
        }
    elif export_format == "stardict":
        # StarDict-specific options
        export_options = {
            "compress": compress,
            "same_type_sequence": "h",  # HTML format
        }

    cache_dir_val = Path(cache_dir or cfg["cache_dir"])

    merge_arg = merge_in_langs if merge_in_langs is not None else cfg.get("merge_in_langs", "")
    merge_list = (
        [normalize_input_name(x.strip()) for x in merge_arg.split(",") if x.strip()]
        if merge_arg
        else []
    )

    dfl = make_defaults(in_lang_norm, out_lang_norm)
    title_val = title or dfl["title"]
    short_val = shortname or dfl["shortname"]
    outdir_path = Path(outdir or dfl["outdir"])
    outdir_path.mkdir(parents=True, exist_ok=True)

    b = Builder(cache_dir=cache_dir_val, show_progress=True)
    b.ensure_download_dirs(force=reset_cache)

    in_langs = [in_lang_norm] + merge_list
    start_label = ", ".join(in_langs)
    console.print(
        f"[dictforge] Starting build: {start_label} → {out_lang_norm} ({export_format})",
        style="cyan",
    )
    try:
        counts = b.build_dictionary(
            in_langs=in_langs,
            out_lang=out_lang_norm,
            title=title_val,
            shortname=short_val,
            outdir=outdir_path,
            export_format=export_format,
            export_options=export_options,
        )
    except KaikkiDownloadError as exc:
        console.print(Text(str(exc), style="bold red"))
        console.print(
            "Download the raw dump manually or retry later if the service is busy.",
            style="yellow",
        )
        raise SystemExit(1) from exc
    except KindleBuildError as exc:
        console.print(Text(str(exc), style="bold red"))
        console.print(
            (
                "Ensure the Kindle Previewer path is correct "
                "and that the metadata contains a valid language code."
            ),
            style="yellow",
        )
        raise SystemExit(1) from exc
    except ExportError as exc:
        console.print(Text(str(exc), style="bold red"))
        console.print(
            "Export failed. Check the error message above for details.",
            style="yellow",
        )
        raise SystemExit(1) from exc
    except KaikkiParseError as exc:
        console.print(Text(str(exc), style="bold red"))
        if getattr(exc, "excerpt", None):
            console.print(Text("Response excerpt:", style="yellow"))
            for line in exc.excerpt:
                console.print(Text(line, style="dim"))
        console.print(
            "Kaikki returned data that is not JSON (often HTML when offline or blocked).",
            style="yellow",
        )
        console.print(
            "Check your internet connection or pre-download datasets as described in the docs.",
            style="yellow",
        )
        raise SystemExit(1) from exc
    except JSONDecodeError as exc:
        error_message = Text(
            "Failed to parse Kaikki data; the download returned non-JSON ",
            style="bold red",
        )
        error_message.append("(often HTML when offline or blocked).")
        console.print(error_message)
        console.print(
            "Check your internet connection or pre-download datasets as described in the docs.",
            style="yellow",
        )
        raise SystemExit(1) from exc
    except ValueError as exc:
        console.print(Text(str(exc), style="bold red"))
        raise SystemExit(1) from exc

    click.secho(
        f"DONE: {outdir_path} (primary entries: {counts.get(in_lang_norm, 0)})",
        fg="green",
        bold=True,
    )
    for extra_lang, entry_count in counts.items():
        if extra_lang == in_lang_norm:
            continue
        click.echo(f"  extra {extra_lang}: {entry_count} entries")


@cli.command("init")
def cmd_init() -> None:
    """
    Interactive setup: choose default output language and save to config.
    """
    cfg = load_config()
    click.echo("dictforge init")
    click.echo("---------------------")
    click.echo(f"Current default_out_lang: {cfg.get('default_out_lang')}")
    val = click.prompt(
        "Enter default output language (e.g. English)",
        default=cfg.get("default_out_lang", "English"),
    )
    cfg["default_out_lang"] = val

    current_kindlegen = str(cfg.get("kindlegen_path") or "")
    guessed_kindlegen = guess_kindlegen_path()
    if guessed_kindlegen:
        click.echo(
            f"Detected Kindle Previewer kindlegen executable: {guessed_kindlegen}",
        )
    else:
        click.echo("Could not auto-detect the Kindle Previewer kindlegen executable.")
        if current_kindlegen:
            click.echo(f"Current configured path: {current_kindlegen}")
        click.echo("Common locations include:")
        click.echo("  • macOS:")
        click.echo("      /Applications/Kindle Previewer 3.app/Contents/MacOS/lib/fc/bin/kindlegen")
        click.echo("      /Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen")
        click.echo("  • Windows (local profile):")
        click.echo("      %LocalAppData%/Amazon/Kindle Previewer 3/lib/fc/bin/kindlegen.exe")
        click.echo("  • Windows (system install):")
        click.echo("      C:/Program Files/Amazon/Kindle Previewer 3/lib/fc/bin/kindlegen.exe")
        click.echo("  • Linux via Wine:")
        click.echo(
            "      ~/.wine/drive_c/Program Files/Amazon/"
            "Kindle Previewer 3/lib/fc/bin/kindlegen.exe",
        )

    kindlegen_default = current_kindlegen or guessed_kindlegen
    prompt_default = kindlegen_default or ""
    prompt_show_default = bool(kindlegen_default)
    kindlegen_path = click.prompt(
        "Enter Kindle Previewer kindlegen path",
        default=prompt_default,
        show_default=prompt_show_default,
    ).strip()
    if kindlegen_path and not Path(kindlegen_path).exists():
        click.echo(
            "Warning: the provided path does not currently exist. Please verify after setup.",
        )
    cfg["kindlegen_path"] = kindlegen_path

    save_config(cfg)
    _help_config_store["config"] = cfg.copy()
    click.secho(f"Saved: {config_path()}", fg="green", bold=True)
