"""Menu coverage and dynamic native state contracts."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from gvu import ActionUnavailable, MenuItem, Session
from gvu.menus import MenuReader


def node(title, children=(), role="AXMenuItem", **attributes):
    return {
        "AXTitle": title,
        "AXRole": role,
        "AXEnabled": True,
        "AXChildren": list(children),
        **attributes,
    }


def menu(title, *items, **attributes):
    return node(title, [node("", items, "AXMenu")], "AXMenuBarItem", **attributes)


def reader():
    return MenuReader(
        lambda n, key, default=None: n.get(key, default),
        lambda n: n.get("AXChildren", ()),
        Mock(),
    )


class MenuTests(unittest.TestCase):
    def test_all_roots(self):
        """Include every app menu and normalize Help's native trailing space."""
        names = (
            "GaussView",
            "File",
            "Edit",
            "Tools",
            "Builder",
            "View",
            "Calculate",
            "Results",
            "Windows",
            "Help ",
        )
        roots = [menu(name, node("Action")) for name in names]
        rows = reader().nodes(roots)
        self.assertEqual(
            [i.path[0] for i, _ in rows if len(i.path) == 1], [n.strip() for n in names]
        )
        self.assertTrue(any(i.path == ("Help", "Action") for i, _ in rows))

    def test_parent_state(self):
        """Expose both native leaf state and effective disabled-parent state."""
        nested = node(
            "Unavailable", [node("", [node("Child")], "AXMenu")], AXEnabled=False
        )
        rows = reader().nodes([menu("Calculate", nested)])
        item = next(i for i, _ in rows if i.path[-1] == "Child")
        self.assertTrue(item.native_enabled)
        self.assertFalse(item.enabled)

    def test_unchecked_items(self):
        """Distinguish unchecked toggles, unselected radio items and plain commands."""
        roots = [
            menu(
                "Builder",
                node("Inquire..."),
                node("Add Valence", AXMenuItemMarkChar="x"),
            ),
            menu(
                "Windows",
                node("Show Molecule Groups", [node("", [node("G2")], "AXMenu")]),
            ),
            menu("File", node("Open...")),
        ]
        items = {i.path: i for i, _ in reader().nodes(roots)}
        self.assertIs(items[("Builder", "Inquire...")].checked, False)
        self.assertIs(items[("Builder", "Add Valence")].checked, True)
        self.assertIs(items[("Windows", "Show Molecule Groups", "G2")].checked, False)
        self.assertIsNone(items[("File", "Open...")].checked)

    def test_service_children(self):
        """Index nested Services entries rather than stopping at their parent."""
        services = node(
            "Services", [node("", [node("Example", AXEnabled=False)], "AXMenu")]
        )
        rows = reader().nodes([menu("GaussView", services)])
        self.assertIn(("GaussView", "Services", "Example"), [i.path for i, _ in rows])

    def test_native_shortcut(self):
        """Preserve keyboard shortcuts without conflating them with checked marks."""
        rows = reader().nodes(
            [
                menu(
                    "File",
                    node("Open...", AXMenuItemCmdChar="O", AXMenuItemCmdModifiers=0),
                )
            ]
        )
        item = next(i for i, _ in rows if len(i.path) == 2)
        self.assertEqual(item.shortcut.character, "O")
        self.assertEqual(item.shortcut.modifiers, 0)
        self.assertIsNone(item.checked)

    def test_dynamic_refresh(self):
        """Refresh native menus before reading dynamically populated children."""
        root = menu("File")
        r = reader()
        r.refresh.side_effect = lambda element: element["AXChildren"][0][
            "AXChildren"
        ].append(node("Recent"))
        self.assertIn(("File", "Recent"), [i.path for i, _ in r.nodes([root])])
        r.refresh.assert_called_once_with(root)

    def test_disabled_root(self):
        """Read disabled roots without trying to open them through a modal dialog."""
        r = reader()
        rows = r.nodes([menu("Edit", node("Copy"), AXEnabled=False)])
        self.assertTrue(all(not i.enabled for i, _ in rows))
        r.refresh.assert_not_called()

    def test_root_failure(self):
        """Report missing or duplicate top-level names rather than returning emptiness."""
        with self.assertRaises(ActionUnavailable):
            reader().nodes([menu("File")], "Unknown")
        with self.assertRaises(ActionUnavailable):
            reader().nodes([menu("File"), menu("File ")], "File")

    def test_ambiguous_action(self):
        """Refuse duplicate native paths before issuing an action."""
        s = Session(SimpleNamespace(front=Mock()))
        s._menu_nodes = lambda root: [(MenuItem(("File", "Open..."), True), None)] * 2
        with self.assertRaises(ActionUnavailable):
            s.invoke("File", "Open...")

    def test_submenu_action(self):
        """Require a leaf command instead of pretending a submenu executes an action."""
        s = Session(SimpleNamespace(front=Mock()))
        s._menu_nodes = lambda root: [
            (MenuItem(("File", "Save Movie"), True, submenu=True), None)
        ]
        with self.assertRaises(ActionUnavailable):
            s.invoke("File", "Save Movie")

    def test_toggle_state(self):
        """Setting the requested state twice must not toggle it back."""
        s = Session(None)
        state = {"checked": False}
        s.action = lambda *path: MenuItem(path, True, state["checked"])
        s.invoke = Mock(side_effect=lambda *path: state.update(checked=True))
        s.set_menu("View", "Labels", checked=True)
        s.set_menu("View", "Labels", checked=True)
        s.invoke.assert_called_once_with("View", "Labels")


class ControlTests(unittest.TestCase):
    def test_disabled_control(self):
        """Refuse disabled native controls before dispatching their actions."""
        from gvu import Control
        from gvu.controls import resolve_control

        item = Control((0,), "AXButton", "Save", False, None, ("AXPress",), ())
        with self.assertRaises(ActionUnavailable):
            resolve_control([(item, None)], item)

    def test_changed_control(self):
        """Refuse a path now occupied by a different control."""
        from gvu import Control
        from gvu.controls import resolve_control

        old = Control((0,), "AXButton", "Save", True, None, ("AXPress",), ())
        new = Control((0,), "AXButton", "Delete", True, None, ("AXPress",), ())
        with self.assertRaises(ActionUnavailable):
            resolve_control([(new, None)], old)

    def test_radio_clear(self):
        """Require selection of another radio item rather than impossible deselection."""
        s = Session(None)
        s.action = lambda *path: MenuItem(path, True, True)
        with self.assertRaises(ValueError):
            s.set_menu("Builder", "Inquire...", checked=False)
