# Getting started

## Requirements

Requirements for the tested setup:

- macOS GaussView 6.0.16 at `~/Applications/GaussView6/gview.app`.
- [uv](https://docs.astral.sh/uv/) for installation and script execution.
- Accessibility and Screen Recording permissions for the terminal or application invoking Python.
- Existing Gaussian files available locally.

GVU opens results and prepares displays; running the examples does not submit a Gaussian job.

Install GVU from PyPI in a project with `uv add gvu`, or use the inline metadata below to let `uv run viewer.py` install it automatically. A source checkout is needed only for development; see the [development guide](development.md). Importing the library and building its documentation also work on Linux, but interactive viewer controls require macOS.

## Open a run

A calculation directory can include a `scripts/viewer.py` entry point. Run its existing script from anywhere with an absolute path:

```bash
uv run /absolute/path/to/project/runs/<timestamp>/scripts/viewer.py
```

Configure the workflow through Python methods in the script:

```python
workflow.validate()
workflow.view()
workflow.view(reuse_views=False, log_level="DEBUG")
workflow.view(application_path=Path("/path/to/gview.app"))
```

- `validate()` checks required files and applicable result markers without opening GaussView.
- `view()` validates before opening and reuses matching views by default.
- `reuse_views=False` requests new views; the default `True` reuses matching open views.
- `log_level="DEBUG"` enables diagnostic logging; `"INFO"` is the default. Standard numeric logging levels are also accepted.
- `application_path=Path(...)` selects an application bundle.

Errors propagate to the calling script.

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

Choose results that the calculation actually contains. Use only `source` for an input-geometry viewer. Call `workflow.validate()` to check data without opening windows. The [viewing guide](workflows.md) explains surfaces, comparisons and ownership; the [menu guide](controls.md) explains actions outside the specialized helpers.
