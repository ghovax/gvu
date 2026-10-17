import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np

from gvu import Result, Surface, Workflow
from gvu.logging import LOG, configure_logging
from gvu.surfaces import surface_range
from gvu.viewer import reusable_groups, validate


def cube(path, values, origin=(-4, -4, -4), step=0.25):
    with path.open("w") as stream:
        stream.write(
            "synthetic test field\nnot a calculation\n1 " + " ".join(map(str, origin)) + "\n"
        )
        for axis, size in enumerate(values.shape):
            vector = [0.0, 0.0, 0.0]
            vector[axis] = step
            stream.write(str(size) + " " + " ".join(map(str, vector)) + "\n")
        stream.write("1 1.0 0 0 0\n")
        stream.write(" ".join(map(str, values.ravel())))


class ScientificRangeTests(unittest.TestCase):
    def test_live_range(self):
        """Recompute exterior extrema after changing the potential field."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            axis = np.linspace(-4, 4, 33)
            x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
            density = np.exp(-(x * x + y * y + z * z))
            cube(root / "density.cube", density)
            cube(root / "potential.cube", x)
            surface = Surface("synthetic", root / "density.cube", root / "potential.cube")
            np.testing.assert_allclose(surface_range(surface, np.exp(-4)), (-2, 2), atol=1e-5)
            cube(surface.potential, x + 3)
            np.testing.assert_allclose(surface_range(surface, np.exp(-4)), (1, 5), atol=1e-5)

    def test_grid_mismatch(self):
        """Reject density and potential cubes with different grid dimensions."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cube(root / "density.cube", np.ones((3, 3, 3)))
            cube(root / "potential.cube", np.ones((4, 3, 3)))
            with self.assertRaisesRegex(ValueError, "grids do not match"):
                surface_range(
                    Surface("mismatch", root / "density.cube", root / "potential.cube"),
                    0.002,
                )


class WorkflowTests(unittest.TestCase):
    def test_view_check(self):
        """Validate through the workflow method without launching a native app."""
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            source = Path(directory) / "model.gjf"
            source.write_text("# PM6\n\nExample\n\n0 1\nH 0 0 0\n\n")
            stream = io.StringIO()
            with patch("gvu.viewer.launch") as launch, contextlib.redirect_stderr(stream):
                Workflow(source).validate()
            launch.assert_not_called()
            self.assertEqual(stream.getvalue(), "")

    def test_view_options(self):
        """Preserve application selection and fresh-view options through the method."""
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            source = Path(directory) / "model.gjf"
            source.write_text("# PM6\n\nExample\n\n0 1\nH 0 0 0\n\n")
            app = Path(directory) / "gview.app"
            executable = app / "Contents/MacOS/gview"
            executable.parent.mkdir(parents=True)
            executable.touch()
            workflow = Workflow(source)
            result = (SimpleNamespace(pid=123), ["G1:"], False)
            with (
                patch("gvu.viewer.sys.platform", "darwin"),
                patch("gvu.viewer.launch", return_value=result) as launch,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                workflow.view(app=app, fresh=True)
            launch.assert_called_once_with(workflow, app.resolve(), True)

    def test_process_args(self):
        """Ignore host process arguments when opening a workflow."""
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            source = Path(directory) / "model.gjf"
            source.write_text("# PM6\n\nExample\n\n0 1\nH 0 0 0\n\n")
            app = Path(directory) / "gview.app"
            executable = app / "Contents/MacOS/gview"
            executable.parent.mkdir(parents=True)
            executable.touch()
            result = (SimpleNamespace(pid=123), ["G1:"], False)
            with (
                patch("sys.argv", ["host", "--unrelated"]),
                patch("gvu.viewer.sys.platform", "darwin"),
                patch("gvu.viewer.launch", return_value=result),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                Workflow(source).view(app=app, verbose=True)
                self.assertEqual(LOG.level, 10)

    def test_view_failure(self):
        """Let callers handle errors without process exit or duplicate logging."""
        with TemporaryDirectory() as directory:
            source = Path(directory) / "missing.gjf"
            stream = io.StringIO()
            with (
                contextlib.redirect_stderr(stream),
                self.assertRaisesRegex(ValueError, "Missing existing calculation data"),
            ):
                Workflow(source).view()
            self.assertEqual(stream.getvalue(), "")

    def test_missing_data(self):
        """Reject a requested property absent from the log before opening the UI."""
        with TemporaryDirectory() as directory:
            source = Path(directory) / "single-point.log"
            source.write_text("SCF Done: synthetic\n")
            with self.assertRaisesRegex(ValueError, "VIBRATIONS data not found"):
                validate(Workflow(source, (Result.VIBRATIONS,)))

    def test_group_reuse(self):
        """Recognize a complete mapped group block without source filenames."""
        source = Path("/runs/irc.log")
        surfaces = tuple(
            Surface(n, Path(n + "-density.cube"), Path(n + "-potential.cube"))
            for n in ("reverse", "ts", "forward")
        )
        workflow = Workflow(source, (Result.IRC,), surfaces)
        windows = [{"kCGWindowName": f"G7:M1:V1 - irc.log ({source})"}]
        windows += [
            {"kCGWindowName": f"G{n}:M1:V1 - Density ( isoval = 0.002 ; [mapped with ESP] )"}
            for n in (8, 9, 10)
        ]
        viewer = SimpleNamespace(workflow=workflow, windows=lambda: windows)
        self.assertEqual(reusable_groups(viewer), ["G7:", "G8:", "G9:", "G10:"])
        windows.pop()
        self.assertIsNone(reusable_groups(viewer))

    def test_json_logging(self):
        """Keep metadata and multiline exceptions within individual JSON records."""
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            configure_logging()
            LOG.debug("hidden")
            LOG.info("sample", extra={"metadata": {"path": Path("/example"), "text": "a\nb"}})
            try:
                raise RuntimeError("multiline\nerror")
            except RuntimeError:
                LOG.error("failed", exc_info=True)
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([r["event"] for r in records], ["sample", "failed"])
        self.assertEqual(records[0]["metadata"]["text"], "a\nb")
        self.assertIn("RuntimeError: multiline\nerror", records[1]["exception"])


if __name__ == "__main__":
    unittest.main()
