# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                           |    Stmts |     Miss |   Cover |   Missing |
|------------------------------- | -------: | -------: | ------: | --------: |
| src/dictforge/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/dictforge/builder.py       |      479 |      205 |     57% |216-217, 222-238, 245, 248-249, 252, 255, 258, 261-266, 277-279, 285-287, 290-293, 297-299, 303, 307-308, 322-336, 358-391, 417-452, 458-459, 470, 472, 480, 499, 505-514, 518, 528, 536-541, 546, 552, 565, 570-578, 591, 630-642, 676-681, 698, 701-702, 705, 712, 715-717, 756, 758, 760-777, 780, 832-851, 857-865, 920-924, 954-958, 965-970, 976, 1013-1015 |
| src/dictforge/config.py        |       38 |        3 |     92% |  9-10, 50 |
| src/dictforge/kaikki.py        |      261 |      210 |     20% |38-47, 51-52, 55-57, 60-77, 99, 103-130, 133-212, 220-250, 253-307, 310-334, 337, 345-368, 372, 376, 380, 383-389, 393 |
| src/dictforge/kindle.py        |       16 |        0 |    100% |           |
| src/dictforge/langutil.py      |       21 |        1 |     95% |        39 |
| src/dictforge/main.py          |      112 |       22 |     80% |95, 138-139, 176-212 |
| src/dictforge/tatoeba.py       |      294 |      220 |     25% |66-67, 80-81, 84-89, 92-95, 99-152, 155-171, 178-216, 219-238, 241-260, 263-288, 295-300, 303-324, 328-332, 336-343, 347-351, 355-358, 362-366, 374-385, 388-392, 404 |
| src/dictforge/translit.py      |       47 |       37 |     21% |52-76, 80-95 |
|                      **TOTAL** | **1269** |  **698** | **45%** |           |


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