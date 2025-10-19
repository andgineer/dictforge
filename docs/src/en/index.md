# dictforge

Forge Kindle-ready dictionaries for every language

## Quick start

[Install the utility](installation.md)

```bash
dictforge --kindlegen-path "/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen" sr en
```

- First run downloads the Wiki Dictinary (~20GB compressed); subsequent runs reuse it.
- The command example creates the dictionary for Serbo-Croatian → English in folder `build\`.
- Copy the generated MOBI-file to `Documents/Dictionaries/` on your Kindle or just to `Documents/` if no `Dictionaries` folder exists.
- Reading the book long-presses a word shows the dictionary. As Kindle does not support a lot of languages, like Serbian,
first time you should select the dictionary manually via `Dictionary` -> `Select new dictionary`.
