"""Shared camera, display and document contracts."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from gvu import Alignment, Bounds, Grouping, Layout, Screen, Session, UnsupportedFormat
from gvu.desktop import place_windows
from gvu.files import first_job, input_paths


class DesktopTests(unittest.TestCase):
    def test_signed_screens(self):
        """Keep all layouts inside displays with negative global coordinates."""
        for area in (Bounds(-2560, -400, 2560, 1400), Bounds(0, 33, 1728, 1004)):
            for style in Layout:
                placed = place_windows(area, 16, style)
                self.assertEqual(len(placed), 16)
                for box in placed:
                    self.assertGreaterEqual(box.x, area.x)
                    self.assertGreaterEqual(box.y, area.y)
                    self.assertLessEqual(box.x + box.width, area.x + area.width)
                    self.assertLessEqual(box.y + box.height, area.y + area.height)

    def test_alignment_axes(self):
        """Validate signed orthogonal axes before invoking any native controls."""
        self.assertEqual(Alignment("-Z", "Y").pairs, (("-Z", "X"), ("Y", "Y")))
        for axes in (("X", "-X"), ("x", "Y"), ("A", "B")):
            with self.assertRaises(ValueError):
                Alignment(*axes)

    def test_invalid_layout(self):
        """Refuse invalid sizes/counts and support an empty layout."""
        area = Bounds(0, 0, 1000, 800)
        self.assertEqual(place_windows(area, 0), ())
        for count in (-1, 1.5):
            with self.assertRaises(ValueError):
                place_windows(area, count)
        with self.assertRaises(ValueError):
            place_windows(area, 1, size=(float("nan"), 390))
        with self.assertRaises(ValueError):
            Bounds(0, 0, -1, 390)

    def test_selected_models(self):
        """Arrange only explicit session models on the selected screen."""
        backend = SimpleNamespace(
            set_bounds=Mock(), group_view=lambda group: {"group": group}
        )
        s = Session(backend, ("G1:", "G2:"))
        screen = Screen(
            2, "Left", Bounds(-1920, 0, 1920, 1080), Bounds(-1920, 30, 1920, 1000)
        )
        s.arrange([s.model("G2:")], screen=screen)
        backend.set_bounds.assert_called_once()
        self.assertEqual(backend.set_bounds.call_args.args[0], {"group": "G2:"})
        self.assertLess(backend.set_bounds.call_args.args[1].x, 0)

    def test_snapshot_restore(self):
        """Restore changed existing windows, ignoring new and unchanged hidden windows."""

        def window(number, x):
            return {
                "kCGWindowNumber": number,
                "kCGWindowName": f"G{number}:M1:V1 - model.gjf",
                "kCGWindowBounds": {"X": x, "Y": 10, "Width": 600, "Height": 390},
            }

        original = [window(1, 10), window(2, 30)]
        current = [window(1, 100), window(2, 30), window(3, 300)]
        backend = SimpleNamespace(
            windows=Mock(side_effect=[original, current]), set_bounds=Mock()
        )
        with Session(backend).preserve_windows():
            pass
        backend.set_bounds.assert_called_once_with(current[0], Bounds(10, 10, 600, 390))

    def test_snapshot_exception(self):
        """Restore changed positions even when the enclosed action fails."""
        w = {
            "kCGWindowNumber": 1,
            "kCGWindowName": "model",
            "kCGWindowBounds": {"X": 1, "Y": 2, "Width": 600, "Height": 390},
        }
        moved = dict(w, kCGWindowBounds={"X": 20, "Y": 2, "Width": 600, "Height": 390})
        backend = SimpleNamespace(
            windows=Mock(side_effect=[[w], [moved]]), set_bounds=Mock()
        )
        with (
            self.assertRaisesRegex(RuntimeError, "test failure"),
            Session(backend).preserve_windows(),
        ):
            raise RuntimeError("test failure")
        backend.set_bounds.assert_called_once_with(moved, Bounds(1, 2, 600, 390))


class DocumentTests(unittest.TestCase):
    def test_unsupported_format(self):
        """Refuse XYZ before it can open an unsupported-format modal."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.xyz"
            path.write_text("1\nexample\nH 0 0 0\n")
            with self.assertRaises(UnsupportedFormat):
                input_paths([path])

    def test_first_geometry(self):
        """Exclude linked jobs without changing the original input document."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.gjf"
            text = "# PM6\n\ngeometry\n\n0 1\nH 0 0 0\n\n--Link1--\n# geom=allcheck\n"
            path.write_text(text)
            self.assertNotIn("--Link1--", first_job(path))
            self.assertEqual(path.read_text(), text)

    def test_checkpoint_input(self):
        """Skip text marker checks for a binary checkpoint; live menus decide availability."""
        from gvu import Result, Workflow
        from gvu.viewer import validate

        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.chk"
            path.write_bytes(b"\xff\x00\x80")
            validate(Workflow(path, results=(Result.VIBRATIONS,)))

    def test_job_records(self):
        """Wait for explicit linked jobs without counting automatic frequency steps."""
        from gvu.files import job_count

        with TemporaryDirectory() as directory:
            path = Path(directory) / "calculation.log"
            path.write_text(" Entering Link 1 = first\nNormal termination\nLink1: Proceeding to internal job step number 2\nNormal termination\n")
            self.assertEqual(job_count(path), 1)
            path.write_text(path.read_text() + " Entering Link 1 = second\n")
            self.assertEqual(job_count(path), 2)

    def test_load_ownership(self):
        """Own new groups only, even when attached to an existing session."""
        backend = SimpleNamespace(
            molecule_groups=Mock(side_effect=[{"G1:"}, {"G1:", "G2:"}]),
            open_documents=Mock(),
            check_errors=Mock(),
            select_file_jobs=Mock(return_value=False),
            windows=Mock(),
            group_ids=set(),
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.gjf"
            path.write_text("# PM6\n")
            backend.windows.side_effect = [
                [], [{"kCGWindowName": f"G2:M1:V1 - {path.name} ({path.resolve()})"}],
            ]
            s = Session(backend)
            models = s.load([path])
            self.assertEqual([m.group for m in models], ["G2:"])
            self.assertEqual(s._owned_groups, ["G2:"])
            backend.molecule_groups.assert_called_once_with()
            backend.open_documents.assert_called_once_with(
                (path.resolve(),), False, Grouping.SEPARATE
            )


class VibrationTests(unittest.TestCase):
    def test_mode_column(self):
        """Select the mode column rather than the duplicate numbered row header."""
        from gvu import Vibrations

        labels = [
            ("Mode #", 90, 100, 70),
            ("Frequency", 200, 100, 170),
            ("Animate Vibration:", 90, 300, 40),
            ("2", 44, 180, 40),
            ("2", 105, 180, 101),
        ]
        backend = SimpleNamespace(
            window=lambda title: {}, read=lambda w: labels, click=Mock()
        )
        Vibrations(Session(backend), "Vibrations").mode(2)
        backend.click.assert_called_once_with(105, 180)

    def test_animation_state(self):
        """Read the OCR variant and verify the state after toggling animation."""
        from gvu import Vibrations

        state = {"playing": False}

        def read(window):
            return [
                (
                    "Stop Animatior" if state["playing"] else "Start Animatior",
                    20,
                    30,
                    10,
                )
            ]

        def click(x, y):
            state["playing"] = not state["playing"]

        backend = SimpleNamespace(
            window=lambda title: {}, read=read, click=Mock(side_effect=click)
        )
        v = Vibrations(Session(backend), "Vibrations")
        v.play()
        v.play()
        v.pause()
        v.pause()
        self.assertFalse(state["playing"])
        self.assertEqual(backend.click.call_count, 2)
