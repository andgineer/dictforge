[![Build Status](https://github.com/andgineer/dictforge/workflows/CI/badge.svg)](https://github.com/andgineer/dictforge/actions)
[![Coverage](https://raw.githubusercontent.com/andgineer/dictforge/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/andgineer/dictforge/blob/python-coverage-comment-action-data/htmlcov/index.html)
# dictforge

Forge Kindle-compatible dictionaries for every language

# Documentation

[Dictforge](https://andgineer.github.io/dictforge/)



# Developers

Do not forget to run `. ./activate.sh`.

For work it need [uv](https://github.com/astral-sh/uv) installed.

Use [pre-commit](https://pre-commit.com/#install) hooks for code quality:

    pre-commit install

## Allure test report

* [Allure report](https://andgineer.github.io/dictforge/builds/tests/)

# Scripts

Install [invoke](https://docs.pyinvoke.org/en/stable/) preferably with [pipx](https://pypa.github.io/pipx/):

    pipx install invoke

For a list of available scripts run:

    invoke --list

For more information about a script run:

    invoke <script> --help


## Coverage report
* [Coveralls](https://coveralls.io/github/andgineer/dictforge)

> Created with cookiecutter using [template](https://github.com/andgineer/cookiecutter-python-package)
