# Development

## Package layout

| Location | Responsibility |
| --- | --- |
| `src/gvu/api.py` | Public sessions, models and dialogs |
| `src/gvu/models.py` | Workflow declarations, alignment, bounds, screens and result enums |
| `src/gvu/menus.py` | Native menu discovery, state and dispatch |
| `src/gvu/controls.py` | Native dialog-control descriptors and resolution |
| `src/gvu/macos.py` | Process-scoped macOS UI backend |
| `src/gvu/viewer.py` | Workflow validation, launch/reuse and command-line entry point |
| `src/gvu/surfaces.py` | Live density-boundary ESP analysis |
| `src/gvu/desktop.py` | Display-independent placement calculations |
| `src/gvu/logging.py` | Structured events and CLI error handling |
| `tests/` | Unit tests with temporary fixtures |
| `docs/` | Sphinx sources and Read the Docs theme configuration |

Run scripts declare calculation-specific data and displays. Add reusable controls to the library rather than embedding another UI implementation in each run. Availability failures should be explicit; do not introduce silent fallbacks that claim an unsupported operation succeeded.

## Build documentation

From the repository root:

```bash
uv sync --extra docs
uv run --extra docs sphinx-build -W --keep-going -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. The generated site includes sidebar navigation, breadcrumbs, search, previous/next links, a Python index and source views. Generated HTML stays under the ignored `_build` directory; maintain the source pages and package docstrings.

The root `.readthedocs.yaml` configures Python, installation of the `docs` extra, the Sphinx configuration and warning-sensitive builds. A Read the Docs project can import this public repository to run those builds. GitHub Pages publishes the same Sphinx site through the documentation workflow.

## Validate changes

```bash
uv run python -m unittest discover -s tests
```

Build with warnings treated as errors after changing documentation or public API signatures. Review the API reference, menu tables, sidebar links and search output in the generated site. Test new native controls against the installed application using temporary fixtures and close only the views those probes own. Keep the [coverage record](coverage.md) consistent with what was actually exercised.

## Documentation sources

- [Sphinx documentation](https://www.sphinx-doc.org/en/master/).
- [MyST Parser](https://myst-parser.readthedocs.io/en/latest/).
- [Read the Docs configuration](https://docs.readthedocs.com/platform/stable/config-file/v2.html).
- [Read the Docs theme](https://sphinx-rtd-theme.readthedocs.io/en/stable/).

## Publish a release

The `publish.yml` workflow uses PyPI Trusted Publishing with the GitHub environment `pypi`. Configure a pending publisher on PyPI with project `gvu`, owner `ghovax`, repository `gvu`, workflow `publish.yml` and environment `pypi`. This is required once, before the first upload; no long-lived API token is needed.

Update the version in `pyproject.toml`, refresh `uv.lock`, run the checks and build both distributions with `uv build --no-sources`. The tag must match the package version, for example `v0.3.0`. Pushing that tag runs the release workflow: build, metadata checks, wheel/source-install smoke tests, attestations and trusted upload. A PyPI release version cannot be replaced; subsequent changes require a new version.

```bash
uv lock
uv run python -m unittest discover -s tests
uv build --no-sources
uv run twine check --strict dist/*
git tag v0.3.0
git push origin v0.3.0
```

The `workflow_dispatch` event can rerun a verified tag after correcting publishing authorization. The workflow checks the tag against package metadata before uploading.
