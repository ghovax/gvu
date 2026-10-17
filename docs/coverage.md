# Coverage and troubleshooting

## Verified behavior

The tested installation is macOS GaussView 6.0.16. Unit tests cover menu hierarchy and state, ambiguity, ownership, input validation, display placement, snapshot restoration, structured logging and numerical ESP-grid analysis. Existing research workflows passed their data preflight; that validates declared data without exercising every native control.

Live checks covered:

- Grouped geometry loading and owned-group cleanup.
- Native axis alignment, fitting/centering and camera rotation.
- Selected-window placement and frame selection/playback.
- Mapped ESP surfaces and structure/image export.
- Vibration selection, scrolling and playback.
- Native optimization-plot data export.
- All ten application menu roots, Help-name normalization and disabled-parent state.
- Settings discovery/opening and a labels toggle restored to its original state.
- Preference category discovery, native-control inspection and closure.

## Incomplete or unverified operations

| Area | Current boundary |
| --- | --- |
| Preferences | Categories are indexed; rendered page navigation failed content-change verification. Individual fields and applying changed values remain unverified. |
| Specialist result dialogs | Entries are indexed and availability is checked; every internal control has not been tested. |
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

Reuse checks source paths, file age, mapped group order and the displayed legend. These checks do not independently prove cube identity. Density/potential pairing, electronic state, atom order, units and convergence must be checked against calculation data.

Bonds displayed by GaussView can be inferred from geometry or read from connectivity. A drawn multiple bond does not establish a calculated bond order. IRC playback is a sequence of computed structures, and its speed is not a physical reaction time.

## Logs

GVU emits JSON Lines to stderr with UTC timestamps, severity, process ID, event and relevant metadata. Default output records essential opening, scale and failure events; `workflow.view(log_level="DEBUG")` adds diagnostics. It does not automatically create log or metadata sidecar files. Initial uv installation output is separate from the library's event stream.
