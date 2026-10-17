"""Public process-scoped GaussView controls and live menu discovery."""

import json
import math
import re
import time
from pathlib import Path

from .errors import ActionUnavailable
from .logging import LOG
from .menus import invoke_native, native_nodes
from .models import Alignment, Bounds, Grouping, Layout, Result, SurfaceStyle
from .viewer import application_pids, launch, validate

DEFAULT_ALIGNMENT = Alignment()


def _export_path(path):
    path = Path(path).expanduser().resolve()
    if path.exists():
        raise FileExistsError(path)
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    return path


class Session:
    """A GaussView process and the molecule groups owned by a workflow."""

    def __init__(self, backend, groups=(), owned=False):
        self.backend, self.groups, self.owned = backend, tuple(groups), owned
        self._owned_groups = list(groups) if owned else []

    @classmethod
    def open(cls, workflow, app=None, fresh=False):
        validate(workflow)
        app = (
            Path(app or Path.home() / "Applications/GaussView6/gview.app")
            .expanduser()
            .resolve()
        )
        backend, groups, reused = launch(workflow, app, fresh)
        LOG.info(
            "session_opened",
            extra={
                "metadata": {
                    "viewer_pid": backend.pid,
                    "groups": groups,
                    "reused": reused,
                }
            },
        )
        return cls(backend, groups, owned=not reused)

    @classmethod
    def attach(cls, app=None):
        from .macos import MacViewer

        app = (
            Path(app or Path.home() / "Applications/GaussView6/gview.app")
            .expanduser()
            .resolve()
        )
        pids = application_pids(app / "Contents/MacOS/gview")
        if len(pids) != 1:
            raise ActionUnavailable(
                "Attach requires exactly one running GaussView instance"
            )
        return cls(MacViewer(pids[0], None, app))

    def load(self, paths, grouping=Grouping.SEPARATE, read_intermediates=False):
        """Load documents and own exactly the new molecule groups they create."""
        from .files import input_paths
        from .macos import wait_for

        paths = input_paths(paths)
        if not isinstance(grouping, Grouping):
            raise TypeError("Supply a Grouping")

        def groups():
            return self.backend.molecule_groups()

        before = groups()
        try:
            self.backend.open_documents(paths, read_intermediates, grouping)

            def loaded():
                self.backend.check_errors()
                created = groups() - before
                expected = len(paths) if grouping is Grouping.SEPARATE else 1
                return created if len(created) == expected else None

            created = wait_for(loaded, "loaded molecule groups", timeout=45)
        except Exception:
            self._claim(groups() - before)
            raise
        ordered = sorted(created, key=lambda g: int(g[1:-1]))
        self._claim(ordered)
        return tuple(self.model(g) for g in ordered)

    def _claim(self, groups):
        for group in groups:
            if group not in self._owned_groups:
                self._owned_groups.append(group)
            if group not in self.groups:
                self.groups = (*self.groups, group)
            self.backend.group_ids.add(group)

    def compare(self, paths, name="comparison", alignment=DEFAULT_ALIGNMENT):
        """Load first-job input geometries as the frames of one molecule group."""
        from tempfile import TemporaryDirectory

        from .files import first_job, input_paths
        from .macos import wait_for

        paths = input_paths(paths)
        if not isinstance(alignment, Alignment):
            raise TypeError("Supply an Alignment")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise ValueError(
                "Comparison name must contain letters, digits, underscores or hyphens"
            )
        documents = tuple(first_job(p) for p in paths)
        with TemporaryDirectory(prefix="gvu-") as directory:
            copies = []
            for index, text in enumerate(documents):
                target = Path(directory) / (
                    name + ".gjf" if index == 0 else f"frame-{index + 1}.gjf"
                )
                target.write_text(text)
                copies.append(target)
            (model,) = self.load(copies, grouping=Grouping.TOGETHER)
            wait_for(lambda: model.frame_count == len(copies), "comparison frames")
        model.align(alignment)
        return model

    def preserve_windows(self):
        """Restore existing window bounds on exit; leave group visibility untouched."""
        from contextlib import contextmanager

        @contextmanager
        def preserve():
            windows = self.backend.windows(include_hidden=True)
            saved = {
                w["kCGWindowNumber"]: (w, Bounds.from_window(w))
                for w in windows
                if w.get("kCGWindowName")
                and w.get("kCGWindowLayer", 0) == 0
                and w["kCGWindowBounds"]["Width"] > 0
                and w["kCGWindowBounds"]["Height"] > 0
            }
            try:
                yield self
            finally:
                alive = {
                    w["kCGWindowNumber"]: w
                    for w in self.backend.windows(include_hidden=True)
                }
                for number, (_window, bounds) in saved.items():
                    if number in alive and Bounds.from_window(alive[number]) != bounds:
                        self.backend.set_bounds(alive[number], bounds)

        return preserve()

    def screens(self):
        return self.backend.screens()

    def arrange(self, models=None, style=Layout.OVERLAP, screen=None, size=(620, 390)):
        """Place only the selected models on an explicitly chosen or current display."""
        from .desktop import place_windows

        models = (
            tuple(models)
            if models is not None
            else tuple(self.model(g) for g in self.groups)
        )
        if any(model.session is not self for model in models):
            raise ValueError("Arrange models from this session")
        screen = screen or self.backend.current_screen()
        placements = place_windows(screen.work_area, len(models), style, size)
        for model, bounds in zip(models, placements, strict=True):
            model.bounds(bounds)
        return placements

    def _menu_nodes(self, root=None):
        return native_nodes(self.backend, root)

    def menus(self, root=None):
        """Read refreshed menu paths, effective enabled states and native marks."""
        self.backend.front()
        return tuple(item for item, _ in self._menu_nodes(root))

    def action(self, *path):
        """Inspect one exact menu path in the current model/dialog context."""
        if not path:
            raise ValueError("Supply a menu path")
        matches = [item for item in self.menus(path[0]) if item.path == path]
        if len(matches) != 1:
            raise ActionUnavailable(
                f"Expected one menu path {path!r}, found {len(matches)}"
            )
        return matches[0]

    def invoke(self, *path):
        """Invoke an exact enabled leaf; never choose among duplicate paths."""
        if len(path) < 2:
            raise ValueError("Supply a menu and at least one item")
        self.backend.front()
        nodes = self._menu_nodes(path[0])
        matches = [(item, node) for item, node in nodes if item.path == path]
        disabled_parent = any(
            not item.enabled and path[: len(item.path)] == item.path
            for item, _ in nodes
        )
        if len(matches) != 1 or not matches[0][0].enabled or disabled_parent:
            raise ActionUnavailable(
                "Unavailable or ambiguous menu path: " + " > ".join(path)
            )
        item, _node = matches[0]
        if item.submenu:
            raise ActionUnavailable("Choose a leaf action inside: " + " > ".join(path))
        invoke_native(self.backend, path)
        LOG.debug("menu_invoked", extra={"metadata": {"path": path}})

    def set_menu(self, *path, checked):
        """Set a checkable menu item without toggling an already matching state."""
        from .macos import wait_for

        if not isinstance(checked, bool):
            raise TypeError("Supply a boolean checked state")
        item = self.action(*path)
        if item.kind == "radio" and not checked:
            raise ValueError("Select another radio item instead of clearing this one")
        if not item.enabled or item.checked is None:
            raise ActionUnavailable(
                "Menu is disabled or has no readable checked state: " + " > ".join(path)
            )
        if item.checked != checked:
            self.invoke(*path)
            wait_for(lambda: self.action(*path).checked == checked, "menu check state")

    def settings(self):
        """Open the application's Preferences dialog through its discovered menu."""
        existing = self.backend.find("GaussView Preferences")
        if existing is None:
            actions = [
                i
                for i in self.menus()
                if len(i.path) == 2
                and i.path[0] not in {"Apple", "Help"}
                and i.path[-1].rstrip(".\u2026").casefold()
                in {"settings", "preferences"}
            ]
            if len(actions) != 1:
                raise ActionUnavailable(
                    "Cannot identify the application settings action"
                )
            self.invoke(*actions[0].path)
        window = self.backend.window("GaussView Preferences")
        return Preferences(self, window["kCGWindowName"])

    def dialog(self, title):
        windows = self.backend.windows()
        matches = [w for w in windows if w.get("kCGWindowName") == title]
        if not matches:
            matches = [w for w in windows if title in w.get("kCGWindowName", "")]
        if len(matches) != 1:
            raise ActionUnavailable(
                f"Expected one dialog {title!r}, found {len(matches)}"
            )
        return Dialog(self, matches[0]["kCGWindowName"])

    def model(self, group=None):
        group = group or next(iter(self.groups), None)
        if group is None or not re.fullmatch(r"G\d+:", group):
            raise ValueError("Supply a molecule group such as G1:")
        return ModelView(self, group)

    def result(self, result, group=None):
        if not isinstance(result, Result):
            raise TypeError("Choose a Result enum value")
        group = self.model(group).group
        window = self.backend.open_result(group, result)
        if result is Result.VIBRATIONS:
            return Vibrations(self, window["kCGWindowName"])
        if result in {
            Result.OPTIMIZATION,
            Result.EXCITATIONS,
            Result.NMR,
            Result.ORD,
            Result.VIBRONIC,
            Result.SCAN,
            Result.IRC,
            Result.TRAJECTORY,
            Result.ENERGY,
        }:
            return Plot(self, window["kCGWindowName"], group)
        return Dialog(self, window["kCGWindowName"])

    def close(self):
        """Close only groups created by this session's open, load or compare operations."""
        for group in reversed(self._owned_groups):
            for _ in range(12):
                window = next(
                    (
                        w
                        for w in self.backend.windows()
                        if w.get("kCGWindowName", "").startswith(group)
                    ),
                    None,
                )
                if window is None:
                    break
                try:
                    self.backend.apple(
                        "click button 1 of (first window whose name starts with "
                        + json.dumps(group)
                        + ")"
                    )
                except RuntimeError:
                    time.sleep(0.3)
                    if any(
                        w.get("kCGWindowName", "").startswith(group)
                        for w in self.backend.windows()
                    ):
                        raise
                    break
                time.sleep(0.4)
            else:
                raise RuntimeError(f"Could not close owned group {group}")

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()

    def _popup(self, label):
        from .macos import wait_for

        def choose():
            for window in self.backend.windows():
                if not window.get("kCGWindowName"):
                    labels = self.backend.read(window)
                    if any(t[0] == "Repeats:" for t in labels):
                        continue
                    matches = [
                        t
                        for t in labels
                        if t[0].rstrip(".").casefold() == label.rstrip(".").casefold()
                    ]
                    if len(matches) == 1:
                        return window, matches[0]
            return None

        window, target = wait_for(choose, f"popup option {label}")
        self.backend.click(target[1], target[2])
        wait_for(
            lambda: (
                not any(
                    w["kCGWindowNumber"] == window["kCGWindowNumber"]
                    for w in self.backend.windows()
                )
            ),
            "popup selection to close",
        )

    def _save(self, path, timeout=60):
        from .macos import wait_for

        path = Path(path).expanduser().resolve()
        if path.exists():
            raise FileExistsError(path)
        if not path.parent.is_dir():
            raise FileNotFoundError(path.parent)
        window = wait_for(
            lambda: next(
                (
                    w
                    for w in self.backend.windows()
                    if "save" in w.get("kCGWindowName", "").lower()
                ),
                None,
            ),
            "Save dialog",
        )
        title = json.dumps(window["kCGWindowName"])
        fields = self.backend.apple(
            "get count of text fields of (first window whose name is " + title + ")"
        ).strip()
        if fields.isdigit() and int(fields) > 0:
            self.backend.apple(
                "set value of text field 1 of (first window whose name is "
                + title
                + ") to "
                + json.dumps(str(path))
            )
        else:
            field = wait_for(
                lambda: self.backend.label(window, "File name:"), "filename field"
            )
            self.backend.click(window["kCGWindowBounds"]["X"] + 300, field[2])
            self.backend.apple(
                'keystroke "a" using command down\nkeystroke ' + json.dumps(str(path))
            )
        label = wait_for(
            lambda: next(
                (t for t in self.backend.read(window) if t[0] == "Save"), None
            ),
            "Save button",
        )
        self.backend.click(label[1], label[2])
        wait_for(
            lambda: path.is_file() and path.stat().st_size > 0,
            "exported file",
            timeout=timeout,
        )
        LOG.info(
            "file_exported",
            extra={"metadata": {"path": path, "bytes": path.stat().st_size}},
        )
        return path


