# Viewing workflows

## Sessions and ownership

`Session.open(workflow)` validates a workflow, starts or attaches to GaussView and opens its declared views. `Session.attach()` requires one running app and attaches without claiming existing groups. Both methods accept `application_path=Path(...)`; `Session.open(..., reuse_views=False)` requests new views. Group identifiers such as `"G1:"` belong to the current application session; discover them at runtime rather than treating them as permanent file identifiers.

Reuse preserves the data already loaded in GaussView and restores missing result panels. After changing source or cube files, use `reuse_views=False` to load the new data.

```python
from gvu import Session

session = Session.attach()
model = session.model("G1:")
model.center()
```

A session owns groups freshly created by its `open`, `load` and `compare` operations:

- `session.close()` closes owned groups while retaining pre-existing groups.
- A `with Session.open(...) as session:` block closes owned groups on exit; reused groups remain open.
- Keep a session outside a context block when new views should remain on screen.

## Load and compare structures

```python
from pathlib import Path
from gvu import Alignment, Grouping, Session

session = Session.attach()
models = session.load(
    [Path("first.gjf"), Path("second.gjf")],
    grouping=Grouping.SEPARATE,
)
for model in models:
    model.align(Alignment("X", "Y"))
```

- `Grouping.SEPARATE` creates separate groups.
- `Grouping.TOGETHER` loads documents into one group.
- `read_intermediates=True` loads optimization/scan/IRC intermediate geometries explicitly.

Supported extensions are validated before the file dialog opens; XYZ is unsupported by this interface.

For linked-job logs:

- GVU selects all sections in the native job-selection dialog.
- Loading waits for every explicit job to appear. Internal optimization/frequency steps do not count as separate file jobs.
- A multi-job log can create several molecule groups.
- Requested result panels open for the jobs that contain those results.

For input-geometry comparisons, use `session.compare([first, second], name="comparison")`. It takes the explicit first-job geometry from each `.gjf` or `.com`, excludes later Link1 jobs from temporary display copies, checks the frame count and aligns the resulting group. The copies are removed after loading; source inputs are unchanged. This helper requires explicit coordinates in the first job.

## Align, fit and position

`Alignment("X", "Y")` places molecular X horizontally and Y vertically using native Quick alignment. Signed axes are accepted, for example `Alignment("-Z", "Y")`. The selected axes must be orthogonal. `model.center()` invokes native View > Center, which also adjusts the displayed size to fit. Camera alignment leaves input coordinates unchanged.

```python
from gvu import Bounds, Layout

screens = session.screens()
session.arrange(models, style=Layout.OVERLAP, screen=screens[0])
models[0].bounds(Bounds(150, 130, 620, 390))
```

- `Screen` objects include complete and usable display bounds.
- Display coordinates can be negative for monitors left of or above the main display.
- Without an explicit screen, `arrange` uses the display containing the pointer.
- `OVERLAP`, `CASCADE` and `TILE` arrange only the selected models.
- Focusing a model does not reposition it.

Use `with session.preserve_windows():` around operations that should restore existing bounds on exit. It restores changed windows that still exist, including after an exception, and leaves group visibility unchanged.

## Frames and animations

```python
model.seek(1)
count = model.frame_count
model.play(frame_delay=100)
model.pause()
model.animation(frame_delay=150, endpoint_delay=500)
```

Frame numbers start at one. Delays are integer milliseconds. `animation` configures native playback; `play` and `pause` control its state. Playback speed is a display setting, not the physical time represented by an IRC or scan.

```python
from gvu import Result

vibrations = session.result(Result.VIBRATIONS, model.group)
vibrations.mode(2)
vibrations.play()
vibrations.pause()
```

Mode indices also start at one. Mode selection can scroll the native table. A requested result must be enabled for the selected group's data.

## Density surfaces and ESP

Declare paired `Surface(name, density=density_path, potential=potential_path)` files in a `Workflow`. Both file arguments are required and keyword-only. Use the same density boundary and opacity for compared states. The library derives shared color limits live by evaluating the potential on the exterior density boundary; it does not use cached scale reports. Grid dimensions and geometry provenance must remain consistent with the calculation. Legend bounds are entered through the detected numeric fields, independently of frame-toolbar placement.

```python
from pathlib import Path
from gvu import Surface, SurfaceStyle, Workflow

workflow = Workflow(
    source=Path("/absolute/path/irc.log"),
    surfaces=(Surface(
        "transition-state",
        density=Path("/absolute/path/ts-density.cube"),
        potential=Path("/absolute/path/ts-potential.cube"),
    ),),
    density_isovalue=0.002,
    surface_style=SurfaceStyle.TRANSPARENT,
    opacity=0.5,
)
```

The exterior boundary is selected through low-density connectivity to the grid boundary. Marching cubes and potential interpolation determine pooled limits, rounded outward. Enclosed near-nuclear boundaries do not determine the shared legend and can saturate it. The supported analysis uses positive-dimension, single-scalar cube grids.

A few endpoint/TS surfaces do not supply an ESP animation for every IRC geometry. Each additional map needs the corresponding computed wavefunction or field. The viewer does not establish convergence, state identity or chemical bonding from a picture.

## Exports and other commands

- `model.save(path)` exports a native structure.
- `model.image(path)` exports a native image.
- `model.movie(path)` exports a movie; end-to-end movie export remains unverified in the current coverage record.
- Plot helpers expose `data(path)`, `image(path)` and `properties()`.

Exports reject existing paths.

Use the [menu and dialog guide](controls.md) for other native actions. Consult [coverage](coverage.md) before treating a specialized operation as tested.
