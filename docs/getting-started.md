# Getting started

## Requirements

The tested target is macOS GaussView 6.0.16, installed at `~/Applications/GaussView6/gview.app`. Install [uv](https://docs.astral.sh/uv/) and allow Accessibility and Screen Recording for the terminal or application invoking Python. Existing Gaussian files must be available locally. GVU opens results and prepares displays; running the examples does not submit a Gaussian job.

Install GVU from PyPI in a project with `uv add gvu`, or use the inline metadata below to let `uv run viewer.py` install it automatically. A source checkout is needed only for development; see the [development guide](development.md). Importing the library and building its documentation also work on Linux, but interactive viewer controls require macOS.

## Open a run

A calculation directory can include a `scripts/viewer.py` entry point. Run its existing script from anywhere with an absolute path:

```bash
uv run /absolute/path/to/project/runs/<timestamp>/scripts/viewer.py
```

| Option | Effect |
| --- | --- |
| `--check` | Validate files and applicable result markers without opening GaussView |
| `--new` | Request fresh views rather than reusing configured results |
| `--verbose` | Include diagnostic JSON Lines events on stderr |
| `--app /path/to/gview.app` | Select another application installation |

Ignored checkpoints and cube grids may need to be obtained separately from the calculation server. A Git checkout alone may not contain all of a workflow's data.

## Write a viewer

Place this entry point beside your calculation or under its `scripts/` directory. Its inline dependency metadata installs GVU from PyPI, without a local source checkout.

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["gvu>=0.3.0,<0.4"]
# ///
from pathlib import Path
from gvu import Alignment, Result, Workflow


def main():
    run = Path(__file__).resolve().parent.parent
    workflow = Workflow(
       source=run / "logs/optimization.log",
       results=(Result.OPTIMIZATION, Result.VIBRATIONS),
       alignment=Alignment("X", "Y"),
    )
    workflow.view()


if __name__ == "__main__":
    main()
```

Choose results that the calculation actually contains. Use only `source` for an input-geometry viewer. Run `--check` first, then open the viewer. The [viewing guide](workflows.md) explains surfaces, comparisons and ownership; the [menu guide](controls.md) explains actions outside the specialized helpers.
