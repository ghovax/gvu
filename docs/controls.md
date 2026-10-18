# Menus and controls

## Discover an action

```python
from gvu import Session

session = Session.attach()
items = session.menus()
roots = [item.path[0] for item in items if len(item.path) == 1]
results = session.model("G1:").menus("Results")
```

`menus()` returns a flat catalog whose path tuples encode the hierarchy:

- The default roots are GaussView, File, Edit, Tools, Builder, View, Calculate, Results, Windows and Help.
- Services and nested menus are included.
- `menus("Results")` restricts discovery to one root.
- `menus("Apple")` explicitly accesses the operating-system menu.

Availability belongs to the active molecule/dialog context. Use `model.menus(...)` or `model.invoke(...)` to select that model first. Recent files, available groups, window titles and some command states are dynamic; inspect again after the context changes.

## Interpret menu state

| Field | Meaning |
| --- | --- |
| `path` | Exact tuple of menu and submenu names |
| `enabled` | Whether the item and its ancestors permit invocation |
| `native_enabled` | The item's own native enabled flag |
| `checked` | `True` or `False` for recognized choices; `None` for an unmarked ordinary command |
| `kind` | `action`, `submenu`, `toggle` or `radio` |
| `submenu` | Whether the entry contains child commands |
| `shortcut` | Native `Shortcut` metadata, when exposed |
| `mark` | Native selection-mark character, when exposed |

A `Shortcut` preserves the native character, modifier bit mask, glyph and virtual-key code. Its fields can be absent; the API does not invent a key binding. The [menu reference](menus.md) lists command paths grouped by root.

## Invoke and set state

```python
item = session.action("Results", "Vibrations...")
if item.enabled:
    session.invoke(*item.path)

session.set_menu("View", "Labels", checked=True)
```

- `action` resolves one exact current entry.
- `invoke` requires an enabled leaf. Unavailable, ambiguous and submenu-only paths raise `ActionUnavailable`.
- `set_menu` reads the existing state, changes it only when necessary and verifies the result.
- To change a radio choice, select another item. Clearing the selected choice directly is unsupported.

Opening a native command may modify a structure, save files or launch a calculation. Menu enumeration alone does not execute those leaf commands. No example here submits a calculation.

## Dialogs and native controls

After opening a command, select its dialog with `session.dialog(title)`. `controls()` returns native `Control` descriptors, including their tree path, originating dialog, role, label, enabled state, value, supported actions and writable attributes.

```python
dialog = session.dialog("Dialog title from the current application")
controls = dialog.controls()
buttons = [control for control in controls
           if control.role == "AXButton" and control.enabled is not False]
```

Pass a discovered descriptor to `dialog.perform(control, "AXPress")`, or to `dialog.set_value(control, value)` when `AXValue` is writable. The library resolves the descriptor again and rejects changed or disabled targets and unsupported operations. An enabled state of `None` means the native interface does not expose that flag.

Many GaussView Qt widgets appear only as an `AXUnknown` region. Use the rendered-interface helpers where native controls are unavailable:

- `dialog.labels()` reads text through OCR.
- `click(label)` clicks a label.
- `check(label, enabled=True)` sets a checkbox.
- `fill(x, y, value)` enters a value at dialog-relative coordinates measured in display points.
- `choose(label)` selects a choice.
- `key(name)` sends a key.

An OCR label does not establish a widget's type, enabled state or current value. Duplicate labels are rejected rather than resolved arbitrarily.

## Automatic interaction

- Menu discovery cancels the open native menu once and waits for tracking to end.
- Menu commands check availability before invocation; disabled actions raise `ActionUnavailable`.
- Animation settings close with a click outside the options panel.
- Opacity uses [Qt's absolute slider positioning](https://github.com/qt/qt/blob/4.8/src/gui/widgets/qslider.cpp) with the middle mouse button. It does not send Home or End keys.
- These operations leave macOS volume and alert-sound preferences unchanged. Explicit calls to `dialog.key(...)` still send the requested key to the application.

## Settings

```python
preferences = session.settings()
pages = preferences.pages()
preferences.cancel()
```

- `settings()` discovers the application settings command.
- `pages()` lists 17 preference categories.
- `page(name)` requires a content change after selection and raises `ActionUnavailable` when that change cannot be verified. Selecting an already displayed page can also fail this check.
- `apply()` selects Ok and verifies closure.
- `cancel()` closes the dialog without applying changes.

Opening, category discovery, native-control inspection and closure were tested. Rendered page navigation failed verification. Individual settings fields and applying changed values remain unverified. Read the [coverage record](coverage.md) before automating preference changes.

## Right-click menus

Model right-click menus share many menu-bar commands; scripts can use the indexed paths through `model.invoke(...)`. This does not prove that the two menus are identical. Plot context menus use `Plot.data`, `image` and `properties` helpers. Arbitrary context-menu trees are not part of the menu-bar catalog.
