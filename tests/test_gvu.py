import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np

from gvu import Result, Session, Surface, Workflow
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
            surface = Surface(
                "synthetic", density=root / "density.cube", potential=root / "potential.cube"
            )
            np.testing.assert_allclose(surface_range(surface, np.exp(-4)), (-2, 2), atol=1e-5)
            cube(surface.potential, x + 3)
            np.testing.assert_allclose(surface_range(surface, np.exp(-4)), (1, 5), atol=1e-5)

    def test_surface_keywords(self):
        """Require labeled density and potential arguments in a surface pair."""
        density, potential = Path("density.cube"), Path("potential.cube")
        surface = Surface("state", density=density, potential=potential)
        self.assertEqual((surface.density, surface.potential), (density, potential))
        with self.assertRaises(TypeError):
            Surface("state", density, potential)
        with self.assertRaises(TypeError):
            Surface("state", density, potential=potential)
        with self.assertRaises(TypeError):
            Surface("state", density=density)

    def test_grid_mismatch(self):
        """Reject density and potential cubes with different grid dimensions."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cube(root / "density.cube", np.ones((3, 3, 3)))
            cube(root / "potential.cube", np.ones((4, 3, 3)))
            with self.assertRaisesRegex(ValueError, "grids do not match"):
                surface_range(
                    Surface(
                        "mismatch", density=root / "density.cube", potential=root / "potential.cube"
                    ),
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
        """Pass the application path and explicit reuse policy to the launcher."""
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
                workflow.view(application_path=app, reuse_views=False)
            launch.assert_called_once_with(workflow, app.resolve(), reuse_views=False)

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
                Workflow(source).view(application_path=app, log_level="DEBUG")
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

    def test_session_options(self):
        """Apply the same reuse policy to Session.open and group ownership."""
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            source = Path(directory) / "model.gjf"
            source.write_text("# PM6\n\nExample\n\n0 1\nH 0 0 0\n\n")
            workflow = Workflow(source)
            app = Path(directory) / "gview.app"
            for reuse in (False, True):
                with (
                    self.subTest(reuse=reuse),
                    patch(
                        "gvu.api.launch",
                        return_value=(SimpleNamespace(pid=123), ["G1:"], reuse),
                    ) as launch,
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    configure_logging()
                    session = Session.open(workflow, application_path=app, reuse_views=reuse)
                    launch.assert_called_once_with(workflow, app.resolve(), reuse_views=reuse)
                    self.assertEqual(session.owned, not reuse)

    def test_log_levels(self):
        """Accept standard level names and numbers; reject invalid levels before opening."""
        from unittest.mock import patch

        with contextlib.redirect_stderr(io.StringIO()):
            for level, expected in (("INFO", 20), ("DEBUG", 10), (30, 30)):
                configure_logging(log_level=level)
                self.assertEqual(LOG.level, expected)
            with (
                patch("gvu.viewer.launch") as launch,
                self.assertRaisesRegex(ValueError, "Unknown level"),
            ):
                Workflow(Path("/missing.gjf")).view(log_level="INVALID")
            launch.assert_not_called()

    def test_missing_data(self):
        """Reject a requested property absent from the log before opening the UI."""
        with TemporaryDirectory() as directory:
            source = Path(directory) / "single-point.log"
            source.write_text("SCF Done: synthetic\n")
            with self.assertRaisesRegex(ValueError, "VIBRATIONS data not found"):
                validate(Workflow(source, (Result.VIBRATIONS,)))

    def test_exact_source(self):
        """Do not confuse another filename with a matching source-path prefix."""
        from gvu.files import matches_document

        path = Path("/runs/source.log")
        self.assertTrue(matches_document({"kCGWindowName": f"G1:M2:V1 - source ({path})"}, path))
        self.assertFalse(matches_document({"kCGWindowName": f"G1:M2:V1 - source ({path}.old)"}, path))
        self.assertFalse(matches_document({"kCGWindowName": f"G1:M2:V1 - source ({path}) extra"}, path))

    def test_duplicate_reuse(self):
        """Reuse one complete load rather than combining duplicate source groups."""
        from unittest.mock import patch

        source = Path("/runs/source.log")
        windows = [{"kCGWindowName": f"G{n}:M1:V1 - source ({source})"} for n in (2, 3, 4, 5)]
        viewer = SimpleNamespace(workflow=Workflow(source), windows=lambda: windows)
        with patch("gvu.viewer.job_count", return_value=1):
            self.assertEqual(reusable_groups(viewer), ["G5:"])
        with patch("gvu.viewer.job_count", return_value=2):
            self.assertEqual(reusable_groups(viewer), ["G4:", "G5:"])

    def test_restore_panel(self):
        """Restore a closed panel on its existing source molecule group."""
        from unittest.mock import Mock

        from gvu.viewer import _reuse_workflow

        source = Path("/runs/source.gjf")
        panel = {"kCGWindowName": "G2:M1:V1 - Vibrations"}
        viewer = SimpleNamespace(
            workflow=Workflow(source, (Result.VIBRATIONS,)), group_ids=set(),
            windows=lambda: [{"kCGWindowName": f"G2:M1:V1 - source ({source})"}],
            result_window=lambda group, result: None,
            open_result=Mock(return_value=panel), front=Mock(),
        )
        self.assertEqual(_reuse_workflow(viewer), ["G2:"])
        viewer.open_result.assert_called_once_with("G2:", Result.VIBRATIONS)

    def test_recent_reuse(self):
        """Reuse loaded files without incorrectly comparing them to app startup."""
        import sys
        from unittest.mock import Mock, patch

        from gvu.viewer import launch

        backend = SimpleNamespace()
        quartz = SimpleNamespace(CGPreflightScreenCaptureAccess=lambda: True)
        native = SimpleNamespace(AXIsProcessTrusted=lambda: True,
                                 AXUIElementCopyAttributeValue=Mock(),
                                 AXUIElementCreateApplication=Mock())
        with (
            patch.dict(sys.modules, {"Quartz": quartz, "ApplicationServices": native}),
            patch("gvu.viewer.application_pids", return_value=[123]),
            patch("gvu.macos.MacViewer", return_value=backend),
            patch("gvu.viewer._reuse_workflow", return_value=["G2:"]),
            patch("gvu.viewer.subprocess.run", side_effect=AssertionError("App-age lookup")),
        ):
            self.assertEqual(launch(Workflow(Path("/recent.gjf")), Path("/gview.app")),
                             (backend, ["G2:"], True))

    def test_reuse_legend(self):
        """Only edit a reused ESP legend when its requested bounds differ."""
        from unittest.mock import Mock

        from gvu.viewer import _reuse_workflow

        source = Path("/runs/source.gjf")
        surface = Surface("state", density=Path("/density.cube"), potential=Path("/potential.cube"))
        viewer = SimpleNamespace(
            workflow=Workflow(source, surfaces=(surface,)), group_ids=set(),
            windows=lambda: [
                {"kCGWindowName": f"G2:M1:V1 - source ({source})"},
                {"kCGWindowName": "G3:M1:V1 - Density ( isoval = 0.002 ; [mapped with ESP] )"},
            ],
            verify_scale=Mock(), apply_scale=Mock(), front=Mock(),
        )
        self.assertEqual(_reuse_workflow(viewer), ["G2:", "G3:"])
        viewer.apply_scale.assert_not_called()
        viewer.verify_scale.side_effect = RuntimeError("Legend differs")
        self.assertEqual(_reuse_workflow(viewer), ["G2:", "G3:"])
        viewer.apply_scale.assert_called_once_with("G3:")

    def test_group_reuse(self):
        """Recognize a complete mapped group block without source filenames."""
        source = Path("/runs/irc.log")
        surfaces = tuple(
            Surface(n, density=Path(n + "-density.cube"), potential=Path(n + "-potential.cube"))
            for n in ("reverse", "ts", "forward")
        )
        workflow = Workflow(source, (Result.IRC,), surfaces)
        windows = [{"kCGWindowName": f"G7:M1:V1 - irc.log ({source})"}]
        windows += [
            {"kCGWindowName": f"G{n}:M1:V1 - Density ( isoval = 0.002 ; [mapped with ESP] )"}
            for n in (8, 9, 10)
        ]
        viewer = SimpleNamespace(workflow=workflow, windows=lambda: windows)
        from unittest.mock import patch

        with patch("gvu.viewer.job_count", return_value=1):
            self.assertEqual(reusable_groups(viewer), ["G7:", "G8:", "G9:", "G10:"])
        windows.pop()
        with patch("gvu.viewer.job_count", return_value=1):
            self.assertIsNone(reusable_groups(viewer))

    def test_linked_reuse(self):
        """Retain both linked source groups when reusing a mapped workflow."""
        source = Path("/runs/linked.log")
        surface = Surface("state", density=Path("/density.cube"), potential=Path("/potential.cube"))
        workflow = Workflow(source, surfaces=(surface,))
        windows = [
            {"kCGWindowName": f"G2:M1:V1 - linked.log ({source})"},
            {"kCGWindowName": f"G3:M1:V1 - linked.log ({source})"},
            {"kCGWindowName": "G4:M1:V1 - Density ( isoval = 0.002 ; [mapped with ESP] )"},
        ]
        viewer = SimpleNamespace(workflow=workflow, windows=lambda: windows)
        from unittest.mock import patch

        with patch("gvu.viewer.job_count", return_value=2):
            self.assertEqual(reusable_groups(viewer), ["G2:", "G3:", "G4:"])

    def test_text_logging(self):
        """Format readable metadata and standard multiline tracebacks."""
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            configure_logging()
            LOG.debug("hidden")
            LOG.info("sample", extra={"metadata": {"path": Path("/example"), "text": "a\nb"}})
            try:
                raise RuntimeError("multiline\nerror")
            except RuntimeError:
                LOG.error("failed", exc_info=True)
        text = stream.getvalue()
        self.assertRegex(text, r"(?m)^\d{4}-\d{2}-\d{2}T\S+ \[INFO\] sample logger=")
        self.assertIn("path=/example text='a\\nb'", text)
        self.assertRegex(text, r"(?m)^\d{4}-\d{2}-\d{2}T\S+ \[ERROR\] failed logger=")
        self.assertNotIn(" time=", text)
        self.assertIn("Traceback (most recent call last):", text)
        self.assertIn("RuntimeError: multiline\nerror", text)
        self.assertNotIn("hidden", text)


if __name__ == "__main__":
    unittest.main()
