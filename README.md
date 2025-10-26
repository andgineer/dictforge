# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                            |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------- | -------: | -------: | ------: | --------: |
| src/dictforge/\_\_about\_\_.py  |        1 |        0 |    100% |           |
| src/dictforge/builder.py        |      408 |      142 |     65% |189-194, 220-221, 226-242, 249, 252-253, 256-261, 271-275, 278-282, 285-287, 294-295, 299, 302-305, 318-332, 354-387, 432-459, 462-466, 477, 479, 488, 504, 507-508, 511, 517-518, 523, 537, 542, 550, 556, 561, 565-566, 608, 642-646, 672-674, 686, 697, 733, 746, 753, 789 |
| src/dictforge/config.py         |       38 |        3 |     92% |  9-10, 50 |
| src/dictforge/kaikki.py         |      261 |      261 |      0% |     1-393 |
| src/dictforge/kindlegen.py      |       16 |        0 |    100% |           |
| src/dictforge/langutil.py       |       21 |        1 |     95% |        39 |
| src/dictforge/main.py           |      112 |       22 |     80% |95, 138-139, 176-212 |
| src/dictforge/source\_base.py   |        4 |        0 |    100% |           |
| src/dictforge/source\_kaikki.py |      238 |       50 |     79% |61, 65-66, 74, 108-110, 134-135, 156, 163-198, 214-215, 233, 246, 267, 278-280, 288-289, 298-299, 320, 327, 330-331, 348, 361-362 |
| src/dictforge/tatoeba.py        |      294 |      294 |      0% |     1-405 |
| src/dictforge/translit.py       |       47 |       47 |      0% |      3-98 |
|                       **TOTAL** | **1440** |  **820** | **43%** |           |


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