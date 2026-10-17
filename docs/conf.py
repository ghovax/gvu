"""Sphinx configuration shared by local and Read the Docs builds."""
from importlib.metadata import version as package_version

project = "GVU"
author = "Giovanni Gravili and contributors"
release = package_version("gvu")
version = release
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.autosummary", "sphinx.ext.viewcode"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
myst_enable_extensions = ["colon_fence", "dollarmath"]
autodoc_member_order = "bysource"
autodoc_typehints = "signature"
html_theme = "sphinx_rtd_theme"
html_title = "GVU documentation"
html_theme_options = {"navigation_depth": 3, "collapse_navigation": False}
html_show_sourcelink = True
