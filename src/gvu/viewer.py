"""Shared launch, validation and reuse for run-specific GaussView workflows."""

import re
import subprocess
import sys
import time
from pathlib import Path

from .errors import ActionUnavailable
from .files import input_paths, job_count
from .logging import LOG, configure_logging
from .models import Workflow
from .surfaces import color_range


def validate(workflow):
    missing = [str(p) for p in workflow.files if not p.is_file()]
    if missing:
        raise ValueError("Missing existing calculation data: " + ", ".join(missing))
    if not workflow.source.is_absolute() or any(not p.is_absolute() for p in workflow.files):
        raise ValueError("Workflow data paths must be absolute")
    names = [s.name for s in workflow.surfaces]
    if len(names) != len(set(names)):
        raise ValueError("Surface names must be unique")
    if workflow.surfaces and not 0 < workflow.density_isovalue < float("inf"):
        raise ValueError("Density isovalue must be positive and finite")
    if any(value <= 0 for value in workflow.reference_screen):
        raise ValueError("Reference screen dimensions must be positive")
    roles = {"source", *names, *workflow.results}
    if workflow.results:
        roles.add("plot")
    for role, position, size in workflow.layout:
        if role not in roles or len(position) != 2 or len(size) != 2 or any(v <= 0 for v in size):
            raise ValueError(f"Invalid layout entry: {role}")
    input_paths(workflow.files)
    text = (
        workflow.source.read_text(errors="replace")
        if workflow.source.suffix.lower() in {".log", ".out"}
        else None
    )
    if not 0 <= workflow.opacity <= 1:
        raise ValueError("Opacity must be between zero and one")
    for result in workflow.results:
        if (
            text is not None
            and result.markers
            and not any(marker in text for marker in result.markers)
        ):
            raise ValueError(f"{result.name} data not found in {workflow.source}")


