# GVU

Python automation for GaussView 6 on macOS. Load and compare structures, inspect native menus and enabled actions, align models, control animations, map density/ESP surfaces and arrange windows through one shared API.

GVU requires a separately installed GaussView application. The tested version is GaussView 6.0.16. Accessibility and Screen Recording permissions are required for the application invoking Python.

## Install

```bash
uv add gvu
```

For a standalone viewer script, let uv install the published package automatically:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["gvu>=0.3.0,<0.4"]
# ///
from pathlib import Path
from gvu import Alignment, Workflow


def main():
    workflow = Workflow(
       source=Path(__file__).resolve().parent / "molecule.gjf",
       alignment=Alignment("X", "Y"),
    )
    workflow.view()


if __name__ == "__main__":
    main()
```

Run it with `uv run viewer.py`. Use `workflow.validate()` for data validation, or `workflow.view(fresh=True, verbose=True)` to open fresh views with diagnostic JSON Lines events. Select an installation with `workflow.view(app=Path("/path/to/gview.app"))`.

## Documentation

Start with the [documentation](https://ghovax.github.io/gvu/) or browse its [source index](https://github.com/ghovax/gvu/blob/main/docs/index.md):

- [Getting started](https://ghovax.github.io/gvu/getting-started.html) for installation and viewer scripts.
- [Viewing workflows](https://ghovax.github.io/gvu/workflows.html) for comparisons, alignment, playback and surfaces.
- [Menus and controls](https://ghovax.github.io/gvu/controls.html) and the [menu reference](https://ghovax.github.io/gvu/menus.html) for native actions and their state.
- [API reference](https://ghovax.github.io/gvu/api.html) for public classes and signatures.
- [Coverage and troubleshooting](https://ghovax.github.io/gvu/coverage.html) for tested behavior and current limitations.
- [Development](https://ghovax.github.io/gvu/development.html) for checks, documentation builds and releases.

Menu discovery does not establish complete automation of every dialog. Unavailable or ambiguous actions must be reported explicitly; preference fields, arbitrary context menus and some specialist controls remain incomplete or unverified.

## Develop

```bash
git clone https://github.com/ghovax/gvu.git
cd gvu
uv sync --extra docs
uv run python -m unittest discover -s tests
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

The documentation uses Sphinx, MyST and the Read the Docs theme. Open `docs/_build/html/index.html` after building. GitHub Pages publishes the site, and `.readthedocs.yaml` also supports importing this repository into Read the Docs.

Released wheels and source distributions contain the Python library, not the GaussView application or Gaussian calculation data. GVU is distributed under the [MIT license](https://github.com/ghovax/gvu/blob/main/LICENSE).
