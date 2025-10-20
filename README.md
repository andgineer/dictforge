# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                           |    Stmts |     Miss |   Cover |   Missing |
|------------------------------- | -------: | -------: | ------: | --------: |
| src/dictforge/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/dictforge/builder.py       |      327 |      270 |     17% |189-198, 202-203, 206-208, 211-228, 249, 252, 255, 258-280, 283-327, 334-357, 365-384, 387-406, 409-464, 478-494, 509-557, 566-636, 639-650, 668-700 |
| src/dictforge/config.py        |       38 |       27 |     29% |9-10, 22-23, 27, 31-38, 43-57 |
| src/dictforge/kindle.py        |       16 |       12 |     25% |      8-26 |
| src/dictforge/langutil.py      |       21 |       13 |     38% |38-41, 45-46, 50-61 |
| src/dictforge/main.py          |      109 |       68 |     38% |88, 96-210, 218-228 |
|                      **TOTAL** |  **512** |  **390** | **24%** |           |


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