# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                              |    Stmts |     Miss |   Cover |   Missing |
|---------------------------------- | -------: | -------: | ------: | --------: |
| src/dictforge/\_\_about\_\_.py    |        1 |        0 |    100% |           |
| src/dictforge/builder.py          |      172 |       16 |     91% |112, 115-116, 121, 135-136, 141, 171, 179, 189, 203, 213-214, 237-238, 303 |
| src/dictforge/config.py           |       37 |        3 |     92% |   7-8, 54 |
| src/dictforge/export\_base.py     |       21 |        0 |    100% |           |
| src/dictforge/export\_mobi.py     |      155 |       23 |     85% |53, 58, 73, 77, 148-152, 168-172, 212-214, 226, 239, 276, 289, 296, 333 |
| src/dictforge/export\_stardict.py |      169 |       71 |     58% |30, 35, 48, 104-106, 156, 160-161, 165, 226, 230-232, 242, 248, 256, 263-265, 269-287, 291-297, 303, 307-328, 332-338, 357-371 |
| src/dictforge/kaikki\_utils.py    |       23 |        1 |     96% |        49 |
| src/dictforge/kindle.py           |       18 |        1 |     94% |       179 |
| src/dictforge/kindlegen.py        |       16 |        0 |    100% |           |
| src/dictforge/main.py             |      188 |       42 |     78% |49, 52, 188, 211-212, 242-243, 251-253, 276-289, 324-370, 407 |
| src/dictforge/progress\_bar.py    |      178 |       26 |     85% |22-27, 93, 101-106, 120, 123, 128, 131, 137, 155-158, 164, 313, 315, 318 |
| src/dictforge/source\_base.py     |       29 |        1 |     97% |        46 |
| src/dictforge/source\_freedict.py |      475 |      165 |     65% |144, 147, 151, 154, 159, 173-181, 200, 212-213, 228-232, 239-246, 258, 274-276, 310, 325-326, 386-395, 404-409, 445-451, 458-480, 483, 494-495, 521-522, 544, 575-617, 674-678, 698, 705, 715, 719, 726, 757-758, 776-779, 786, 791-792, 797, 821-824, 829, 834-835, 877, 891-1018 |
| src/dictforge/source\_kaikki.py   |      284 |       52 |     82% |91, 95-96, 104, 143, 150, 157, 196-197, 218, 226-261, 278-279, 301, 318, 351, 354-355, 364, 375-377, 385-386, 395-396, 418, 425, 428-429, 459-460 |
| src/dictforge/translit.py         |       46 |        0 |    100% |           |
|                         **TOTAL** | **1812** |  **401** | **78%** |           |


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