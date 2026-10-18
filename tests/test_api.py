import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from gvu import (
    ActionUnavailable,
    Dialog,
    MenuItem,
    ModelView,
    Result,
    Session,
    Workflow,
)
from gvu.viewer import validate


class ApiTests(unittest.TestCase):
    def test_group_discovery(self):
        """Read group identifiers from the native menu without Escape."""
        from unittest.mock import Mock, patch

        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        backend.front = Mock()
        backend.apple = Mock()
        items = [
            (MenuItem(("Windows", "Show Molecule Groups", "G2"), True), None),
            (MenuItem(("Windows", "Show Molecule Groups", "G12"), True), None),
            (MenuItem(("Windows", "Other"), True), None),
        ]
        with patch("gvu.menus.native_nodes", return_value=items):
            self.assertEqual(backend.molecule_groups(), {"G2:", "G12:"})
        backend.apple.assert_not_called()

    def test_animation_dismiss(self):
        """Dismiss animation options with a pointer action instead of Escape."""
        from unittest.mock import Mock

        view = {"kCGWindowBounds": {"X": 100, "Y": 50}}
        popup = {"kCGWindowBounds": {}, "kCGWindowNumber": 42}
        state = {"open": True}

        def click(x, y):
            if (x, y) == (300, 64):
                state["open"] = False

        backend = SimpleNamespace(
            group_view=lambda group: view,
            windows=lambda: [popup] if state["open"] else [],
            label=lambda window, text: (text, 0, 0),
            click=Mock(side_effect=click),
            apple=Mock(),
        )
        model = ModelView(Session(backend), "G1:")
        model.activate = Mock()
        model.animation()
        backend.apple.assert_not_called()
        backend.click.assert_any_call(300, 64)

    def test_opacity_pointer(self):
        """Position opacity absolutely without Home or End key events."""
        from unittest.mock import Mock

        from gvu import SurfaceStyle
        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        dialog = {"kCGWindowBounds": {"X": 100, "Y": 50}}
        backend.group_view = lambda group: {}
        backend.activate = Mock()
        backend.menu = Mock()
        backend.window = lambda title: dialog
        backend.label = lambda window, text: (text, 0, 0)
        backend.open_popup = lambda *args: {}
        backend.windows = lambda: []
        backend.find = lambda title: None
        backend.color_range = None
        backend.click = Mock()
        backend.apple = Mock()
        backend.surface_format("G1:", SurfaceStyle.TRANSPARENT, 0.25)
        backend.click.assert_any_call(308.0, 204, button="middle")
        backend.apple.assert_not_called()

    def test_middle_click(self):
        """Send paired pointer events with the requested native mouse button."""
        from unittest.mock import Mock, patch

        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        backend.front = Mock()
        names = (
            "kCGMouseButtonLeft",
            "kCGMouseButtonCenter",
            "kCGMouseButtonRight",
            "kCGEventLeftMouseDown",
            "kCGEventLeftMouseUp",
            "kCGEventOtherMouseDown",
            "kCGEventOtherMouseUp",
            "kCGEventRightMouseDown",
            "kCGEventRightMouseUp",
            "kCGEventMouseMoved",
            "kCGHIDEventTap",
        )
        constants = {name: name for name in names}
        backend.Q = SimpleNamespace(
            **constants, CGEventPost=Mock(), CGEventCreateMouseEvent=Mock(side_effect=lambda *a: a)
        )
        with patch("gvu.macos.time.sleep"):
            backend.click(10, 20, button="middle")
        events = backend.Q.CGEventCreateMouseEvent.call_args_list
        self.assertEqual(
            [e.args[1] for e in events],
            ["kCGEventMouseMoved", "kCGEventOtherMouseDown", "kCGEventOtherMouseUp"],
        )
        self.assertTrue(all(e.args[3] == "kCGMouseButtonCenter" for e in events))

    def test_disabled_action(self):
        """Refuse a disabled menu action before sending an accessibility event."""
        backend = SimpleNamespace(front=lambda: None)
        session = Session(backend)
        session._menu_nodes = lambda root: [
            (MenuItem(("Results", "NMR..."), False), None)
        ]
        with self.assertRaises(ActionUnavailable):
            session.invoke("Results", "NMR...")

    def test_ambiguous_control(self):
        """Refuse duplicated labels instead of clicking an arbitrary match."""
        window = {"kCGWindowName": "Test"}
        backend = SimpleNamespace(
            window=lambda title: window, read=lambda w: [("Save", 1, 2), ("Save", 3, 4)]
        )
        with self.assertRaises(ActionUnavailable):
            Dialog(Session(backend), "Test").click("Save")

    def test_export_collision(self):
        """Refuse an existing export path before activating or modifying a view."""
        with TemporaryDirectory() as directory:
            target = Path(directory) / "existing.png"
            target.write_bytes(b"preserve me")
            with self.assertRaises(FileExistsError):
                ModelView(Session(None), "G1:").image(target)
            self.assertEqual(target.read_bytes(), b"preserve me")

    def test_owned_cleanup(self):
        """Never close windows from a session attached to pre-existing views."""
        Session(None, ("G1:",), owned=False).close()

    def test_invalid_opacity(self):
        """Reject invalid rendering values before starting the app."""
        with TemporaryDirectory() as directory:
            source = Path(directory) / "model.gjf"
            source.write_text("synthetic input")
            with self.assertRaisesRegex(ValueError, "Opacity"):
                validate(Workflow(source, opacity=1.1))

    def test_disabled_parent(self):
        """Refuse a leaf whose containing menu is disabled."""
        session = Session(SimpleNamespace(front=lambda: None))
        session._menu_nodes = lambda root: [
            (MenuItem(("File", "Save Movie"), False), None),
            (MenuItem(("File", "Save Movie", "Save Movie File..."), True), None),
        ]
        with self.assertRaises(ActionUnavailable):
            session.invoke("File", "Save Movie", "Save Movie File...")

    def test_renamed_view(self):
        """Find a saved model after its original source filename changes."""
        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        expected = {"kCGWindowName": "G2:M1:V1 - saved.gjf (/tmp/saved.gjf)"}
        backend.windows = lambda: [
            {"kCGWindowName": "G2:M1:V1 - Optimization Plot"},
            expected,
        ]
        self.assertIs(backend.group_view("G2:"), expected)

    def test_popup_parent(self):
        """Select the menu option rather than its value in the animation panel."""
        from unittest.mock import Mock

        parent = {"kCGWindowName": "", "kCGWindowNumber": 1}
        menu = {"kCGWindowName": "", "kCGWindowNumber": 2}
        state = {"open": True}

        def click(x, y):
            state["open"] = False

        backend = SimpleNamespace(
            windows=lambda: [parent, menu] if state["open"] else [parent],
            read=lambda window: (
                [("Repeats:", 1, 1), ("Endless", 10, 20)]
                if window is parent
                else [("Endless", 30, 40)]
            ),
            click=Mock(side_effect=click),
        )
        Session(backend)._popup("Endless")
        backend.click.assert_called_once_with(30, 40)

    def test_popup_close(self):
        """Wait for a closing popup instead of clicking the exposed canvas twice."""
        from unittest.mock import Mock

        popup = {"kCGWindowName": "", "kCGWindowNumber": 42}
        state = {"clicked": False, "reads": 0}

        def windows():
            if state["clicked"]:
                state["reads"] += 1
                if state["reads"] > 1:
                    return []
            return [popup]

        def click(x, y):
            state["clicked"] = True

        backend = SimpleNamespace(
            windows=windows,
            read=lambda window: [("Endless", 10, 20)],
            click=Mock(side_effect=click),
        )
        Session(backend)._popup("Endless")
        backend.click.assert_called_once_with(10, 20)

    def test_frame_reference(self):
        """Keep the same view address while animation changes molecule numbers."""
        from gvu.macos import window_reference

        first = window_reference("G2:M1:V1 - molecule.log")
        self.assertEqual(first, window_reference("G2:M87:V1 - molecule.log"))
        self.assertNotEqual(first, window_reference("G2:M87:V2 - molecule.log"))
        self.assertNotEqual(first, window_reference("G3:M1:V1 - molecule.log"))

    def test_surface_group(self):
        """Map the requested group when two molecules share cube filenames."""
        from unittest.mock import Mock

        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        old = {"kCGWindowName": "G2:M1:V1 - reverse-endpoint-density.cube"}
        requested = {"kCGWindowName": "G6:M1:V1 - reverse-endpoint-density.cube"}
        backend.group_view = lambda group: requested if group == "G6:" else old
        backend.window = lambda name: old
        backend.activate = Mock()
        backend.menu = Mock(side_effect=RuntimeError("activation checked"))
        with self.assertRaisesRegex(RuntimeError, "activation checked"):
            backend.map_surface("reverse-endpoint", "G6:")
        backend.activate.assert_called_once_with(requested)

    def test_legend_fields(self):
        """Find numeric range fields beside, rather than inside, frame controls."""
        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        view = {"kCGWindowBounds": {"X": 100, "Y": 50, "Width": 1000, "Height": 600}}
        backend.read = lambda window: [
            ("1", 190, 99),
            ("Of 2", 260, 99),
            ("-7.429e-2|", 395, 99),
            ("8.600e-2", 790, 99),
        ]
        self.assertEqual(backend.scale_fields(view), [(-0.07429, 395, 99), (0.086, 790, 99)])
        backend.read = lambda window: [("1", 190, 99)]
        with self.assertRaises(ActionUnavailable):
            backend.scale_fields(view)

    def test_legend_target(self):
        """Edit the discovered range-field centers before verifying the legend."""
        from unittest.mock import Mock

        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        view = {"kCGWindowBounds": {"X": 100, "Y": 50, "Width": 1000, "Height": 600}}
        backend.group_view = lambda group: view
        backend.activate = Mock()
        backend.scale_fields = lambda window: [(-0.1, 395, 99), (0.1, 790, 99)]
        backend.click = Mock()
        backend.enter = Mock()
        backend.verify_scale = Mock()
        backend.color_range = (-0.2, 0.2)
        backend.apply_scale("G2:")
        self.assertEqual(backend.click.call_args_list[1::2], [((395, 99),), ((790, 99),)])
        self.assertEqual(backend.enter.call_args_list, [((-0.2,),), ((0.2,),)])
        backend.verify_scale.assert_called_once_with("G2:")

    def test_linked_jobs(self):
        """Select every linked job in the native table and confirm loading."""
        from unittest.mock import Mock

        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        dialog = {"kCGWindowName": "Select Jobs from File"}
        backend.find = Mock(side_effect=[dialog, None])
        backend.read = lambda window: [("Job Type", 100, 100), ("Ok", 400, 400)]
        backend.click = Mock()
        backend.apple = Mock()
        self.assertTrue(backend.select_file_jobs())
        backend.apple.assert_called_once_with('keystroke "a" using command down')
        self.assertEqual(backend.click.call_args_list, [((100, 130),), ((400, 400),)])
        backend.find = lambda title: None
        self.assertFalse(backend.select_file_jobs())

    def test_result_window(self):
        """Do not confuse a scan log's filename with its native scan plot."""
        from gvu.macos import MacViewer

        backend = MacViewer.__new__(MacViewer)
        source = {"kCGWindowName": "G2:M1:V1 (Job #2) - Scan.log (/tmp/Scan.log)"}
        plot = {"kCGWindowName": "G2:M1:V1 (Job #2) - Scan Plot"}
        backend.windows = lambda: [source, plot]
        self.assertIs(backend.result_window("G2:", Result.SCAN), plot)
        backend.windows = lambda: [source]
        self.assertIsNone(backend.result_window("G2:", Result.SCAN))

    def test_result_catalog(self):
        """Expose all 17 documented Results entries with title aliases."""
        self.assertEqual(len(Result), 17)
        self.assertEqual(len({r.value for r in Result}), len(Result))
        self.assertTrue(all(r.titles for r in Result))


if __name__ == "__main__":
    unittest.main()
