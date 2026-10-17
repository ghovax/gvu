# Menu reference

The installed GaussView 6.0.16 menu bar is addressed through `Session.menus()`, `action(*path)` and `invoke(*path)`. Paths include every submenu component. `ModelView.menus()` and `invoke()` first select that molecule group, so availability belongs to the intended model.

`enabled` includes disabled ancestors, while `native_enabled` records the item's own flag. `checked` is true or false for recognized toggles and radio choices, and `None` for ordinary commands without a native mark. `kind` is `action`, `submenu`, `toggle` or `radio`. `shortcut` preserves the native character, modifier mask, glyph and virtual key where exposed. `mark` preserves the native selection mark. `set_menu(*path, checked=True)` verifies the resulting state; radio choices are changed by selecting another item.

Selection, loaded data, current dialog and installed Gaussian/Ampac capabilities determine which commands are enabled. Recent files, services, molecule groups and window names are read dynamically. The Apple menu is a macOS menu outside this application's default catalog; it can be inspected explicitly with `menus("Apple")`.

A successful menu dispatch does not establish that every control in the resulting dialog is automated. `Dialog.controls()` reports native controls, values, writable attributes and supported actions; `perform()` and `set_value()` reject unavailable native operations. `Dialog.labels()` reads rendered text separately. An OCR label does not prove a control's enabled state, type or value. GaussView's custom Qt panels often expose only an `AXUnknown` region rather than their internal widgets.

The menu names below were checked against the running application and its bundled `help/gvmenu.htm`. Dynamic entries are represented by their parent, and remain available through the live API.

## GaussView

| Path within menu | `kind` |
| --- | --- |
| About GaussView | `action` |
| Settings… | `action` |
| Services | `submenu` |
| Hide GaussView | `action` |
| Hide Others | `action` |
| Show All | `action` |
| Quit GaussView | `action` |

## File

| Path within menu | `kind` |
| --- | --- |
| New Molecule Group | `action` |
| Add to Molecule Group | `action` |
| Open... | `action` |
| Recent Files | `submenu` |
| Related Files | `submenu` |
| Refresh | `action` |
| Save... | `action` |
| Save Temp Files... | `action` |
| Convert Files... | `action` |
| Directory... | `action` |
| Print... | `action` |
| Save Image... | `action` |
| Save Movie | `submenu` |
| Save Movie / Save Movie File... | `action` |
| Save Movie / Save Movie Frame Files... | `action` |
| Save Movie / Save Both... | `action` |

## Edit

| Path within menu | `kind` |
| --- | --- |
| Undo | `action` |
| Redo | `action` |
| Cut | `action` |
| Copy | `action` |
| Paste | `submenu` |
| Paste / Add to Molecule Group | `action` |
| Paste / Replace Molecule | `action` |
| Paste / Append Molecule | `action` |
| Delete | `action` |
| Image Capture | `action` |
| Standardize Z-Matrix | `action` |
| Symmetrize | `action` |
| Reorient | `action` |
| Rebond | `action` |
| Remove Weak Bonds | `action` |
| Clean | `action` |
| Mirror Invert | `action` |

## Tools

| Path within menu | `kind` |
| --- | --- |
| Atom List... | `action` |
| Redundant Coordinates... | `action` |
| Connection... | `action` |
| Select Layer... | `action` |
| Atom Groups... | `action` |
| Atom Selection... | `action` |
| PDB Residues... | `action` |
| PDB Secondary Structure... | `action` |
| Point Group... | `action` |
| PBC... | `action` |
| MOs... | `action` |
| Custom Bonding Parameters... | `action` |

## Builder

| Path within menu | `kind` |
| --- | --- |
| Element Fragment... | `action` |
| Ring Fragment... | `action` |
| R-Group Fragment... | `action` |
| Biological Fragment... | `action` |
| Custom Fragment... | `action` |
| Fragment | `submenu` |
| Place Fragment at Centroid of Selected Atoms | `action` |
| Modify Bond... | `action` |
| Modify Angle... | `action` |
| Modify Dihedral... | `action` |
| Inquire... | `radio` |
| Add Valence | `radio` |
| Delete Atom | `radio` |
| Invert Atom | `radio` |
| Select Atoms by Clicking | `radio` |
| Select Atoms by Rubberband | `radio` |
| Select Atoms by Brush | `radio` |
| Deselect All Atoms | `action` |
| Select All Atoms | `action` |

## View

