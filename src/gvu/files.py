"""GaussView input formats and single-job comparison documents."""

import re
from pathlib import Path

from .errors import UnsupportedFormat

FORMATS = frozenset(
    [
        ".gjf",
        ".com",
        ".log",
        ".out",
        ".fch",
        ".fchk",
        ".chk",
        ".gfrq",
        ".cub",
        ".cube",
        ".pdb",
        ".pdb1",
        ".mol",
        ".rxn",
        ".sdf",
        ".gmmx",
        ".mol2",
        ".ml2",
        ".cif",
    ]
)


def input_paths(paths):
    """Validate every document before any UI mutation."""
    if isinstance(paths, (str, Path)):
        paths = (paths,)
    paths = tuple(Path(p).expanduser().resolve() for p in paths)
    if not paths:
        raise ValueError("Supply at least one document")
    for path in paths:
        if path.suffix.lower() not in FORMATS:
            raise UnsupportedFormat(
                f"Unsupported GaussView format {path.suffix!r}: {path}"
            )
        if not path.is_file():
            raise FileNotFoundError(path)
    return paths



def matches_document(window, path):
    """Match a molecule view's complete source path, excluding prefix collisions."""
    title = str(window.get("kCGWindowName", ""))
    source = Path(path).expanduser().resolve()
    return bool(re.match(r"G\d+:M\d+:V\d+", title)) and title.endswith(f" ({source})")


def first_job(path):
    """Use the explicit first Gaussian input geometry, excluding later Link1 jobs."""
    path = Path(path)
    if path.suffix.lower() not in {".gjf", ".com"}:
        raise UnsupportedFormat("Comparisons require Gaussian .gjf or .com inputs")
    text = re.split(r"(?im)^\s*--Link1--\s*$", path.read_text(), maxsplit=1)[0]
    if re.search(
        r"(?i)geom\s*=\s*(?:\([^)]*\b(?:allcheck|check)\b|allcheck|check)", text
    ):
        raise ValueError(f"Comparison needs explicit coordinates: {path}")
    return text.rstrip() + "\n\n"


def job_count(path):
    """Count Gaussian job-start records, excluding internal Opt/Freq steps."""
    path = Path(path)
    if path.suffix.lower() not in {".log", ".out"}:
        return 1
    with path.open(errors="replace") as stream:
        return max(1, sum(line.lstrip().startswith("Entering Link 1 =") for line in stream))