def application_pids(executable):
    result = subprocess.run(
        ["ps", "-axo", "pid=,comm="],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    return [
        int(parts[0])
        for line in result.stdout.splitlines()
        if len(parts := line.strip().split(None, 1)) == 2 and parts[1] == str(executable)
    ]


def reusable_groups(viewer):
    """Match the source path and the ordered surface block opened with it."""
    workflow = viewer.workflow
    windows = viewer.windows()
    mapped_groups = {
        w["kCGWindowName"].split(":")[0] + ":"
        for w in windows
        if "mapped with" in w.get("kCGWindowName", "")
        and f"isoval = {workflow.density_isovalue:g}" in w.get("kCGWindowName", "")
    }
    sources = {
        int(match.group(1))
        for window in windows
        if str(workflow.source) in (title := window.get("kCGWindowName", ""))
        and (match := re.match(r"G(\d+):M\d+:V\d+", title))
    }
    for start in sorted(sources):
        end = start
        while end + 1 in sources:
            end += 1
        groups = [f"G{number}:" for number in range(start, end + 1)]
        surfaces = [f"G{end + offset}:" for offset in range(1, len(workflow.surfaces) + 1)]
        if len(groups) >= job_count(workflow.source) and all(group in mapped_groups for group in surfaces):
            return [*groups, *surfaces]
    return None


def launch(workflow, app, reuse_views=True):
    import Quartz as Q
    from ApplicationServices import (
        AXIsProcessTrusted,
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
    )

    from .macos import MacViewer, wait_for

    if not AXIsProcessTrusted():
        raise RuntimeError(
            "Enable Accessibility for the invoking terminal/Codex in macOS System Settings"
        )
    if not Q.CGPreflightScreenCaptureAccess():
        raise RuntimeError(
            "Enable Screen Recording for the invoking terminal/Codex in macOS System Settings"
        )
    executable = app / "Contents/MacOS/gview"
    bounds = (
        color_range(workflow.surfaces, workflow.density_isovalue) if workflow.surfaces else None
    )
    pids = application_pids(executable)
    if len(pids) > 1:
        raise RuntimeError("Close duplicate GaussView app instances before running this launcher")
    if reuse_views and pids:
        process_started = subprocess.run(
            ["ps", "-p", str(pids[0]), "-o", "lstart="],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        process_start = time.mktime(time.strptime(process_started, "%a %b %d %H:%M:%S %Y"))
        if all(p.stat().st_mtime < process_start for p in workflow.files):
            viewer = MacViewer(pids[0], workflow, app, bounds)
            groups = reusable_groups(viewer)
            source_groups = (
                (groups[: -len(workflow.surfaces)] if workflow.surfaces else groups)
                if groups
                else []
            )
            if source_groups and all(
                any(viewer.result_window(group, result) for group in source_groups)
                for result in workflow.results
            ):
                viewer.group_ids.update(groups)
                try:
                    surface_groups = groups[-len(workflow.surfaces) :] if workflow.surfaces else []
                    for group in surface_groups:
                        viewer.verify_scale(group)
                except RuntimeError as error:
                    LOG.debug(
                        "existing_views_incomplete",
                        extra={"metadata": {"reason": str(error)}},
                    )
                else:
                    for result in workflow.results:
                        for group in source_groups:
                            if not viewer.result_window(group, result):
                                try:
                                    viewer.open_result(group, result)
                                except ActionUnavailable:
                                    continue
                    viewer.front(force=True)
                    return viewer, groups, True

    # Start the normal app before configuring file-reading options.
    if not pids:
        subprocess.run(["open", "-a", str(app)], check=True, timeout=15)
    pid = wait_for(lambda: next(iter(application_pids(executable)), None), "GaussView process")
    viewer = MacViewer(pid, workflow, app, bounds)
    application = AXUIElementCreateApplication(pid)

    def menu_ready():
        for window in viewer.windows():
            if not window.get("kCGWindowName") and viewer.label(
                window, "Gaussian is not installed"
            ):
                viewer.apple("set frontmost to true\nkey code 36")
        error, menu = AXUIElementCopyAttributeValue(application, "AXMenuBar", None)
        if error or menu is None:
            return False
        error, children = AXUIElementCopyAttributeValue(menu, "AXChildren", None)
        return not error and any(
            AXUIElementCopyAttributeValue(child, "AXTitle", None) == (0, "File")
            for child in children or ()
        )

    wait_for(menu_ready, "GaussView menu bar", timeout=45)
    previous_windows = {w["kCGWindowNumber"] for w in viewer.windows()}
    density_files = [s.density for s in workflow.surfaces]
    # The file dialog applies intermediate-geometry options to this exact load.
    viewer.open_documents(
        [workflow.source, *density_files],
        read_intermediates=any(r.intermediate_geometries for r in workflow.results),
    )

    def opened(path):
        return next(
            (
                w
                for w in viewer.windows()
                if w["kCGWindowNumber"] not in previous_windows
                and str(path) in w.get("kCGWindowName", "")
            ),
            None,
        )

    LOG.info(
        "viewer_opening",
        extra={
            "metadata": {
                "viewer_pid": pid,
                "app": app,
                "source": workflow.source,
                "results": [r.name for r in workflow.results],
                "surfaces": [s.name for s in workflow.surfaces],
            }
        },
    )

    expected_source_jobs = job_count(workflow.source)

    def ready():
        if viewer.select_file_jobs():
            return False
        for window in viewer.windows():
            if not window.get("kCGWindowName") and viewer.label(
                window, "Gaussian is not installed"
            ):
                viewer.apple("set frontmost to true\nkey code 36")
        for window in viewer.windows():
            if not window.get("kCGWindowName"):
                labels = [t[0] for t in viewer.read(window)]
                if any(
                    "Failure reading" in t or "Error reading" in t or "Unknown file type" in t
                    for t in labels
                ):
                    raise RuntimeError("GaussView rejected the input: " + "; ".join(labels))
        source_groups = {
            w["kCGWindowName"].split(":")[0]
            for w in viewer.windows()
            if w["kCGWindowNumber"] not in previous_windows
            and str(workflow.source) in w.get("kCGWindowName", "")
        }
        return len(source_groups) >= expected_source_jobs and all(
            opened(p) for p in [workflow.source, *density_files]
        )

    wait_for(ready, "source and density files", timeout=45)
    source_groups = list(
        dict.fromkeys(
            w["kCGWindowName"].split(":")[0] + ":"
            for w in viewer.windows()
            if w["kCGWindowNumber"] not in previous_windows
            and str(workflow.source) in w.get("kCGWindowName", "")
        )
    )
    source_groups.sort(key=lambda group: int(group[1:-1]))
    surface_groups = [opened(p)["kCGWindowName"].split(":")[0] + ":" for p in density_files]
    groups = [*source_groups, *surface_groups]
    viewer.group_ids.update(groups)
    for surface, group in zip(workflow.surfaces, surface_groups, strict=True):
        LOG.debug(
            "state_configuring",
            extra={"metadata": {"state": surface.name, "group": group}},
        )
        viewer.map_surface(surface.name, group)
        viewer.orient(group)
        viewer.surface_format(group, workflow.surface_style, workflow.opacity)
        LOG.debug(
            "surface_styled",
            extra={"metadata": {"state": surface.name, "group": group}},
        )
    for group in source_groups:
        viewer.orient(group)
    for result in workflow.results:
        displays = []
        for group in source_groups:
            try:
                window = viewer.open_result(group, result)
            except ActionUnavailable:
                continue
            displays.append(window)
            LOG.debug(
                "result_opened",
                extra={
                    "metadata": {
                        "result": result.name,
                        "window": window["kCGWindowName"],
                        "group": group,
                    }
                },
            )
        if not displays:
            raise ActionUnavailable(f"{result.name} is unavailable in all loaded jobs")
    if workflow.layout:
        viewer.arrange(groups)
    return viewer, groups, False


def open_workflow(workflow: Workflow, *, application_path=None, reuse_views=True, log_level="INFO"):
    """Validate and open a workflow using explicit Python options."""
    configure_logging(log_level)
    started = time.monotonic()
    validate(workflow)
    if sys.platform != "darwin":
        raise RuntimeError("GaussView UI automation requires macOS")
    app = (
        (
            Path(application_path)
            if application_path is not None
            else Path.home() / "Applications/GaussView6/gview.app"
        )
        .expanduser()
        .resolve()
    )
    if not (app / "Contents/MacOS/gview").is_file():
        raise ValueError(f"GaussView executable not found in {app}")
    viewer, groups, reused = launch(workflow, app, reuse_views=reuse_views)
    LOG.info(
        "viewer_ready",
        extra={
            "metadata": {
                "source": workflow.source,
                "viewer_pid": viewer.pid,
                "reused": reused,
                "groups": groups,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        },
    )
