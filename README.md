# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                           |    Stmts |     Miss |   Cover |   Missing |
|------------------------------- | -------: | -------: | ------: | --------: |
| src/dictforge/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/dictforge/builder.py       |      538 |      174 |     68% |228, 232-233, 241, 253-258, 284-285, 290-306, 313, 316-317, 320-325, 335-339, 342-346, 349-351, 358-359, 363, 366-369, 382-396, 418-451, 483-510, 513-517, 528, 530, 560-561, 582, 592, 603-605, 613-614, 623-624, 645, 652, 655-656, 673, 686-687, 693-728, 744-745, 763, 776, 819, 853-857, 883-885, 897, 908, 944, 957, 964, 1000 |
| src/dictforge/config.py        |       38 |        3 |     92% |  9-10, 50 |
| src/dictforge/kindle.py        |       16 |        0 |    100% |           |
| src/dictforge/langutil.py      |       21 |        1 |     95% |        39 |
| src/dictforge/main.py          |      111 |       22 |     80% |88, 131-132, 169-205 |
|                      **TOTAL** |  **725** |  **200** | **72%** |           |


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