class Dialog:
    """Read, click and fill controls in a process-scoped dialog."""

    def __init__(self, session, title):
        self.session, self.title = session, title

    @property
    def window(self):
        return self.session.backend.window(self.title)

    def controls(self):
        """Inspect native roles, states, values, supported actions and writable fields."""
        from .controls import native_controls

        return tuple(
            item for item, _ in native_controls(self.session.backend.pid, self.title)
        )

    def perform(self, control, action="AXPress"):
        from ApplicationServices import AXUIElementPerformAction

        from .controls import native_controls, resolve_control

        item, node = resolve_control(
            native_controls(self.session.backend.pid, self.title), control
        )
        if action not in item.actions:
            raise ActionUnavailable(f"Control does not support {action}")
        error = AXUIElementPerformAction(node, action)
        if error:
            raise ActionUnavailable(f"Native control action failed ({error})")

    def set_value(self, control, value):
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementSetAttributeValue,
        )

        from .controls import native_controls, resolve_control
        from .macos import wait_for

        item, node = resolve_control(
            native_controls(self.session.backend.pid, self.title), control
        )
        if "AXValue" not in item.writable:
            raise ActionUnavailable("The control has no writable native value")
        error = AXUIElementSetAttributeValue(node, "AXValue", value)
        if error:
            raise ActionUnavailable(f"Cannot set native control value ({error})")
        wait_for(
            lambda: AXUIElementCopyAttributeValue(node, "AXValue", None) == (0, value),
            "native control value",
        )

    def labels(self):
        return tuple(t[0] for t in self.session.backend.read(self.window))

    def click(self, label, exact=True):
        matches = [
            t
            for t in self.session.backend.read(self.window)
            if (
                t[0].casefold() == label.casefold()
                if exact
                else label.casefold() in t[0].casefold()
            )
        ]
        if len(matches) != 1:
            raise ActionUnavailable(
                f"Expected one control {label!r}, found {len(matches)}"
            )
        self.session.backend.click(matches[0][1], matches[0][2])

    def fill(self, x, y, value):
        """Set a field at explicit dialog-relative coordinates in display points."""
        bounds = self.window["kCGWindowBounds"]
        if not 0 <= x < bounds["Width"] or not 0 <= y < bounds["Height"]:
            raise ValueError("Field coordinates must be inside the dialog")
        self.session.backend.click(bounds["X"] + x, bounds["Y"] + y)
        self.session.backend.apple(
            'keystroke "a" using command down\nkeystroke ' + json.dumps(str(value))
        )

    def check(self, label, enabled=True, x=None):
        absolute_x = None if x is None else self.window["kCGWindowBounds"]["X"] + x
        self.session.backend.set_checked(self.window, label, absolute_x, bool(enabled))

    def key(self, name):
        codes = {
            "enter": 36,
            "escape": 53,
            "space": 49,
            "left": 123,
            "right": 124,
            "down": 125,
            "up": 126,
            "tab": 48,
        }
        if name not in codes:
            raise ValueError("Unknown key: " + name)
        self.session.backend.apple(f"key code {codes[name]}")

    def bounds(self, position, size):
        if len(position) != 2 or len(size) != 2 or any(v <= 0 for v in size):
            raise ValueError("Supply a position pair and a positive size pair")
        x, y = map(int, position)
        w, h = map(int, size)
        window = "(first window whose name is " + json.dumps(self.title) + ")"
        self.session.backend.apple(
            f"set size of {window} to {{{w}, {h}}}\nset position of {window} to {{{x}, {y}}}"
        )

    def choose(self, label):
        self.session._popup(label)

    def close(self):
        self.session.backend.apple(
            "click button 1 of (first window whose name is "
            + json.dumps(self.title)
            + ")"
        )


