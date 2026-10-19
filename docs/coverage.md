# Coverage and troubleshooting

## Verified behavior

The tested installation is macOS GaussView 6.0.16. Unit tests cover menu hierarchy and state, ambiguity, ownership, input validation, display placement, snapshot restoration, structured logging and numerical ESP-grid analysis. Existing research workflows passed their data preflight; that validates declared data without exercising every native control.

Live checks covered:

- Grouped geometry loading and owned-group cleanup.
- Both sections of a linked-job scan log and their separate scan plots.
- Native axis alignment, fitting/centering and camera rotation.
- Selected-window placement and frame selection/playback.
- Animation repeat, direction and delay settings read back after closing and reopening the options panel.
- Absolute opacity positioning at 0.2 and 0.8, checked from the reopened slider.
- Mapped ESP surfaces and structure/image export.
- Shared ESP legends located by their numeric fields, including fields with a visible editing caret.
- Vibration selection, scrolling and playback.
- Native optimization-plot data export.
- All ten application menu roots, Help-name normalization and disabled-parent state.
- Settings discovery/opening and a labels toggle restored to its original state.
- Preference category discovery, native-control inspection and closure.
- Single-action native menu cancellation, including a menu already open before discovery.
- Model and result-window activation, including plots absent from the Windows menu.
- Repeated activation and same-group plot raising without Windows-menu dispatch; cross-group selection checked against the native group menu.
- Reuse of existing input, vibration and IRC views without duplicate groups.
- Restoration of a closed vibration panel without reloading its source molecule.

## Incomplete or unverified operations

| Area | Current boundary |
| --- | --- |
| Preferences | Categories are indexed; rendered page navigation failed content-change verification. Individual fields and applying changed values remain unverified. |
| Specialist result dialogs | Entries are indexed and availability is checked; every internal control has not been tested. |
| Quiet interaction | Live checks cover native menu cancellation, animation settings and absolute opacity positioning. Tests prohibit extra cancellation and slider endpoint keys and bound combo navigation to recognized choices. Absence of audible alerts has not been independently recorded. |
| Movie export | Native helpers exist; end-to-end export remains unverified in this revision. |
| Context menus | Dedicated plot helpers exist; the menu-bar catalog does not enumerate every arbitrary right-click tree. |
| Other installations | Other GaussView versions, themes, display scales, languages and operating systems require validation. |

## Common failures

| Symptom | Check |
| --- | --- |
| Missing-file or unsupported-format error | Required data exists locally and uses a supported extension; XYZ is unsupported. |
| `ActionUnavailable` for a result | Select the intended group, inspect its Results menu and check the source calculation contains the property. |
| Only one geometry loads | Load intermediate geometries explicitly or request the appropriate workflow result. |
| Accessibility or screenshot error | Enable Accessibility and Screen Recording for the actual invoking terminal/application. |
| Attach fails | Exactly one copy of the selected GaussView installation must be running. |
| Ambiguous label or changed native control | Inspect the current dialog again; do not reuse a descriptor after changing its layout. |
| Preference navigation fails | The requested page's content was not verified. Inspect it manually rather than treating the old page as the new one. |
| Export refuses a path | Choose a non-existing file in an existing parent directory. |
| Open views retain prior styling | Reuse preserves manual changes; use `workflow.view(reuse_views=False)` to request reconstruction. |

## Reuse and scientific interpretation

Reuse matches the complete source path and one complete molecule-group block. It restores missing result panels and corrects a mismatched shared ESP legend in place.

- Reuse preserves data already loaded in GaussView, including manual view settings.
- After changing source or cube files, use `workflow.view(reuse_views=False)` to load the new data.
- Mapped group order and the displayed legend do not independently prove cube identity. Check density/potential pairing, electronic state, atom order, units and convergence against calculation data.

Bonds displayed by GaussView can be inferred from geometry or read from connectivity. A drawn multiple bond does not establish a calculated bond order. IRC playback is a sequence of computed structures, and its speed is not a physical reaction time.

## Logs

GVU emits `TIMESTAMP [LEVEL] message key=value ...` records to stderr. The UTC timestamp precedes the level; logger, process ID and relevant metadata follow the message. Exceptions include ordinary Python tracebacks. Default output records essential opening, scale and failure events; `workflow.view(log_level="DEBUG")` adds diagnostics. It does not automatically create log or metadata sidecar files. Initial uv installation output is separate from the library's event stream.
