from __future__ import annotations
from pathlib import Path
import rich_click as click

from .builder import Builder
from .config import load_config, save_config, config_path
from .kindle import guess_kindlegen_path
from .langutil import normalize_input_name, make_defaults

# rich-click styling
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.MAX_WIDTH = 100
click.rich_click.STYLE_HELPTEXT = "dim"
click.rich_click.STYLE_OPTION = "bold"
click.rich_click.STYLE_SWITCH = "bold"
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True

@click.group(invoke_without_command=True, context_settings=dict(ignore_unknown_options=False))
@click.argument("in_lang", required=False)
@click.argument("out_lang", required=False)
@click.option("--merge-in-langs", default=None, help="Comma-separated extra input languages to merge (overrides config)")
@click.option("--title", default="", help="Override auto title")
@click.option("--shortname", default="", help="Override auto short name")
@click.option("--outdir", default="", help="Override auto output directory")
@click.option("--kindlegen-path", default="", help="Path to kindlegen (auto-detect if empty)")
@click.option("--max-entries", type=int, default=0, help="Debug: limit number of entries")
@click.option("--include-pos", is_flag=True, default=None, help="Include part-of-speech headers")
@click.option("--try-fix-inflections", is_flag=True, default=None, help="Fix lookup for inflections (mostly Latin scripts)")
@click.option("--cache-dir", default=None, help="Cache directory for downloaded JSONL")
@click.pass_context
def cli(ctx,
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
        cache_dir: str | None):
    """
    [bold]wikidict-kindle[/bold]: build a Kindle dictionary from Wiktionary (Wiktextract/Kaikki) in one go.

    Usage:
      \b
      wikidict-kindle IN_LANG [OUT_LANG] [OPTIONS...]
      wikidict-kindle init
    """
    # If subcommand is invoked (init), do nothing here.
    if ctx.invoked_subcommand is not None:
        return

    cfg = load_config()

    if not in_lang:
        raise click.UsageError("Input language is required. Example: 'wikidict-kindle sr' or 'wikidict-kindle \"Serbo-Croatian\" en'")

    in_lang_norm = normalize_input_name(in_lang)
    out_lang_norm = normalize_input_name(out_lang) if out_lang else cfg["default_out_lang"]

    kindlegen = kindlegen_path or guess_kindlegen_path()
    if not kindlegen:
        raise click.ClickException("kindlegen not found; install Kindle Previewer 3 or pass --kindlegen-path")

    include_pos_val = cfg["include_pos"] if include_pos is None else True
    try_fix_val = cfg["try_fix_inflections"] if try_fix_inflections is None else True
    cache_dir_val = Path(cache_dir or cfg["cache_dir"])

    merge_arg = merge_in_langs if merge_in_langs is not None else cfg.get("merge_in_langs", "")
    merge_list = [normalize_input_name(x.strip()) for x in merge_arg.split(",") if x.strip()] if merge_arg else []

    dfl = make_defaults(in_lang_norm, out_lang_norm)
    title_val = title or dfl["title"]
    short_val = shortname or dfl["shortname"]
    outdir_path = Path(outdir or dfl["outdir"])
    outdir_path.mkdir(parents=True, exist_ok=True)

    b = Builder(cache_dir=cache_dir_val)
    b.ensure_download(force=False)

    in_langs = [in_lang_norm] + merge_list
    b.build_dictionary(
        in_langs=in_langs,
        out_lang=out_lang_norm,
        title=title_val,
        shortname=short_val,
        outdir=outdir_path,
        kindlegen_path=kindlegen,
        include_pos=include_pos_val,
        try_fix_inflections=try_fix_val,
        max_entries=max_entries,
    )
    click.secho(f"DONE: {outdir_path}", fg="green", bold=True)

@cli.command("init")
def cmd_init():
    """
    Interactive setup: choose default output language and save to config.
    """
    cfg = load_config()
    click.echo("wikidict-kindle init")
    click.echo("---------------------")
    click.echo(f"Current default_out_lang: {cfg.get('default_out_lang')}")
    val = click.prompt("Enter default output language (e.g. English)", default=cfg.get("default_out_lang", "English"))
    cfg["default_out_lang"] = val
    save_config(cfg)
    click.secho(f"Saved: {config_path()}", fg="green", bold=True)
