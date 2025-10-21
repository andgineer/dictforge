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

### Kindle language workarounds

Kindle links a dictionary automatically based on the language stored in the ebook metadata.

Unfortunately the reader supports only a narrow list of languages for dictionaries – see Amazon’s
[supported Kindle language list](https://wiki.mobileread.com/wiki/Amazon_Kindle#Supported_languages).

Pick any (otherwise unused) supported language both in the `--kindle-lang` option and, preferably, in the book metadata;
the dictionary will then attach automatically.

If you use [Calibre](https://calibre-ebook.com/), set that language before converting the book to MOBI.
