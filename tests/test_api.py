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

    def test_result_catalog(self):
        """Expose all 17 documented Results entries with title aliases."""
        self.assertEqual(len(Result), 17)
        self.assertEqual(len({r.value for r in Result}), len(Result))
        self.assertTrue(all(r.titles for r in Result))


if __name__ == "__main__":
    unittest.main()
