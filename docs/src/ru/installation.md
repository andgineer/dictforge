# Установка

## Установка pipx
[`pipx`](https://pypa.github.io/pipx/) создаёт изолированные окружения, чтобы избежать конфликтов с системными пакетами.

=== "macOS"
    Выполните в терминале:
    ```bash
    --8<-- "install_pipx_macos.sh"
    ```

=== "Linux"
    Сначала убедитесь, что установлен Python.
    ```bash
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    ```

=== "Windows"
    Сначала установите Python, если он ещё не установлен.
    ```bash
    python -m pip install --user pipx
    ```

## Установка dictforge
Выполните в терминале или командной строке:

```bash
pipx install dictforge
```

## Установка Kindle Previewer

`dictforge` использует утилиту Amazon `kindlegen` для сборки словарей Kindle (формат MOBI). Установите
[Kindle Previewer 3](https://kdp.amazon.com/en_US/help/topic/G202131170).

Запустите Kindle Previewer один раз после установки, чтобы распаковать встроенный бинарник `kindlegen`.

В новых версиях Kindle Previewer 3 Amazon перестала распространять kindlegen как отдельную утилиту — она встроена
в Kindle Previewer и не устанавливается глобально.

### Настройка пути к kindlegen

Вы можете настроить путь к `kindlegen` один раз с помощью команды `init`, и затем не нужно будет указывать его при каждой сборке:

```bash
dictforge init
```

Команда запросит путь к `kindlegen`. Типичные расположения:

=== "macOS"
    /Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen

=== "Windows"
    %LocalAppData%\\Amazon\\Kindle Previewer 3\\lib\\fc\\bin\\kindlegen.exe

Альтернативно, вы можете указать путь напрямую при запуске `dictforge` с помощью опции `--kindlegen-path`.

Подробнее: [Installing Kindlegen](https://www.jutoh.com/kindlegen.html).
