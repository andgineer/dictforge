# dictforge

Forge Kindle-ready dictionaries for every language

## Quick start

[Install the utility](installation.md)

```bash
dictforge --kindlegen-path "/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen" sr en
```

- On the first run, dictforge downloads the Wiktionary dump (~20 GB compressed); subsequent runs reuse it.
- The example command builds a Serbo-Croatian → English dictionary in the `build/` folder.
- Copy the generated MOBI file to `Documents/Dictionaries/` on your Kindle, or to `Documents/` if `Dictionaries` is missing.
- While reading, long-press a word to reveal the dictionary. Because Kindle does not support some languages, such as Serbian,
you may need to select the dictionary manually the first time via `Dictionary` → `Select new dictionary`.
