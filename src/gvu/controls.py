"""Native dialog controls, with explicit availability and writable attributes."""

from dataclasses import dataclass
from typing import Any

from .errors import ActionUnavailable


@dataclass(frozen=True)
class Control:
    path: tuple[int, ...]
    role: str
    label: str
    enabled: bool | None
    value: Any
    actions: tuple[str, ...]
    writable: tuple[str, ...]
    dialog: str = ""


def native_controls(pid, title):
    from ApplicationServices import (
        AXUIElementCopyActionNames,
        AXUIElementCopyAttributeNames,
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        AXUIElementIsAttributeSettable,
    )

    def attribute(element, name, default=None):
        error, value = AXUIElementCopyAttributeValue(element, name, None)
        return default if error or value is None else value

    app = AXUIElementCreateApplication(pid)
    windows = [
        w
        for w in attribute(app, "AXWindows", ())
        if attribute(w, "AXTitle", "") == title
    ]
    if len(windows) != 1:
        raise ActionUnavailable(
            f"Expected one native dialog {title!r}, found {len(windows)}"
        )
    result = []

    def descend(element, path, ancestor=True):
        enabled = attribute(element, "AXEnabled")
        effective = False if ancestor is False or enabled is False else enabled
        error, actions = AXUIElementCopyActionNames(element, None)
        error_attrs, attributes = AXUIElementCopyAttributeNames(element, None)
        writable = []
        for name in attributes or () if not error_attrs else ():
            error_set, allowed = AXUIElementIsAttributeSettable(element, name, None)
            if not error_set and allowed:
                writable.append(str(name))
        descriptor = Control(
            path,
            str(attribute(element, "AXRole", "")),
            str(
                attribute(element, "AXTitle")
                or attribute(element, "AXDescription")
                or ""
            ),
            effective,
            attribute(element, "AXValue"),
            tuple(actions or ()) if not error else (),
            tuple(writable),
            title,
        )
        result.append((descriptor, element))
        for index, child in enumerate(attribute(element, "AXChildren", ())):
            descend(child, (*path, index), effective)

    descend(windows[0], ())
    return result


def resolve_control(nodes, control):
    if not isinstance(control, Control):
        raise TypeError("Choose a Control from this dialog's controls()")
    matches = [
        (item, node)
        for item, node in nodes
        if item.path == control.path
        and item.role == control.role
        and item.label == control.label
        and item.dialog == control.dialog
    ]
    if len(matches) != 1:
        raise ActionUnavailable("The dialog control changed; inspect controls() again")
    if matches[0][0].enabled is False:
        raise ActionUnavailable("The dialog control is disabled")
    return matches[0]