class Preferences(Dialog):
    """GaussView preference pages with explicit apply/cancel operations."""

    PAGES = (
        "Ampac Setup",
        "Building",
        "Charge Distribution",
        "Clean Controls",
        "Custom Bonding Parameters",
        "Colors",
        "Display Format",
        "File/Directory",
        "Font",
        "Gaussian Setup",
        "Icons",
        "Image",
        "Job Setup",
        "Movie, Animation",
        "Print",
        "Vibrations",
        "Window Behavior",
    )

    def pages(self):
        labels = set(self.labels())
        missing = [p for p in self.PAGES if p not in labels]
        if missing:
            raise ActionUnavailable(
                "Cannot read preference pages: " + ", ".join(missing)
            )
        return self.PAGES

    def page(self, name):
        if name not in self.pages():
            raise ValueError(f"Unknown preference page: {name}")
        previous = tuple(t for t in self.labels() if t not in self.PAGES)
        self.click(name)
        from .macos import wait_for

        try:
            wait_for(
                lambda: (
                    tuple(t for t in self.labels() if t not in self.PAGES) != previous
                ),
                "preference content to change",
                timeout=3,
            )
        except RuntimeError as error:
            raise ActionUnavailable(
                f"Cannot verify preference page {name!r}; its rendered content did not change"
            ) from error
        return self

    def apply(self):
        self.click("Ok")
        from .macos import wait_for

        wait_for(
            lambda: self.session.backend.find(self.title) is None,
            "preferences to apply",
        )

    def cancel(self):
        # GaussView's native window-close action rejects this preferences dialog.
        self.close()
        from .macos import wait_for

        wait_for(
            lambda: self.session.backend.find(self.title) is None,
            "preferences to cancel",
        )


