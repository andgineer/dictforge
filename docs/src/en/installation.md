# Installation
## Installing pipx
[`pipx`](https://pypa.github.io/pipx/) creates isolated environments to avoid conflicts with existing system packages.

=== "macOS"
    Run in the terminal:
    ```bash
    --8<-- "install_pipx_macos.sh"
    ```

=== "Linux"
    First, ensure Python is installed.
    ```bash
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    ```

=== "Windows"
    First, install Python if it's not already installed.
    ```bash
    python -m pip install --user pipx
    ```

## Installing `dictforge`
Run in the terminal or command prompt:

```bash
pipx install dictforge
```

## Installing Kindle Previewer

`dictforge` invokes Amazon's `kindlegen` utility to generate Kindle dictionaries (MOBI format). Install
[Kindle Previewer 3](https://kdp.amazon.com/en_US/help/topic/G202131170).

Launch Kindle Previewer once after installation to extract the embedded `kindlegen` binary.

In newer versions of Kindle Previewer 3, Amazon has stopped distributing kindlegen as a separate utility — it is embedded
within Kindle Previewer itself and is not installed globally on the system.

### Configuring kindlegen path

You can configure the path to `kindlegen` once using the `init` command, and then you won't need to specify it in every build:

```bash
dictforge init
```

The command will prompt you for the `kindlegen` path. Common locations:

=== "macOS"
    /Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen

=== "Windows"
    %LocalAppData%\Amazon\Kindle Previewer 3\lib\fc\bin\kindlegen.exe

Alternatively, you can provide the path directly when running `dictforge` using the `--kindlegen-path` option.

More details: [Installing Kindlegen](https://www.jutoh.com/kindlegen.html).
