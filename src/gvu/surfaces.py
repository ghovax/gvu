"""Live ESP bounds on exterior density surfaces; no cached reports."""

import itertools
import math
import time

from .logging import LOG


def read_cube(path):
    import numpy as np

    with path.open() as stream:
        stream.readline()  # cube comments
        stream.readline()
        header = stream.readline().split()
        atoms = int(header[0])
        origin = np.asarray(header[1:4], dtype=float)
        axes = [stream.readline().split() for _ in range(3)]
        shape = tuple(int(axis[0]) for axis in axes)
        steps = np.asarray([axis[1:4] for axis in axes], dtype=float)
        if atoms <= 0 or any(n <= 0 for n in shape):
            raise ValueError(
                f"Expected a single scalar cube with positive grid dimensions: {path}"
            )
        for _ in range(atoms):
            stream.readline()
        values = np.fromstring(stream.read().replace("D", "E"), sep=" ")
    if values.size != np.prod(shape) or not np.isfinite(values).all():
        raise ValueError(f"Incomplete or nonfinite cube: {path}")
    return values.reshape(shape), origin, steps


def surface_range(surface, isovalue):
    import numpy as np
    from scipy.ndimage import label, map_coordinates
    from skimage.measure import marching_cubes

    density, origin, steps = read_cube(surface.density)
    potential, other_origin, other_steps = read_cube(surface.potential)
    if (
        density.shape != potential.shape
        or not np.array_equal(origin, other_origin)
        or not np.array_equal(steps, other_steps)
    ):
        raise ValueError(f"Density and potential grids do not match for {surface.name}")
    # The low-density region touching the box boundary defines the exterior.
    regions, _ = label(density < isovalue)
    boundary_ids = np.unique(
        np.concatenate(
            [
                regions[0].ravel(),
                regions[-1].ravel(),
                regions[:, 0].ravel(),
                regions[:, -1].ravel(),
                regions[:, :, 0].ravel(),
                regions[:, :, -1].ravel(),
            ]
        )
    )
    outside = np.isin(regions, boundary_ids[boundary_ids != 0])
    vertices, faces, _, _ = marching_cubes(
        density, level=isovalue, allow_degenerate=False
    )
    cells = np.floor(vertices[faces].mean(axis=1)).astype(int)
    exterior_faces = np.zeros(len(faces), dtype=bool)
    for shift in itertools.product((0, 1), repeat=3):
        indices = np.clip(cells + shift, 0, np.asarray(density.shape) - 1)
        exterior_faces |= outside[tuple(indices.T)]
    triangles = vertices[faces[exterior_faces]]
    if not len(triangles):
        raise ValueError(f"No exterior density surface for {surface.name}")
    # Sample the entire triangle interiors, not only mesh vertices.
    # Check refinement at the precision used for the legend.
    extrema = []
    for divisions in (8, 16):
        lower, upper = math.inf, -math.inf
        for i in range(divisions + 1):
            for j in range(divisions + 1 - i):
                a, b = i / divisions, j / divisions
                points = (
                    triangles[:, 0] * a
                    + triangles[:, 1] * b
                    + triangles[:, 2] * (1 - a - b)
                )
                values = map_coordinates(potential, points.T, order=1, mode="nearest")
                lower = min(lower, float(values.min()))
                upper = max(upper, float(values.max()))
        extrema.append([lower, upper])
    if max(abs(a - b) for a, b in zip(*extrema, strict=True)) > 0.0001:
        raise ValueError(
            f"Surface sampling needs further refinement for {surface.name}"
        )
    return tuple(extrema[-1])


def color_range(surfaces, isovalue):
    """Derive the shared exterior ESP range directly from the source cubes."""
    started = time.monotonic()
    states = [surface_range(surface, isovalue) for surface in surfaces]
    lower = min(bounds[0] for bounds in states)
    upper = max(bounds[1] for bounds in states)
    bounds = [math.floor(lower * 10000) / 10000, math.ceil(upper * 10000) / 10000]
    if not all(math.isfinite(v) for v in bounds) or bounds[0] >= bounds[1]:
        raise ValueError("Invalid derived ESP range")
    LOG.info(
        "esp_scale_derived",
        extra={
            "metadata": {
                "bounds": bounds,
                "units": "atomic units",
                "density_isovalue": isovalue,
                "scope": "exterior density boundary",
                "states": dict(zip((s.name for s in surfaces), states, strict=True)),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        },
    )
    return tuple(f"{value:.4f}" for value in bounds)
