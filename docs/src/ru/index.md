# dictforge

Создавайте словари для Kindle на любом языке.

## Быстрый старт

[Установите утилиту](installation.md)

```bash
dictforge --kindlegen-path "/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen" sr en
```

- При первом запуске dictforge скачивает дамп Викисловаря (≈20 ГБ в сжатом виде); последующие сборки используют его повторно.
- Пример команды собирает сербско-хорватский → английский словарь в каталоге `build/`.
- Скопируйте полученный MOBI-файл в `Documents/Dictionaries/` на Kindle либо в `Documents/`, если каталога `Dictionaries` нет.
- Во время чтения зажмите слово, чтобы открыть словарь. Поскольку Kindle не поддерживает некоторые языки, например сербский,
  при первом использовании выберите словарь вручную через `Dictionary` → `Select new dictionary`.
