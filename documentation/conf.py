from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

project = "Proxima"
author = "Proxima contributors"
copyright = "2026, Proxima contributors"

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx.ext.autodoc",
    "sphinx.ext.mathjax",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"

html_theme = "furo"
html_title = "Proxima Documentation"
html_theme_options = {
    "navigation_with_keys": True,
    "top_of_page_button": "edit",
    "light_css_variables": {
        "color-brand-primary": "#15879a",
        "color-brand-content": "#15879a",
    },
    "dark_css_variables": {
        "color-brand-primary": "#4fd8ec",
        "color-brand-content": "#8ff2ff",
        "color-background-primary": "#05090b",
        "color-background-secondary": "#0a1318",
        "color-sidebar-background": "#071015",
        "color-sidebar-background-border": "#1c3a42",
    },
}

html_static_path = ["_static"]
html_css_files = ["mermaid-zoom.css"]
html_js_files = ["mermaid-zoom.js"]

myst_heading_anchors = 3
myst_enable_extensions = [
    "amsmath",
    "dollarmath",
]
myst_fence_as_directive = [
    "math",
]
