"""Live menu discovery, native state and exact action addressing."""

import re
from dataclasses import dataclass

from .errors import ActionUnavailable


@dataclass(frozen=True)
class Shortcut:
    """Native macOS shortcut attributes; modifiers use AX's bit mask."""

    character: str | None = None
    modifiers: int | None = None
    glyph: int | None = None
    key: int | None = None


@dataclass(frozen=True)
class MenuItem:
    path: tuple[str, ...]
    enabled: bool
    checked: bool | None = None
    submenu: bool = False
    native_enabled: bool = True
    shortcut: Shortcut | None = None
    mark: str | None = None

    @property
    def kind(self):
        if self.submenu:
            return "submenu"
        if self.checked is None:
            return "action"
        if self.path[0] == "Builder" or (
            self.path[0] == "Windows" and len(self.path) == 2
        ):
            return "radio"
        return "toggle"


def checkable(path):
    """Unmarked native commands are distinct from unchecked toggles/radio items."""
    return (
        len(path) == 2
        and path[0] == "View"
        and path[1]
        in {
            "Builder",
            "Hydrogens",
            "Dummies",
            "Labels",
            "Symbols",
            "Bonds",
            "Synchronize",
            "Cartesian Axes",
            "Stereochemistry",
            "Positioning Tools",
        }
        or len(path) == 2
        and path[0] == "Builder"
        and path[1]
        in {
            "Inquire...",
            "Add Valence",
            "Delete Atom",
            "Invert Atom",
            "Select Atoms by Clicking",
            "Select Atoms by Rubberband",
            "Select Atoms by Brush",
        }
        or len(path) == 3
        and path[:2] == ("Windows", "Show Molecule Groups")
        and re.fullmatch(r"G\d+", path[2]) is not None
        or len(path) == 2
        and path[0] == "Windows"
        and re.match(r"G\d+:M\d+:V\d+", path[1]) is not None
    )


class MenuReader:
    """Read an AX menu tree through an injectable native adapter."""

    def __init__(self, attribute, children, refresh):
        self.attribute, self.children, self.refresh = attribute, children, refresh

    def nodes(self, roots, root=None):
        nodes = []
        matches = (
            [r for r in roots if self.attribute(r, "AXTitle", "").strip() == root]
            if root
            else [
                r for r in roots if self.attribute(r, "AXTitle", "").strip() != "Apple"
            ]
        )
        if root and len(matches) != 1:
            raise ActionUnavailable(f"Expected one menu {root!r}, found {len(matches)}")

        def descend(element, prefix, ancestor):
            for child in self.children(element):
                role = self.attribute(child, "AXRole", "")
                if role == "AXMenu":
                    descend(child, prefix, ancestor)
                elif role == "AXMenuItem":
                    title = str(self.attribute(child, "AXTitle", "")).strip()
                    if not title:
                        continue
                    path = (*prefix, title)
                    native = bool(self.attribute(child, "AXEnabled", False))
                    enabled = ancestor and native
                    children = self.children(child)
                    submenu = any(
                        self.attribute(c, "AXRole", "") == "AXMenu" for c in children
                    )
                    mark = self.attribute(child, "AXMenuItemMarkChar", None)
                    checked = (
                        bool(mark) if checkable(path) or mark is not None else None
                    )
                    char = self.attribute(child, "AXMenuItemCmdChar", None)
                    glyph = self.attribute(child, "AXMenuItemCmdGlyph", None)
                    key = self.attribute(child, "AXMenuItemCmdVirtualKey", None)
                    shortcut = (
                        Shortcut(
                            char,
                            self.attribute(child, "AXMenuItemCmdModifiers", None),
                            glyph,
                            key,
                        )
                        if char or glyph or key is not None
                        else None
                    )
                    nodes.append(
                        (
                            MenuItem(
                                path, enabled, checked, submenu, native, shortcut, mark
                            ),
                            child,
                        )
                    )
                    descend(child, path, enabled)

        for item in matches:
            title = str(self.attribute(item, "AXTitle", "")).strip()
            enabled = bool(self.attribute(item, "AXEnabled", True))
            if enabled:
                self.refresh(item)
            nodes.append(
                (
                    MenuItem((title,), enabled, submenu=True, native_enabled=enabled),
                    item,
                )
            )
            descend(item, (title,), enabled)
        return nodes


def native_nodes(backend, root=None):
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        AXUIElementPerformAction,
    )

    def attribute(element, name, default=None):
        error, value = AXUIElementCopyAttributeValue(element, name, None)
        return default if error or value is None else value

    def children(element):
        return attribute(element, "AXChildren", ())

    def refresh(element):
        from .macos import wait_for

        # macOS menu tracking can ignore Escape sent through System Events.
        # Cancel the native AXMenu itself and verify that tracking has ended.
        error = AXUIElementPerformAction(element, "AXPress")
        if error:
            raise ActionUnavailable(
                f"Cannot refresh menu {attribute(element, 'AXTitle', '')!r} ({error})"
            )
        wait_for(
            lambda: (
                attribute(element, "AXSelected", False)
                and any(w.get("kCGWindowLayer") == 101 for w in backend.windows())
            ),
            "native menu to become visible",
            timeout=3,
        )
        menus = [c for c in children(element) if attribute(c, "AXRole", "") == "AXMenu"]
        if len(menus) != 1:
            raise ActionUnavailable("Cannot identify the open native menu")
        error = AXUIElementPerformAction(element, "AXCancel")
        AXUIElementPerformAction(menus[0], "AXCancel")
        if error:
            raise ActionUnavailable(f"Cannot close native menu ({error})")
        wait_for(
            lambda: not attribute(element, "AXSelected", False),
            "menu to close",
            timeout=3,
        )

    app = AXUIElementCreateApplication(backend.pid)
    bar = attribute(app, "AXMenuBar")
    if bar is None:
        raise ActionUnavailable(
            "Cannot read the app menu bar; check Accessibility permissions"
        )
    return MenuReader(attribute, children, refresh).nodes(children(bar), root)


def invoke_native(backend, path):
    """Dispatch from refreshed nodes after native menu tracking has ended."""
    from ApplicationServices import AXUIElementPerformAction

    nodes = native_nodes(backend, path[0])
    matches = [(item, node) for item, node in nodes if item.path == path]
    if len(matches) != 1 or not matches[0][0].enabled or matches[0][0].submenu:
        raise ActionUnavailable(
            "Unavailable or ambiguous menu action: " + " > ".join(path)
        )
    error = AXUIElementPerformAction(matches[0][1], "AXPress")
    root_node = next(node for item, node in nodes if item.path == path[:1])
    AXUIElementPerformAction(root_node, "AXCancel")
    if error:
        raise ActionUnavailable(f"Cannot invoke {path!r} ({error})")
