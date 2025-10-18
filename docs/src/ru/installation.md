## Установка

## Установка pipx
[`pipx`](https://pypa.github.io/pipx/) создает изолированные среды, чтобы избежать конфликтов с
существующими системными пакетами.

=== "MacOS"
    В терминале выполните:
    ```bash
    brew install pipx
    pipx ensurepath
    ```

=== "Linux"
    Сначала убедитесь, что Python установлен.

    Введите в терминал:

    ```bash
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    ```

=== "Windows"
    Сначала установите Python, если он еще не установлен.

    В командной строке введите (если Python был установлен из Microsoft Store, используйте `python3` вместо `python`):

    ```bash
    python -m pip install --user pipx
    ```

## Установка `dictforge`:
В терминале (командной строке) выполните:

```bash
pipx install dictforge
```

## Kindle Previewer
DictForge использует служебную программу `kindlegen` для сборки словарей Kindle. Установите
[Kindle Previewer 3](https://kdp.amazon.com/en_US/help/topic/G202131170), чтобы получить
эту утилиту и добавить её в PATH.

С версии Kindle Previewer 3, Amazon перестала распространять kindlegen как отдельную утилиту — теперь она встроена
в сам Kindle Previewer и не устанавливается глобально в систему.

В статье [Installing Kindlegen](https://www.jutoh.com/kindlegen.html) описано как найти путь к ней.

Указывайте путь перед языковыми аргументами:

```bash
dictforge --kindlegen-path="/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen" sr en
```
