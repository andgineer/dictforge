# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                            |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------- | -------: | -------: | ------: | --------: |
| src/dictforge/\_\_about\_\_.py  |        1 |        0 |    100% |           |
| src/dictforge/builder.py        |      256 |       35 |     86% |69-73, 85, 87, 118, 121-122, 127, 133-134, 139, 154, 159, 167, 173, 179, 183-184, 237-241, 270-272, 284, 295, 332, 345, 352, 389 |
| src/dictforge/config.py         |       38 |        3 |     92% |  9-10, 55 |
| src/dictforge/kindle.py         |       19 |        1 |     95% |       181 |
| src/dictforge/kindlegen.py      |       16 |        0 |    100% |           |
| src/dictforge/langutil.py       |       21 |        1 |     95% |        40 |
| src/dictforge/main.py           |      152 |       25 |     84% |37, 40, 141, 190-191, 228-264, 301 |
| src/dictforge/progress\_bar.py  |      162 |       25 |     85% |24-29, 95, 103-108, 122, 125, 130, 133, 139, 157-160, 277, 279, 282 |
| src/dictforge/source\_base.py   |       30 |        2 |     93% |    28, 48 |
| src/dictforge/source\_kaikki.py |      289 |       52 |     82% |93, 97-98, 106, 145, 152, 159, 198-199, 220, 228-263, 280-281, 303, 320, 353, 356-357, 366, 377-379, 387-388, 397-398, 420, 427, 430-431, 461-462 |
| src/dictforge/translit.py       |       47 |       47 |      0% |      3-98 |
|                       **TOTAL** | **1031** |  **191** | **81%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/andgineer/dictforge/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/andgineer/dictforge/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fandgineer%2Fdictforge%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.