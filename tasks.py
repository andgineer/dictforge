import os
import shutil
import sys

from invoke import task, Context, Collection
import time


def get_allowed_doc_languages():
    build_docs_file_name = "scripts/build-docs.sh"
    try:
        with open(build_docs_file_name, "r") as f:
            for line in f:
                if "for lang in" in line:
                    langs = line.split("in")[1].strip().split(";")[0].split()
                    return [lang.strip() for lang in langs]
    except FileNotFoundError:
        print(f"No {build_docs_file_name} file found")
    return ["en", "bg", "de", "es", "fr", "ru"]  # default


ALLOWED_DOC_LANGUAGES = get_allowed_doc_languages()
ALLOWED_VERSION_TYPES = ["release", "bug", "feature"]


@task
def version(_c: Context):
    """Show the current version."""
    with open("src/dictforge/__about__.py", "r") as f:
        version_line = f.readline()
        version_num = version_line.split('"')[1]
        print(version_num)
        return version_num


def ver_task_factory(version_type: str):
    @task
    def ver(c: Context):
        """Bump the version."""
        c.run(f"./scripts/verup.sh {version_type}")

    return ver


@task
def reqs(c: Context):
    """Upgrade requirements including pre-commit."""
    c.run("pre-commit autoupdate")
    c.run("uv lock --upgrade")

def docs_task_factory(language: str):
    @task
    def docs(c: Context):
        """Docs preview for the language specified."""
        c.run("open -a 'Google Chrome' http://127.0.0.1:8000/dictforge/")
        c.run(f"scripts/docs-render-config.sh {language}")
        if language != "en":
            shutil.rmtree(f"./docs/src/{language}/images", ignore_errors=True)
            shutil.copytree("./docs/src/en/images", f"./docs/src/{language}/images")
            shutil.copy("./docs/src/en/reference.md", f"./docs/src/{language}/reference.md")
        c.run("mkdocs serve -f docs/_mkdocs.yml")

    return docs


@task
def uv(c: Context):
    """Install or upgrade uv."""
    c.run("curl -LsSf https://astral.sh/uv/install.sh | sh")

@task
def pre(c):
    """Run pre-commit checks"""
    c.run("pre-commit run --verbose --all-files")



namespace = Collection.from_module(sys.modules[__name__])
for name in ALLOWED_VERSION_TYPES:
    namespace.add_task(ver_task_factory(name), name=f"ver-{name}")
for name in ALLOWED_DOC_LANGUAGES:
    namespace.add_task(docs_task_factory(name), name=f"docs-{name}")
