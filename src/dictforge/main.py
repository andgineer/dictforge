from __future__ import annotations

import sys
from json import JSONDecodeError
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.text import Text

from dictforge import __version__

from .builder import Builder, KaikkiDownloadError, KaikkiParseError, KindleBuildError
from .config import config_path, load_config, save_config
from .kindlegen import guess_kindlegen_path
from .langutil import lang_meta, make_defaults, normalize_input_name

# rich-click styling
click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.MAX_WIDTH = 100
click.rich_click.STYLE_HELPTEXT = "dim"
click.rich_click.STYLE_OPTION = "bold"
click.rich_click.STYLE_SWITCH = "bold"
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True


@click.group(invoke_without_command=True, context_settings={"ignore_unknown_options": False})
@click.argument("in_lang", required=False)
@click.argument("out_lang", required=False)
@click.option(
    "--merge-in-langs",
    default=None,
    help="Comma-separated extra input languages to merge (overrides config)",
)
@click.option("--title", default="", help="Override auto title")
@click.option("--shortname", default="", help="Override auto short name")
@click.option("--outdir", default="", help="Override auto output directory")
@click.option("--kindlegen-path", default="", help="Path to kindlegen (auto-detect if empty)")
@click.option("--max-entries", type=int, default=0, help="Debug: limit number of entries")
@click.option("--include-pos", is_flag=True, default=None, help="Include part-of-speech headers")
@click.option(
    "--try-fix-inflections",
    is_flag=True,
    default=None,
    help="Fix lookup for inflections (mostly Latin scripts)",
)
@click.option(
    "--kindle-lang",
    default="",
    help="Override Kindle dictionary language code if your target language is unsupported",
)
@click.option("--cache-dir", default=None, help="Cache directory for downloaded JSONL")
@click.option(
    "--reset-cache",
    is_flag=True,
    default=False,
    help="Force re-download of cached sources",
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
def cli(  # noqa: PLR0913,PLR0915,C901,PLR0912
    ctx: click.Context,
    in_lang: str | None,
    out_lang: str | None,
    merge_in_langs: str | None,
    title: str,
    shortname: str,
    outdir: str,
    kindlegen_path: str,
    max_entries: int,
    include_pos: bool | None,
    try_fix_inflections: bool | None,
    kindle_lang: str,
    cache_dir: str | None,
    reset_cache: bool,
    version: bool,
) -> None:
    """
    DictForge build a Kindle dictionary from Wiktionary (Wiktextract/Kaikki) in one go.

    Usage:
      \b
      dictforge IN_LANG [OUT_LANG] [OPTIONS...]
      dictforge init
    """
    # If subcommand is invoked (init), do nothing here.
    if ctx.invoked_subcommand is not None:
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

    in_lang_norm = normalize_input_name(in_lang)
    out_lang_norm = normalize_input_name(out_lang) if out_lang else cfg["default_out_lang"]

    kindlegen = kindlegen_path or guess_kindlegen_path()
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
    cache_dir_val = Path(cache_dir or cfg["cache_dir"])

    merge_arg = merge_in_langs if merge_in_langs is not None else cfg.get("merge_in_langs", "")
    merge_list = (
        [normalize_input_name(x.strip()) for x in merge_arg.split(",") if x.strip()]
        if merge_arg
        else []
    )

    kindle_lang_code: str | None = None
    if kindle_lang:
        kindle_lang_name = normalize_input_name(kindle_lang)
        kindle_lang_code, _ = lang_meta(kindle_lang_name)

    dfl = make_defaults(in_lang_norm, out_lang_norm)
    title_val = title or dfl["title"]
    short_val = shortname or dfl["shortname"]
    outdir_path = Path(outdir or dfl["outdir"])
    outdir_path.mkdir(parents=True, exist_ok=True)

    b = Builder(cache_dir=cache_dir_val, show_progress=True)  # reset_cache=reset_cache
    b.ensure_download(force=False)

    in_langs = [in_lang_norm] + merge_list
    start_label = ", ".join(in_langs)
    console.print(
        f"[dictforge] Starting build: {start_label} → {out_lang_norm}",
        style="cyan",
    )
    try:
        counts = b.build_dictionary(
            in_langs=in_langs,
            out_lang=out_lang_norm,
            title=title_val,
            shortname=short_val,
            outdir=outdir_path,
            kindlegen_path=kindlegen,
            include_pos=include_pos_val,
            try_fix_inflections=try_fix_val,
            max_entries=max_entries,
            kindle_lang_override=kindle_lang_code,
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
    save_config(cfg)
    click.secho(f"Saved: {config_path()}", fg="green", bold=True)