class ModelView:
    def __init__(self, session, group):
        self.session, self.group = session, group

    @property
    def window(self):
        from .macos import wait_for

        return wait_for(
            lambda: self.session.backend.group_view(self.group), f"view {self.group}"
        )

    def activate(self):
        self.session.backend.activate(self.window)

    def menus(self, root=None):
        """Inspect native menu availability for this molecule group."""
        self.activate()
        return self.session.menus(root)

    def invoke(self, *path):
        self.activate()
        self.session.invoke(*path)

    def align(self, alignment=DEFAULT_ALIGNMENT):
        if not isinstance(alignment, Alignment):
            raise TypeError("Supply an Alignment")
        self.session.backend.align(self.group, alignment)

    def bounds(self, bounds):
        """Set a model's bounds without activating or moving other windows."""
        self.session.backend.set_bounds(self.window, bounds)

    def click(self, x, y, button="left", modifiers=()):
        """Click a view-relative point for builder, atom-selection or context actions."""
        self.drag((x, y), (x, y), button, modifiers)

    def drag(self, start, end, button="left", modifiers=()):
        """Send a scoped canvas gesture, including documented mouse modifiers."""
        if button not in ("left", "right", "middle") or any(
            m not in ("shift", "control", "alt", "command") for m in modifiers
        ):
            raise ValueError("Unknown mouse button or modifier")
        self.activate()
        b = self.window["kCGWindowBounds"]
        for x, y in (start, end):
            if not 0 <= x < b["Width"] or not 0 <= y < b["Height"]:
                raise ValueError("Gesture coordinates must lie inside the view")
        Q = self.session.backend.Q
        flags = 0
        for m in modifiers:
            flags |= {
                "shift": Q.kCGEventFlagMaskShift,
                "control": Q.kCGEventFlagMaskControl,
                "alt": Q.kCGEventFlagMaskAlternate,
                "command": Q.kCGEventFlagMaskCommand,
            }[m]
        down, up, drag, mouse = {
            "left": (
                Q.kCGEventLeftMouseDown,
                Q.kCGEventLeftMouseUp,
                Q.kCGEventLeftMouseDragged,
                Q.kCGMouseButtonLeft,
            ),
            "right": (
                Q.kCGEventRightMouseDown,
                Q.kCGEventRightMouseUp,
                Q.kCGEventRightMouseDragged,
                Q.kCGMouseButtonRight,
            ),
            "middle": (
                Q.kCGEventOtherMouseDown,
                Q.kCGEventOtherMouseUp,
                Q.kCGEventOtherMouseDragged,
                Q.kCGMouseButtonCenter,
            ),
        }[button]

        def event(kind, point):
            e = Q.CGEventCreateMouseEvent(
                None, kind, (b["X"] + point[0], b["Y"] + point[1]), mouse
            )
            Q.CGEventSetFlags(e, flags)
            Q.CGEventPost(Q.kCGHIDEventTap, e)
            time.sleep(0.05)

        event(Q.kCGEventMouseMoved, start)
        event(down, start)
        try:
            if start != end:
                for step in range(1, 11):
                    event(
                        drag, tuple(a + (z - a) * step / 10 for a, z in zip(start, end, strict=True))
                    )
        finally:
            event(up, end)

    def center(self):
        self.activate()
        self.session.invoke("View", "Center")

    def toggle(self, item, enabled):
        self.activate()
        entry = next(
            (i for i in self.session.menus() if i.path == ("View", item)), None
        )
        if entry is None or entry.checked is None:
            raise ActionUnavailable(f"Cannot read toggle state for {item}")
        if entry.checked != enabled:
            self.session.invoke("View", item)

    @property
    def frame(self):
        window = self.window
        bounds = window["kCGWindowBounds"]
        labels = [
            t
            for t in self.session.backend.read(window)
            if bounds["Y"] + 24 < t[2] < bounds["Y"] + 70 and t[0].isdigit()
        ]
        if labels:
            return int(min(labels, key=lambda t: abs(t[1] - bounds["X"] - 95))[0])
        return int(re.search(r":M(\d+):V", window["kCGWindowName"])[1])

    @property
    def frame_count(self):
        window = self.window
        b = window["kCGWindowBounds"]
        labels = [
            t
            for t in self.session.backend.read(window)
            if b["Y"] + 24 < t[2] < b["Y"] + 70
        ]
        for label in labels:
            match = re.fullmatch(r"[Oo]f\s*(\d+)", label[0])
            if match:
                return int(match[1])
            if label[0].lower() == "of":
                following = sorted(
                    (t for t in labels if t[1] > label[1] and t[0].isdigit()),
                    key=lambda t: t[1],
                )
                if following:
                    return int(following[0][0])
        return 1

    def seek(self, frame):
        if not isinstance(frame, int) or frame < 1:
            raise ValueError("Frame numbers start at one")
        self.activate()
        if frame > self.frame_count:
            raise ValueError("Frame exceeds the loaded sequence")
        b = self.window["kCGWindowBounds"]
        self.session.backend.click(b["X"] + 95, b["Y"] + 49)
        self.session.backend.enter(str(frame))
        from .macos import wait_for

        wait_for(lambda: self.frame == frame, f"frame {frame}")

    @property
    def playing(self):
        from AppKit import NSBitmapImageRep

        window = self.window
        b = window["kCGWindowBounds"]
        Q = self.session.backend.Q
        image = Q.CGWindowListCreateImage(
            Q.CGRectNull,
            Q.kCGWindowListOptionIncludingWindow,
            window["kCGWindowNumber"],
            Q.kCGWindowImageBoundsIgnoreFraming,
        )
        if image is None:
            raise ActionUnavailable("Cannot read animation state")
        bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
        sx, sy = bitmap.pixelsWide() / b["Width"], bitmap.pixelsHigh() / b["Height"]
        red = green = dark = 0
        for x in range(38, 55, 2):
            for y in range(42, 59, 2):
                color = bitmap.colorAtX_y_(int(x * sx), int(y * sy))
                r, g, blue = (
                    color.redComponent(),
                    color.greenComponent(),
                    color.blueComponent(),
                )
                red += r > 0.15 and r > g + 0.1 and r > blue + 0.1
                green += g > 0.15 and g > r + 0.1 and g > blue + 0.1
                dark += (
                    max(r, g, blue) < 0.6 and max(r, g, blue) - min(r, g, blue) < 0.12
                )
        if max(red, green) < 5:
            # This legacy macOS build renders the stop glyph without color.
            if dark > 5 and self.frame_count > 1:
                return True
            before = self.frame
            for _ in range(8):
                time.sleep(0.05)
                if self.frame != before:
                    return True
            raise ActionUnavailable("Cannot determine molecule-group playback state")
        return red > green

    def animation(
        self, repeats=None, sequence=None, frame_delay=None, endpoint_delay=None
    ):
        """Configure the native molecule-group playback controls."""
        from .macos import wait_for

        for value in (frame_delay, endpoint_delay):
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError(
                    "Animation delays must be nonnegative integer milliseconds"
                )
        self.activate()
        backend = self.session.backend
        b = self.window["kCGWindowBounds"]
        backend.click(b["X"] + 70, b["Y"] + 50)

        def options():
            return next(
                (
                    w
                    for w in backend.windows()
                    if not w.get("kCGWindowName") and backend.label(w, "Repeats:")
                ),
                None,
            )

        window = wait_for(options, "animation options")
        bounds = window["kCGWindowBounds"]
        for label, value in (("Repeats:", repeats), ("Sequence:", sequence)):
            if value is not None:
                control = backend.label(window, label)
                backend.click(bounds["X"] + 215, control[2])
                self.session._popup(str(value))
        for label, value in (
            ("Frame Delay (msec):", frame_delay),
            ("Endpoint Delay (msec):", endpoint_delay),
        ):
            if value is not None:
                control = backend.label(window, label)
                backend.click(bounds["X"] + 205, control[2])
                backend.apple(
                    'keystroke "a" using command down\nkeystroke '
                    + json.dumps(str(value))
                    + "\nkey code 48"
                )
        backend.apple("key code 53")
        # Escape may close a combo list first; an outside title-bar click closes
        # the containing Qt options popup before the playback button is used.
        backend.click(b["X"] + 200, b["Y"] + 14)
        wait_for(
            lambda: (
                not any(
                    w["kCGWindowNumber"] == window["kCGWindowNumber"]
                    for w in backend.windows()
                )
            ),
            "animation options to close",
        )
        LOG.debug(
            "animation_configured",
            extra={
                "metadata": {
                    "repeats": repeats,
                    "sequence": sequence,
                    "frame_delay_ms": frame_delay,
                    "endpoint_delay_ms": endpoint_delay,
                }
            },
        )

    def _playback(self, enabled):
        from .macos import wait_for

        if self.playing == enabled:
            return
        if enabled:
            self.activate()
        else:
            self.session.backend.front(force=True)
        b = self.window["kCGWindowBounds"]
        self.session.backend.click(b["X"] + 46, b["Y"] + 50)

        def matches():
            try:
                return self.playing == enabled
            except ActionUnavailable:
                return False

        wait_for(matches, "animation playback state")

    def play(self, loop=True, frame_delay=100):
        if self.playing:
            return
        self.animation(repeats="Endless" if loop else "None", frame_delay=frame_delay)
        if self.frame == self.frame_count:
            self.seek(1)
        if loop:
            self._playback(True)
        else:
            self.activate()
            b = self.window["kCGWindowBounds"]
            self.session.backend.click(b["X"] + 46, b["Y"] + 50)

    def pause(self):
        self._playback(False)

    def transform(self, operation, axis, amount, frame="View"):
        if (
            operation not in ("Rotate", "Translate")
            or axis not in ("X", "Y", "Z")
            or frame not in ("View", "Mol")
        ):
            raise ValueError("Choose Rotate/Translate, axis X/Y/Z, and View/Mol frame")
        if not isinstance(amount, (int, float)) or not math.isfinite(amount):
            raise ValueError("Transformation amount must be finite")
        self.activate()
        backend = self.session.backend
        toolbar = next(
            (
                i
                for i in self.session.menus("View")
                if i.path == ("View", "Positioning Tools")
            ),
            None,
        )
        was_visible = toolbar is not None and toolbar.checked is True
        if not was_visible:
            self.session.invoke("View", "Positioning Tools")
        from .macos import wait_for

        mode = wait_for(
            lambda: next(
                (
                    t
                    for t in backend.read(self.window)
                    if re.match(r"^(Rotate|Translate)\b", t[0])
                ),
                None,
            ),
            "positioning mode",
        )
        if mode is None:
            raise ActionUnavailable("Cannot locate positioning mode")
        if not mode[0].startswith(operation):
            backend.click(mode[1], mode[2])
            self.session._popup(operation)
        axis_label = wait_for(
            lambda: backend.label(
                self.window, "Around" if operation == "Rotate" else "Along"
            ),
            "axis selector",
        )
        backend.click(axis_label[3] + 100, axis_label[2])
        self.session._popup(f"{frame} {axis}")
        by = wait_for(lambda: backend.label(self.window, "By"), "transformation amount")
        backend.click(by[3] + 55, by[2])
        backend.apple(
            'keystroke "a" using command down\nkeystroke ' + json.dumps(str(amount))
        )
        apply = wait_for(lambda: backend.label(self.window, "Apply"), "Apply button")
        backend.click(apply[1], apply[2])
        if not was_visible:
            self.session.invoke("View", "Positioning Tools")

    def rotate(self, axis, degrees, frame="View"):
        self.transform("Rotate", axis, degrees, frame)

    def translate(self, axis, distance, frame="View"):
        self.transform("Translate", axis, distance, frame)

    def surface_style(self, style=SurfaceStyle.TRANSPARENT, opacity=0.5):
        self.session.backend.surface_format(self.group, style, opacity)

    def scale(self, lower, upper):
        if not all(math.isfinite(x) for x in (lower, upper)) or lower >= upper:
            raise ValueError("Supply finite, increasing color bounds")
        self.session.backend.color_range = (f"{lower:.4f}", f"{upper:.4f}")
        self.session.backend.apply_scale(self.group)

    def image(self, path):
        path = _export_path(path)
        self.activate()
        self.session.invoke("File", "Save Image...")
        return self.session._save(path)

    def save(self, path):
        path = _export_path(path)
        before = {
            w["kCGWindowName"].split(":")[0] + ":"
            for w in self.session.backend.windows()
            if re.match(r"G\d+:", w.get("kCGWindowName", ""))
        }
        self.activate()
        self.session.invoke("File", "Save...")
        result = self.session._save(path)
        created = {
            w["kCGWindowName"].split(":")[0] + ":"
            for w in self.session.backend.windows()
            if str(result) in w.get("kCGWindowName", "")
            and re.match(r"G\d+:", w.get("kCGWindowName", ""))
        } - before
        for group in sorted(created):
            self.session._owned_groups.append(group)
            self.session.groups = (*self.session.groups, group)
        return result

    def movie(self, path):
        path = _export_path(path)
        if self.frame_count > 1:
            self.pause()
        self.activate()
        self.session.invoke("File", "Save Movie", "Save Movie File...")
        return self.session._save(path, timeout=180)


