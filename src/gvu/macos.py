"""macOS GaussView 6 controls, scoped to one process and workflow."""

import json
import random
import re
import subprocess
import time

from .errors import ActionUnavailable
from .models import Alignment, Bounds, Grouping, Result, Screen, SurfaceStyle


def wait_for(check, description, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.15)
    raise RuntimeError(f"Timed out waiting for {description}")


def window_reference(title):
    """Address a view without the frame number that changes during playback."""
    match = re.fullmatch(r"(G\d+:)M\d+(:V\d+(?: \(Job #\d+\))? - .+)", title)
    if match:
        return (
            "(first window whose name starts with "
            + json.dumps(match[1])
            + " and name ends with "
            + json.dumps(match[2])
            + ")"
        )
    return "(first window whose name is " + json.dumps(title) + ")"


class MacViewer:
    """Bound every menu, window lookup and screenshot to this viewer process."""

    def __init__(self, pid, workflow, app, color_range=None):
        self.pid = pid
        self.app = app
        self.workflow = workflow
        self.color_range = color_range
        self.surfaces = {s.name: s for s in workflow.surfaces} if workflow else {}
        self.group_ids = set()
        import Quartz
        import Vision

        self.Q = Quartz
        self.V = Vision

    def apple(self, commands):
        if "keystroke" in commands or "key code" in commands:
            self.front()
        script = (
            'tell application "System Events"\n'
            f"  tell (first application process whose unix id is {self.pid})\n"
            + commands
            + "\nend tell\nend tell"
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    def windows(self, include_hidden=False):
        return [
            dict(w)
            for w in self.Q.CGWindowListCopyWindowInfo(
                self.Q.kCGWindowListOptionAll
                if include_hidden
                else self.Q.kCGWindowListOptionOnScreenOnly,
                self.Q.kCGNullWindowID,
            )
            if w.get("kCGWindowOwnerPID") == self.pid
        ]

    def molecule_groups(self):
        from .menus import native_nodes

        self.front()
        return {
            item.path[2] + ":"
            for item, _ in native_nodes(self, "Windows")
            if len(item.path) == 3
            and item.path[:2] == ("Windows", "Show Molecule Groups")
            and re.fullmatch(r"G\d+", item.path[2])
        }

    def check_errors(self):
        for window in self.windows():
            if not window.get("kCGWindowName"):
                labels = [t[0] for t in self.read(window)]
                if any(
                    any(
                        word in t.lower()
                        for word in (
                            "failure reading",
                            "error reading",
                            "unknown file type",
                        )
                    )
                    for t in labels
                ):
                    raise ActionUnavailable(
                        "GaussView rejected the input: " + "; ".join(labels)
                    )

    def find(self, text):
        return next(
            (w for w in self.windows() if text in w.get("kCGWindowName", "")), None
        )

    def window(self, text):
        return wait_for(lambda: self.find(text), f"window {text!r}")

    def read(self, window):
        capture = self.Q.CGWindowListCreateImage(
            self.Q.CGRectNull,
            self.Q.kCGWindowListOptionIncludingWindow,
            window["kCGWindowNumber"],
            self.Q.kCGWindowImageBoundsIgnoreFraming,
        )
        if capture is None:
            raise RuntimeError(
                "Cannot read GaussView; enable Screen Recording for your terminal/Codex."
            )
        request = self.V.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(0)
        request.setUsesCPUOnly_(True)
        request.setUsesLanguageCorrection_(False)
        handler = self.V.VNImageRequestHandler.alloc().initWithCGImage_options_(
            capture, {}
        )
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            raise RuntimeError(f"Cannot read GaussView controls: {error}")
        bounds = window["kCGWindowBounds"]
        labels = []
        for observation in request.results():
            box = observation.boundingBox()
            labels.append(
                (
                    str(observation.topCandidates_(1)[0].string()),
                    bounds["X"] + (box.origin.x + box.size.width / 2) * bounds["Width"],
                    bounds["Y"]
                    + (1 - box.origin.y - box.size.height / 2) * bounds["Height"],
                    bounds["X"] + box.origin.x * bounds["Width"],
                )
            )
        return labels

    def label(self, window, text):
        return next(
            (t for t in self.read(window) if text.lower() in t[0].lower()), None
        )

    def set_checked(self, window, label_text, checkbox_x=None, enabled=True):
        # Legacy Qt exposes these checkboxes as pixels rather than AX controls.
        # Its checked blue fill contrasts with the empty white checkbox interior.
        from AppKit import NSBitmapImageRep

        label = wait_for(lambda: self.label(window, label_text), label_text)
        # OCR can merge the checkmark into the label when already checked.
        offset = -12 if label[0].lower().startswith(label_text.lower()) else 6
        x, y = (label[3] + offset if checkbox_x is None else checkbox_x), label[2]

        def is_checked():
            image = self.Q.CGWindowListCreateImage(
                self.Q.CGRectNull,
                self.Q.kCGWindowListOptionIncludingWindow,
                window["kCGWindowNumber"],
                self.Q.kCGWindowImageBoundsIgnoreFraming,
            )
            if image is None:
                raise RuntimeError("Cannot inspect GaussView checkbox")
            bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
            b = window["kCGWindowBounds"]
            sx, sy = bitmap.pixelsWide() / b["Width"], bitmap.pixelsHigh() / b["Height"]
            return (
                sum(
                    bitmap.colorAtX_y_(
                        int((x - b["X"] + dx) * sx), int((y - b["Y"] + dy) * sy)
                    ).redComponent()
                    < 0.6
                    for dx in range(-2, 3)
                    for dy in range(-2, 3)
                )
                > 5
            )

        if is_checked() != enabled:
            self.click(x, y)
            wait_for(lambda: is_checked() == enabled, f"checkbox {label_text}")

    def ensure_intermediate_geometries(self, enabled=True):
        options = self.find("Options for Opening Files")
        if options is None:
            dialog = self.find("Open Files")
            if dialog is None:
                self.menu("File", "Open...")
                dialog = self.window("Open Files")
            label = wait_for(lambda: self.label(dialog, "Options..."), "Open options")
            self.click(label[1], label[2])
            options = self.window("Options for Opening Files")
        for text in (
            "Read Intermediate Geometries (Optimizations)",
            "Read Intermediate Geometries (Scans/IRCs)",
        ):
            self.set_checked(
                options, text, options["kCGWindowBounds"]["X"] + 20, enabled=enabled
            )
        label = wait_for(
            lambda: next((t for t in self.read(options) if t[0].lower() == "ok"), None),
            "OK",
        )
        self.click(label[1], label[2])
        dialog = self.window("Open Files")
        self.set_checked(dialog, "Retain Settings")

    def open_documents(
        self, paths, read_intermediates=False, grouping=Grouping.SEPARATE
    ):
        from .api import Session
        from .files import input_paths

        paths = input_paths(paths)
        if not isinstance(grouping, Grouping):
            raise TypeError("Supply a Grouping")
        self.ensure_intermediate_geometries(enabled=read_intermediates)
        dialog = self.window("Open Files")
        target = wait_for(
            lambda: next(
                (t for t in self.read(dialog) if "new molecule group" in t[0].lower()),
                None,
            ),
            "file grouping",
        )
        if target[0] != grouping.value:
            self.click(target[1], target[2])
            Session(self)._popup(grouping.value)
        field = wait_for(lambda: self.label(dialog, "File name:"), "filename field")
        self.click(dialog["kCGWindowBounds"]["X"] + 300, field[2])
        filenames = " ".join('"' + str(p) + '"' for p in paths)
        self.apple(
            'keystroke "a" using command down\nkeystroke ' + json.dumps(filenames)
        )
        button = wait_for(
            lambda: next((t for t in self.read(dialog) if t[0] == "Open"), None),
            "Open button",
        )
        self.click(button[1], button[2])
        wait_for(lambda: self.find("Open Files") is None, "files to open")

    def select_file_jobs(self):
        """Load every linked job when GaussView asks which file sections to read."""
        dialog = self.find("Select Jobs from File")
        if dialog is None:
            return False
        labels = self.read(dialog)
        header = next((label for label in labels if label[0] == "Job Type"), None)
        button = next((label for label in labels if label[0].lower() == "ok"), None)
        if header is None or button is None:
            raise ActionUnavailable("Cannot identify the linked-job table and confirmation button")
        # Focus the table below its header, then use its native Select All action.
        self.click(header[1], header[2] + 30)
        self.apple('keystroke "a" using command down')
        self.click(button[1], button[2])
        wait_for(lambda: self.find("Select Jobs from File") is None, "selected jobs to load")
        return True

    def click(self, x, y, button="left"):
        buttons = {
            "left": (
                self.Q.kCGMouseButtonLeft,
                self.Q.kCGEventLeftMouseDown,
                self.Q.kCGEventLeftMouseUp,
            ),
            "middle": (
                self.Q.kCGMouseButtonCenter,
                self.Q.kCGEventOtherMouseDown,
                self.Q.kCGEventOtherMouseUp,
            ),
            "right": (
                self.Q.kCGMouseButtonRight,
                self.Q.kCGEventRightMouseDown,
                self.Q.kCGEventRightMouseUp,
            ),
        }
        if button not in buttons:
            raise ValueError("Choose left, middle or right mouse button")
        native_button, down, up = buttons[button]
        self.front()
        self.Q.CGEventPost(
            self.Q.kCGHIDEventTap,
            self.Q.CGEventCreateMouseEvent(None, self.Q.kCGEventMouseMoved, (x, y), native_button),
        )
        time.sleep(0.1)
        for kind in (down, up):
            event = self.Q.CGEventCreateMouseEvent(None, kind, (x, y), native_button)
            self.Q.CGEventPost(self.Q.kCGHIDEventTap, event)
            time.sleep(0.06)
        time.sleep(0.35)

    def menu(self, menu, item):
        from .menus import invoke_native

        self.front()
        invoke_native(self, (menu, item))
        time.sleep(0.25)

    def front(self, force=False):
        from AppKit import (
            NSApplicationActivateIgnoringOtherApps,
            NSWorkspace,
        )
        from Foundation import NSDate, NSRunLoop

        def active():
            # Deliver workspace activation notifications before consulting AppKit's cache.
            NSRunLoop.currentRunLoop().runUntilDate_(
                NSDate.dateWithTimeIntervalSinceNow_(0.02)
            )
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return app is not None and app.processIdentifier() == self.pid

        already_active = active()
        if force or not already_active:
            app = next(
                (
                    candidate
                    for candidate in NSWorkspace.sharedWorkspace().runningApplications()
                    if candidate.processIdentifier() == self.pid
                ),
                None,
            )
            if app is None:
                raise RuntimeError("GaussView is no longer running")
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            wait_for(active, "GaussView app activation", timeout=5)
            time.sleep(0.25)

    def activate(self, window):
        """Focus a model without moving it or any other window."""
        self.front(force=True)
        title = window["kCGWindowName"]
        target = window_reference(title)
        # The native Windows menu selects the model even when AXRaise alone
        # raises its Qt shell without changing the active molecule group.
        self.apple(
            "set targetName to name of " + target + "\n"
            'click menu bar item "Windows" of menu bar 1\n'
            'click menu item targetName of menu "Windows" '
            'of menu bar item "Windows" of menu bar 1\n'
            'perform action "AXRaise" of ' + target
        )
        wait_for(
            lambda: (
                next(
                    (w for w in self.windows() if w.get("kCGWindowLayer", 0) == 0), {}
                ).get("kCGWindowNumber")
                == window["kCGWindowNumber"]
            ),
            "active molecule window",
        )

    def set_bounds(self, window, bounds):
        if not isinstance(bounds, Bounds):
            raise TypeError("Supply Bounds")
        target = window_reference(window["kCGWindowName"])
        self.apple(
            f"set size of {target} to {{{round(bounds.width)}, {round(bounds.height)}}}\n"
            f"set position of {target} to {{{round(bounds.x)}, {round(bounds.y)}}}"
        )

        def settled():
            current = next(
                (
                    w
                    for w in self.windows(include_hidden=True)
                    if w["kCGWindowNumber"] == window["kCGWindowNumber"]
                ),
                None,
            )
            return current and Bounds.from_window(current) == bounds

        wait_for(settled, "requested window bounds", timeout=5)

    def screens(self):
        """Convert Cocoa display rectangles to global top-left coordinates."""
        from AppKit import NSScreen

        screens = list(NSScreen.screens())
        top = screens[0].frame().size.height

        def bounds(rect):
            return Bounds(
                round(rect.origin.x),
                round(top - rect.origin.y - rect.size.height),
                round(rect.size.width),
                round(rect.size.height),
            )

        return tuple(
            Screen(
                int(s.deviceDescription()["NSScreenNumber"]),
                str(s.localizedName()),
                bounds(s.frame()),
                bounds(s.visibleFrame()),
            )
            for s in screens
        )

    def current_screen(self):
        point = self.Q.CGEventGetLocation(self.Q.CGEventCreate(None))
        screens = self.screens()
        return next(
            (
                s
                for s in screens
                if s.bounds.x <= point.x < s.bounds.x + s.bounds.width
                and s.bounds.y <= point.y < s.bounds.y + s.bounds.height
            ),
            screens[0],
        )

    def enter(self, value):
        self.apple(
            'keystroke "a" using command down\n'
            f"keystroke {json.dumps(value)}\nkey code 36"
        )
        time.sleep(0.25)

    def open_popup(self, x, y, height):
        # A first click can activate a newly shown Qt toolbar without opening it.
        for attempt in range(2):
            self.click(x, y)
            try:
                return self.popup(height, timeout=1.2)
            except RuntimeError:
                if attempt:
                    raise

    def popup(self, height=None, timeout=5):
        def match():
            return next(
                (
                    w
                    for w in self.windows()
                    if not w.get("kCGWindowName")
                    and w["kCGWindowBounds"]["Width"] < 210
                    and (height is None or w["kCGWindowBounds"]["Height"] == height)
                ),
                None,
            )

        return wait_for(match, "GaussView popup menu", timeout=timeout)

    def load_potential(self, state):
        dialog = self.window("Surfaces and Contours")
        bounds = dialog["kCGWindowBounds"]
        menu = self.open_popup(bounds["X"] + 608, bounds["Y"] + 60, 70)[
            "kCGWindowBounds"
        ]
        self.click(menu["X"] + 50, menu["Y"] + 26)  # Load Cube
        self.window("Open Cube Files")
        self.apple('keystroke "g" using {command down, shift down}')
        wait_for(
            lambda: (
                "sheet 1"
                in self.apple('get entire contents of window "Open Cube Files"')
            ),
            "Go to Folder sheet",
        )
        path = str(self.surfaces[state].potential)
        self.apple(
            'click text field 1 of sheet 1 of window "Open Cube Files"\n'
            'keystroke "a" using command down\n'
            f"keystroke {json.dumps(path)}"
        )
        time.sleep(0.4)
        self.apple("key code 36")
        time.sleep(0.6)
        self.apple(
            'click button "Open" of splitter group 1 of window "Open Cube Files"'
        )
        wait_for(lambda: self.find("Open Cube Files") is None, "cube file to open")
        wait_for(
            lambda: self.label(dialog, "Electrostatic potential"),
            "potential cube to load",
        )

    def map_surface(self, state, group):
        self.activate(wait_for(lambda: self.group_view(group), f"density view {group}"))
        self.menu("Results", "Surfaces/Contours...")
        dialog = self.window("Surfaces and Contours")
        if not dialog["kCGWindowName"].startswith(group):
            raise RuntimeError("GaussView activated an unexpected molecule group")
        self.load_potential(state)
        bounds = dialog["kCGWindowBounds"]
        x, y = bounds["X"], bounds["Y"]
        self.click(x + 420, y + 344)
        self.enter(str(self.workflow.density_isovalue))
        self.click(x + 200, y + 102)  # density cube, not the potential cube
        menu = self.open_popup(x + 608, y + 211, 85)["kCGWindowBounds"]
        self.click(menu["X"] + 70, menu["Y"] + 27)  # New Mapped Surface
        mapping = self.window("Surface Mapping")["kCGWindowBounds"]
        self.click(mapping["X"] + 19, mapping["Y"] + 68)  # existing cube
        self.click(mapping["X"] + 140, mapping["Y"] + 140)  # potential cube
        self.click(mapping["X"] + 81, mapping["Y"] + 361)  # OK
        wait_for(lambda: self.find("Surface Mapping") is None, "mapped surface")
        wait_for(
            lambda: (
                self.label(dialog, f"isoval = {self.workflow.density_isovalue:g}")
                or self.label(dialog, f"isoval {self.workflow.density_isovalue:g}")
            ),
            "density isovalue",
        )
        self.apple(
            'click button 1 of (first window whose name contains "Surfaces and Contours")'
        )
        wait_for(
            lambda: self.find("Surfaces and Contours") is None,
            "surface controls to close",
        )

    def group_view(self, group):
        # Saving a structure can rename its view or create a new group. Match the
        # model-window identity and file path, not only the original basename.
        return next(
            (
                w
                for w in self.windows()
                if w.get("kCGWindowName", "").startswith(group)
                and re.match(r"G\d+:M\d+:V\d+", w.get("kCGWindowName", ""))
                and (
                    "mapped with" in w.get("kCGWindowName", "")
                    or re.search(r"\([/~].*\)$", w.get("kCGWindowName", ""))
                    or "untitled" in w.get("kCGWindowName", "").lower()
                )
            ),
            None,
        )

    def align(self, group, alignment: Alignment):
        """Use GaussView's native molecular-axis alignment menu."""
        from .api import Session

        session = Session(self)
        model = session.model(group)
        model.activate()
        entry = next(
            (
                i
                for i in session.menus("View")
                if i.path == ("View", "Positioning Tools")
            ),
            None,
        )
        if entry is None or entry.checked is None:
            raise ActionUnavailable("Cannot read positioning toolbar state")
        visible = entry.checked
        if not visible:
            session.invoke("View", "Positioning Tools")
        try:
            for molecular, view_axis in alignment.pairs:
                quick = wait_for(
                    lambda: self.label(model.window, "Quick"), "positioning toolbar"
                )
                self.click(quick[1], quick[2])

                def parent():
                    for w in self.windows():
                        if not w.get("kCGWindowName"):
                            labels = self.read(w)
                            rows = sorted(
                                (t for t in labels if "view" in t[0].lower()),
                                key=lambda t: t[2],
                            )
                            if len(rows) == 3 and any(t[0] == "Center" for t in labels):
                                return w, rows

                popup, rows = wait_for(parent, "axis alignment menu")
                row = rows["XYZ".index(view_axis)]
                self.Q.CGEventPost(
                    self.Q.kCGHIDEventTap,
                    self.Q.CGEventCreateMouseEvent(
                        None,
                        self.Q.kCGEventMouseMoved,
                        (row[1], row[2]),
                        self.Q.kCGMouseButtonLeft,
                    ),
                )

                def submenu(popup=popup):
                    for w in self.windows():
                        if (
                            not w.get("kCGWindowName")
                            and w["kCGWindowNumber"] != popup["kCGWindowNumber"]
                        ):
                            choices = sorted(
                                (
                                    t
                                    for t in self.read(w)
                                    if t[0].lower().startswith("mol")
                                ),
                                key=lambda t: t[2],
                            )
                            if len(choices) == 6:
                                return w, choices

                child, choices = wait_for(submenu, "molecular axes")
                positive = [t for t in choices if "-" not in t[0]]
                negative = [t for t in choices if "-" in t[0]]
                options = negative if molecular.startswith("-") else positive
                if len(options) != 3:
                    raise ActionUnavailable("Cannot distinguish signed molecular axes")
                choice = options["XYZ".index(molecular.lstrip("-"))]
                self.click(choice[1], choice[2])
                wait_for(
                    lambda child=child: (
                        not any(
                            w["kCGWindowNumber"] == child["kCGWindowNumber"]
                            for w in self.windows()
                        )
                    ),
                    "alignment selection",
                )
        finally:
            if not visible:
                session.invoke("View", "Positioning Tools")
        self.menu("View", "Center")

    def orient(self, group):
        if self.workflow.alignment is not None:
            self.align(group, self.workflow.alignment)
        else:
            self.activate(wait_for(lambda: self.group_view(group), f"view {group}"))
            self.menu("View", "Center")

    def surface_format(self, group, style=SurfaceStyle.TRANSPARENT, opacity=0.5):
        if not isinstance(style, SurfaceStyle) or not 0 <= opacity <= 1:
            raise ValueError("Choose a SurfaceStyle and opacity between zero and one")
        self.activate(self.group_view(group))
        self.menu("View", "Display Format...")
        dialog = self.window("Display Format")
        surface = wait_for(lambda: self.label(dialog, "Surface"), "Surface tab")
        self.click(surface[1], surface[2])
        wait_for(lambda: self.label(dialog, "Format:"), "surface format")
        bounds = dialog["kCGWindowBounds"]
        popup = self.open_popup(bounds["X"] + 157, bounds["Y"] + 96, 47)
        choice = wait_for(lambda: self.label(popup, style.value), f"{style.value} option")
        self.click(choice[1], choice[2])
        if any(
            not w.get("kCGWindowName") and w["kCGWindowBounds"]["Height"] == 47
            for w in self.windows()
        ):
            self.click(choice[1], choice[2])
        if style is SurfaceStyle.TRANSPARENT:
            wait_for(lambda: self.label(dialog, "Transparent Options"), "transparent surface")
            left, right = bounds["X"] + 153, bounds["X"] + 373
            target, slider_y = left + (right - left) * opacity, bounds["Y"] + 154
            # Qt's native macOS and common slider styles use the middle button
            # for absolute positioning, without relying on keyboard focus.
            self.click(target, slider_y, button="middle")
        self.click(bounds["X"] + 162, bounds["Y"] + 446)  # OK
        wait_for(lambda: self.find("Display Format") is None, "display settings to apply")
        if self.color_range is not None:
            self.apply_scale(group)

    def transparent(self, group):
        self.surface_format(group)

    def scale_fields(self, view):
        """Locate the two numeric ESP legend fields, excluding frame controls."""
        bounds = view["kCGWindowBounds"]
        fields = []
        for label in self.read(view):
            text = label[0].replace("O", "0").replace("o", "0").replace("−", "-").rstrip("|")
            if (
                bounds["Y"] + 24 < label[2] < bounds["Y"] + 85
                and ("." in text or "e" in text.lower())
                and re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
            ):
                fields.append((float(text), label[1], label[2]))
        if len(fields) != 2:
            raise ActionUnavailable("Cannot identify both ESP legend fields")
        return sorted(fields, key=lambda field: field[1])

    def apply_scale(self, group):
        view = self.group_view(group)
        self.activate(view)
        bounds = view["kCGWindowBounds"]
        self.click(bounds["X"] + bounds["Width"] - 20, bounds["Y"] + bounds["Height"] - 50)
        # Inspect both fields before typing; toolbar positions vary with frame controls.
        self.scale_fields(self.group_view(group))
        for index, value in enumerate(self.color_range):
            view = self.group_view(group)
            field = self.scale_fields(view)[index]
            self.click(field[1], field[2])
            self.enter(value)
            bounds = view["kCGWindowBounds"]
            self.click(bounds["X"] + bounds["Width"] - 20, bounds["Y"] + bounds["Height"] - 50)
        self.verify_scale(group)

    def verify_scale(self, group):
        view = self.group_view(group)
        if view is None:
            raise RuntimeError(f"Missing mapped view for {group}")
        for field, value in zip(self.scale_fields(view), self.color_range, strict=True):
            if abs(field[0] - float(value)) > 0.0005:
                raise RuntimeError(f"Failed to verify ESP bound {value} for {group}: {field[0]}")

    def arrange(self, groups):
        """Use the user's staggered arrangement, with small bounded variations."""
        screen = self.current_screen()
        area = screen.work_area
        width, height = screen.bounds.width, screen.bounds.height
        reference_width, reference_height = self.workflow.reference_screen
        sx, sy = width / reference_width, height / reference_height
        top = area.y
        bottom = area.y + area.height
        jitter = random.SystemRandom()
        surface_groups = groups[-len(self.workflow.surfaces) :] if self.workflow.surfaces else []
        roles = dict(zip((s.name for s in self.workflow.surfaces), surface_groups, strict=True))
        roles["source"] = groups[0]
        self.front(force=True)
        for role, position, size in self.workflow.layout:
            result = (
                role
                if isinstance(role, Result)
                else (next(iter(self.workflow.results), None) if role == "plot" else None)
            )
            window = (
                wait_for(
                    lambda result=result: self.result_window(groups[0], result),
                    f"{result.name} window",
                )
                if result is not None
                else self.group_view(roles[role])
            )
            px, py = position
            w, h = size
            size_noise = self.workflow.size_jitter
            pos_noise = self.workflow.position_jitter
            w = min(
                round(area.width),
                max(340, round(w * sx + jitter.uniform(-size_noise, size_noise))),
            )
            h = min(
                round(bottom - top),
                max(300, round(h * sy + jitter.uniform(-size_noise, size_noise))),
            )
            px = round(
                max(
                    area.x,
                    min(
                        area.x + area.width - w,
                        area.x + px * sx + jitter.uniform(-pos_noise, pos_noise),
                    ),
                )
            )
            py = round(
                max(
                    top,
                    min(
                        bottom - h,
                        screen.bounds.y + py * sy + jitter.uniform(-pos_noise, pos_noise),
                    ),
                )
            )
            target = window_reference(window["kCGWindowName"])
            self.apple(
                f"set size of {target} to {{{w}, {h}}}\nset position of {target} to {{{px}, {py}}}"
            )
        self.front(force=True)

    def result_window(self, group, result):
        for window in self.windows():
            title = window.get("kCGWindowName", "")
            if not title.startswith(group):
                continue
            detail = title.partition(" - ")[2]
            if re.search(r"\([/~].*\)$", detail):
                continue
            if any(
                detail.casefold() == name.casefold()
                or detail.casefold().startswith(name.casefold() + " ")
                for name in result.titles
            ):
                return window
        return None

    def open_result(self, group, result):
        self.activate(self.group_view(group))
        enabled = self.apple(
            "get enabled of menu item "
            + json.dumps(result.value)
            + ' of menu "Results" of menu bar item "Results" of menu bar 1'
        ).strip()
        if enabled != "true":
            from .api import ActionUnavailable

            raise ActionUnavailable(
                f"{result.name} is unavailable for this molecule group"
            )
        self.menu("Results", result.value)
        return wait_for(
            lambda: self.result_window(group, result), f"{result.name} display"
        )
