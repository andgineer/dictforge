# dictforge

Forge Kindle-compatible dictionaries for every language


### Quick Start

Install Kindle Previewer 3 first

```
wikidict-kindle sr en
```

#### Load the dictionary onto your Kindle

Connect your Kindle over USB (it appears as a drive).

Copy the .mobi/.azw3 dictionary file to:

Documents/Dictionaries (preferred), or just Documents if the folder doesn’t exist.

On the Kindle:

Settings → Language & Dictionaries → Dictionaries

Select the input language group (e.g., Serbian / Serbo-Croatian).

Choose your new dictionary as the default for that group.

Open a Serbian/Serbo-Croatian text and tap a word to see the lookup.

set default output language (e.g., English)
```
dictforge --init
```

to see all available options.

```bash
dictforge --help
```


!!! info "About"
    ![About](images/about.jpg)
    [About][dictforge.__about__]
