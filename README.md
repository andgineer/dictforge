# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                            |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------- | -------: | -------: | ------: | --------: |
| src/dictforge/\_\_about\_\_.py  |        1 |        0 |    100% |           |
| src/dictforge/builder.py        |      435 |      134 |     69% |190-195, 256, 264-269, 282-286, 290-294, 298-300, 314, 318-321, 337-351, 376-409, 458-485, 489-493, 505, 507, 538, 541-542, 547, 553-554, 559, 573, 579, 582, 597, 602, 610, 616, 622, 626-627, 672, 707-711, 737-739, 751, 762, 799, 812, 819, 856 |
| src/dictforge/config.py         |       38 |        3 |     92% |  9-10, 54 |
| src/dictforge/kindlegen.py      |       16 |        0 |    100% |           |
| src/dictforge/langutil.py       |       21 |        1 |     95% |        40 |
| src/dictforge/main.py           |      113 |       22 |     81% |95, 138-139, 177-213 |
| src/dictforge/source\_base.py   |       24 |        3 |     88% |24, 32, 39 |
| src/dictforge/source\_kaikki.py |      265 |       49 |     82% |66, 70-71, 79, 148-149, 170, 178-213, 230-231, 253, 270, 311, 314-315, 324, 335-337, 345-346, 355-356, 378, 385, 388-389, 419-420 |
| src/dictforge/tatoeba.py        |      294 |      294 |      0% |     1-405 |
| src/dictforge/translit.py       |       47 |       47 |      0% |      3-98 |
|                       **TOTAL** | **1254** |  **553** | **56%** |           |


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