| Path within menu | `kind` |
| --- | --- |
| Show Tab Bar | `action` |
| Show All Tabs | `action` |
| Add View | `action` |
| Center | `action` |
| Builder | `toggle` |
| Hydrogens | `toggle` |
| Dummies | `toggle` |
| Labels | `toggle` |
| Symbols | `toggle` |
| Bonds | `toggle` |
| Synchronize | `toggle` |
| Cartesian Axes | `toggle` |
| Stereochemistry | `toggle` |
| Positioning Tools | `toggle` |
| Display Format... | `action` |
| Enter Full Screen | `action` |

## Calculate

| Path within menu | `kind` |
| --- | --- |
| Gaussian Calculation Setup... | `action` |
| Gaussian Quick Launch | `submenu` |
| Gaussian Quick Launch / Temp File | `action` |
| Gaussian Quick Launch / Save File... | `action` |
| Gaussian Quick Launch / Save and Edit File... | `action` |
| Gaussian Quick Launch / Current Input File... | `action` |
| Gaussian Calculation Scheme | `submenu` |
| Gaussian Calculation Scheme / (Unnamed Scheme) | `action` |
| Gaussian Calculation Scheme / (Default Scheme) | `action` |
| Gaussian Calculation Scheme / (More Schemes...) | `action` |
| GMMX Conformer Dialog... | `action` |
| Ampac Calculation Setup... | `action` |
| Ampac Quick Launch | `submenu` |
| Ampac Quick Launch / Temp File | `action` |
| Ampac Quick Launch / Save File... | `action` |
| Ampac Quick Launch / Save and Edit File... | `action` |
| Ampac Quick Launch / Current Input File... | `action` |
| Ampac Calculation Scheme | `submenu` |
| Ampac Calculation Scheme / (Unnamed Scheme) | `action` |
| Ampac Calculation Scheme / (Default Scheme) | `action` |
| Ampac Calculation Scheme / Codessa/AM1 | `action` |
| Ampac Calculation Scheme / Codessa/AM1-FS2 | `action` |
| Ampac Calculation Scheme / Codessa/PM6 | `action` |
| Ampac Calculation Scheme / (More Schemes...) | `action` |
| Current Jobs... | `action` |
| SC Job Manager... | `action` |

## Results

| Path within menu | `kind` |
| --- | --- |
| Summary... | `action` |
| Charge Distribution... | `action` |
| PCM Solvation Cavity... | `action` |
| Atom Properties... | `action` |
| Bond Properties... | `action` |
| Surfaces/Contours... | `action` |
| Vibrations... | `action` |
| NMR... | `action` |
| UV-Vis... | `action` |
| ORD... | `action` |
| Vibronic... | `action` |
| Molecule Group Table... | `action` |
| Scan... | `action` |
| IRC/Path... | `action` |
| Trajectory... | `action` |
| Optimization... | `action` |
| Energy Plot... | `action` |
| Ampac | `submenu` |
| Ampac / Reaction Path... | `action` |
| Ampac / Reaction Grid... | `action` |
| Ampac / Annealing... | `action` |
| Ampac / Chain... | `action` |
| Ampac / IRC/Path... | `action` |
| View / Edit File | `action` |
| Stream Output File | `action` |

## Windows

| Path within menu | `kind` |
| --- | --- |
| Show Molecule Groups | `submenu` |
| Minimize All | `action` |
| Restore | `action` |
| Restore All | `action` |
| Close | `action` |
| Close All | `action` |
| Previous | `action` |
| Next | `action` |
| Cascade | `action` |
| Tile | `action` |

## Help

| Path within menu | `kind` |
| --- | --- |
| GaussView Help... | `action` |
| Menus and Icons | `action` |
| How Do I...? | `action` |
| Tutorials | `action` |
| Gaussian Help... | `action` |
| Ampac Help... | `action` |
| GaussView Tips... | `action` |

## Preferences

`Session.settings()` discovers the application settings command and opens GaussView Preferences. `pages()` indexes all 17 categories below. `page(name)` requires a visible content change and reports `ActionUnavailable` if navigation cannot be verified. `cancel()` closes without applying; `apply()` selects Ok and verifies closure.

The current live check verified opening, category discovery and native closure. Page navigation through the rendered list failed its content-change check; individual settings fields and applying changed values are not verified. Treat them as incomplete automation until tested, rather than inferring full support from the menu entry.

Ampac Setup, Building, Charge Distribution, Clean Controls, Custom Bonding Parameters, Colors, Display Format, File/Directory, Font, Gaussian Setup, Icons, Image, Job Setup, Movie, Animation, Print, Vibrations, Window Behavior.