class Plot(Dialog):
    def __init__(self, session, title, group):
        super().__init__(session, title)
        self.group = group

    def _context(self, action):
        backend = self.session.backend
        backend.front(force=True)
        backend.apple(
            'perform action "AXRaise" of (first window whose name is '
            + json.dumps(self.title)
            + ")"
        )
        time.sleep(0.15)
        b = self.window["kCGWindowBounds"]
        x, y = b["X"] + b["Width"] / 2, b["Y"] + b["Height"] / 2
        Q = backend.Q
        for kind in (
            Q.kCGEventMouseMoved,
            Q.kCGEventRightMouseDown,
            Q.kCGEventRightMouseUp,
        ):
            Q.CGEventPost(
                Q.kCGHIDEventTap,
                Q.CGEventCreateMouseEvent(None, kind, (x, y), Q.kCGMouseButtonRight),
            )
            time.sleep(0.1)
        self.session._popup(action)

    def data(self, path):
        path = _export_path(path)
        self._context("Save Data")
        return self.session._save(path)

    def image(self, path):
        path = _export_path(path)
        self._context("Save Picture")
        return self.session._save(path)

    def properties(self):
        self._context("Properties")
        return self.session.dialog("Properties")


class Vibrations(Dialog):
    """Normal-mode selection, animation and native movie export."""

    def _animation(self, enabled):
        from .macos import wait_for

        def control():
            labels = self.session.backend.read(self.window)
            return next(
                (t for t in labels if re.match(r"^(Start|Stop) Animatio[nr]", t[0])),
                None,
            )

        button = wait_for(control, "vibration animation button")
        if button[0].startswith("Stop") == enabled:
            return
        self.session.backend.click(button[1], button[2])
        wait_for(
            lambda: (b := control()) and b[0].startswith("Stop") == enabled,
            "vibration animation state",
        )

    def play(self):
        self._animation(True)

    def pause(self):
        self._animation(False)

    def mode(self, index):
        if not isinstance(index, int) or index < 1:
            raise ValueError("Mode indices start at one")
        backend = self.session.backend
        previous = None
        for _ in range(30):
            labels = backend.read(self.window)
            header = next((t for t in labels if t[0] == "Mode #"), None)
            frequency = next((t for t in labels if t[0] == "Frequency"), None)
            bottom = next(
                (t for t in labels if t[0].startswith("Animate Vibration")), None
            )
            if header is None or frequency is None or bottom is None:
                raise ActionUnavailable("Cannot locate the normal-mode table")
            rows = [
                t
                for t in labels
                if t[0].isdigit()
                and header[3] - 5 < t[1] < (header[1] + frequency[1]) / 2
                and header[2] < t[2] < bottom[2]
            ]
            matches = [t for t in rows if int(t[0]) == index]
            if len(matches) == 1:
                backend.click(matches[0][1], matches[0][2])
                return
            visible = tuple(int(t[0]) for t in sorted(rows, key=lambda t: t[2]))
            if not visible or visible == previous:
                break
            previous = visible
            direction = 1 if index < min(visible) else -1
            Q = backend.Q
            point = (frequency[1], (header[2] + bottom[2]) / 2)
            Q.CGEventPost(
                Q.kCGHIDEventTap,
                Q.CGEventCreateMouseEvent(
                    None, Q.kCGEventMouseMoved, point, Q.kCGMouseButtonLeft
                ),
            )
            Q.CGEventPost(
                Q.kCGHIDEventTap,
                Q.CGEventCreateScrollWheelEvent(
                    None, Q.kCGScrollEventUnitLine, 1, direction * 4
                ),
            )
            time.sleep(0.25)
        raise ActionUnavailable(
            f"Mode {index} is not available in the normal-mode table"
        )

    def movie(self, path):
        path = _export_path(path)
        self.pause()
        self.click("Save Movie...")
        self.session._popup("Save Movie File...")
        return self.session._save(path, timeout=180)
