# GVU documentation

GVU controls macOS GaussView 6 through a shared Python interface. Run-specific viewer scripts declare the existing calculation files and desired displays; the library handles loading, native menus, camera alignment, animations, surfaces and window placement.

## Where to start

| Your task | Read |
| --- | --- |
| Open a run or write its viewer | [Getting started](getting-started.md) |
| Compare inputs, align models or arrange views | [Viewing workflows](workflows.md) |
| Find an action, inspect its state or use a dialog | [Menus and controls](controls.md) |
| Find a particular GaussView menu command | [Menu reference](menus.md) |
| Look up Python methods, parameters and data types | [API reference](api.rst) |
| Check what has been verified and diagnose failures | [Coverage and troubleshooting](coverage.md) |
| Build or maintain these docs | [Development](development.md) |

Navigate the documentation using:

- The sidebar for pages and their sections.
- The search box for a command or Python name.
- Breadcrumbs to return to the documentation root.
- Previous/next links to follow the guide in order.

The API reference is generated from the installed package so signatures follow the implementation.

```{toctree}
:maxdepth: 2
:caption: Guides

getting-started
workflows
controls
```

```{toctree}
:maxdepth: 2
:caption: Reference

menus
api
coverage
```

```{toctree}
:maxdepth: 2
:caption: Development

development
```
