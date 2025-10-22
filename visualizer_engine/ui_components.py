"""
ui_components.py

PROXIMA LUNAR SIMULATION - UI LAYOUT COMPONENTS

PURPOSE:
========
HTML component builders and layout definitions for the Proxima dashboard.
Separates presentation logic from business logic.
"""

from __future__ import annotations
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
from dash import dcc, html
from visualizer_engine.ui_models import UIColors, DarkTheme


class CardBuilder:
    """Builds standardized card components."""

    def __init__(self, colors: UIColors, theme: DarkTheme):
        """Initialize card builder."""
        self.colors = colors
        self.theme = theme

    def create_card(self, title: str, body_content, class_name: str = "mb-4") -> dbc.Card:
        """Create standardized card component."""
        return dbc.Card(
            [
                dbc.CardHeader(
                    title,
                    style={
                        "backgroundColor": self.theme.bg_tertiary,
                        "color": self.theme.text,
                        "padding": "15px",
                    },
                ),
                dbc.CardBody(body_content, style={"backgroundColor": self.theme.bg_secondary, "padding": "20px"}),
            ],
            className=class_name,
            style={"border": f"1px solid {self.theme.border}"},
        )


class ButtonBuilder:
    """Builds standardized button components."""

    def __init__(self, colors: UIColors):
        """Initialize button builder."""
        self.colors = colors

    def create_outline_button(self, text: str, id_: str, color: str) -> dbc.Button:
        """Create standardized outline button."""
        color_hex = getattr(self.colors, color, self.colors.secondary)
        return dbc.Button(
            text,
            id=id_,
            color=color,
            outline=True,
            className="me-3",
            style={"borderColor": color_hex, "color": color_hex},
        )


class BadgeBuilder:
    """Builds status badge components."""

    def __init__(self, theme: DarkTheme):
        """Initialize badge builder."""
        self.theme = theme

    def create_status_badge(self, text: str, color: str, id_: str = None) -> dbc.Badge:
        """Create status badge."""
        base_style = {
            "fontSize": "13px",
            "padding": "8px 12px",
            "backgroundColor": "transparent",
            "border": f"1px solid {color}",
            "color": color,
        }

        props = {"pill": True, "style": base_style}
        if id_:
            props["id"] = id_

        return dbc.Badge(text, **props)


class TableBuilder:
    """Builds AG Grid table components."""

    def __init__(self, theme: DarkTheme):
        """Initialize table builder."""
        self.theme = theme

    def create_sector_table(self) -> dag.AgGrid:
        """Create AG Grid for sector data."""
        col_defs = [
            {
                "headerName": "Sector",
                "field": "Sector",
                "sortable": True,
                "filter": True,
                "resizable": True,
                "width": 120,
                "cellStyle": {"color": "#e0e0e0", "backgroundColor": "transparent"},
            },
            {
                "headerName": "Metric",
                "field": "Metric",
                "sortable": True,
                "filter": True,
                "resizable": True,
                "wrapText": True,
                "autoHeight": True,
                "cellStyle": {
                    "whiteSpace": "normal",
                    "lineHeight": "1.3rem",
                    "color": "#e0e0e0",
                    "backgroundColor": "transparent",
                },
            },
            {
                "headerName": "Value",
                "field": "Value",
                "sortable": True,
                "filter": True,
                "resizable": True,
                "wrapText": True,
                "autoHeight": True,
                "cellStyle": {
                    "whiteSpace": "normal",
                    "lineHeight": "1.3rem",
                    "color": "#e0e0e0",
                    "backgroundColor": "transparent",
                },
            },
        ]

        return dag.AgGrid(
            id="sector-data-grid",
            className="ag-theme-alpine-dark",
            columnDefs=col_defs,
            rowData=[],
            persistence=True,
            persistence_type="session",
            persisted_props=["filterModel", "sortModel", "columnState"],
            defaultColDef={"minWidth": 100, "flex": 1},
            dashGridOptions={
                "domLayout": "normal",
                "suppressScrollOnNewData": True,
                "deltaRowDataMode": True,
                "getRowId": "function(params) { return params.data._id; }",
                "animateRows": False,
                "suppressCellFocus": True,
                "sideBar": {
                    "toolPanels": ["filters", "columns"],
                    "defaultToolPanel": "filters",
                    "hiddenByDefault": False,
                },
                "rowSelection": "multiple",
                "enableRangeSelection": True,
            },
            style={"width": "100%", "height": "400px", "backgroundColor": "transparent"},
        )


class LayoutBuilder:
    """Builds major layout sections."""

    def __init__(
        self, colors: UIColors, theme: DarkTheme, read_only: bool, default_step_delay: float, default_max_steps: int
    ):
        """Initialize layout builder."""
        self.colors = colors
        self.theme = theme
        self.read_only = read_only
        self.default_step_delay = default_step_delay
        self.default_max_steps = default_max_steps

        # Initialize sub-builders
        self.card_builder = CardBuilder(colors, theme)
        self.button_builder = ButtonBuilder(colors)
        self.badge_builder = BadgeBuilder(theme)

    def build_header(self) -> html.Div:
        """Build dashboard header."""
        return html.Div(
            [
                html.H1(
                    "🚀 PROXIMA LUNAR COMMAND",
                    className="text-center mb-2",
                    style={
                        "color": "#e8f4f8",
                        "paddingTop": "20px",
                        "fontSize": "32px",
                        "fontWeight": "300",
                        "letterSpacing": "2px",
                        "textShadow": "0 2px 4px rgba(0,0,0,0.5)",
                    },
                ),
                html.P(
                    "Mission Control Dashboard",
                    className="text-center mb-3",
                    style={"color": "#9ca3af", "fontSize": "14px", "fontWeight": "400", "letterSpacing": "1px"},
                ),
                html.Div(
                    id="status-display",
                    className="mb-4 text-center",
                    style={
                        "color": "#e0e0e0",
                        "fontSize": "16px",
                        "fontWeight": "bold",
                        "padding": "10px",
                        "backgroundColor": "rgba(0,0,0,0.2)",
                        "borderRadius": "8px",
                        "border": "1px solid rgba(255,255,255,0.1)",
                    },
                ),
                self.build_status_strip(),
            ],
            style={
                "marginBottom": "25px",
                "background": "linear-gradient(180deg, rgb(15,19,23) 0%, rgb(25,29,33) 50%, rgb(20,24,28) 100%)",
                "borderRadius": "16px",
                "padding": "25px",
                "border": "1px solid #404854",
            },
        )

    def build_status_strip(self) -> dbc.Card:
        """Build status strip with badges."""
        return dbc.Card(
            [
                dbc.CardBody(
                    [
                        html.H5(
                            "🌙 LUNAR BASE STATUS",
                            className="text-center mb-3",
                            style={"color": "#b8c5d6", "fontSize": "14px", "fontWeight": "600", "letterSpacing": "1px"},
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        self.badge_builder.create_status_badge("-", "#6c757d", id_=f"badge-{sector}")
                                        for sector in ["power", "science", "mfg", "dust"]
                                    ],
                                    width=12,
                                    className="d-flex align-items-center justify-content-center",
                                )
                            ]
                        ),
                    ],
                    style={"padding": "20px"},
                )
            ],
            className="mb-4",
            style={"border": "1px solid #404854", "borderRadius": "12px", "backgroundColor": "transparent"},
        )

    def build_simulation_control(self) -> dbc.Card:
        """Build simulation control panel."""
        buttons = dbc.ButtonGroup(
            [
                self.button_builder.create_outline_button("Start Continuous", "btn-start-continuous", "primary"),
                self.button_builder.create_outline_button("Start Limited", "btn-start-limited", "primary"),
                self.button_builder.create_outline_button("Pause", "btn-pause", "warning"),
                self.button_builder.create_outline_button("Resume", "btn-resume", "success"),
                self.button_builder.create_outline_button("Stop", "btn-stop", "danger"),
            ],
            className="mb-4",
        )

        inputs = dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label("Step Delay (s)", style={"color": "#e0e0e0", "marginBottom": "8px"}),
                        dbc.Input(
                            id="step-delay",
                            type="number",
                            value=self.default_step_delay,
                            min=0.01,
                            step=0.01,
                            style={
                                "backgroundColor": self.theme.bg_tertiary,
                                "border": f"1px solid {self.theme.border}",
                                "color": "#e0e0e0",
                                "padding": "10px",
                            },
                        ),
                    ],
                    width=6,
                ),
                dbc.Col(
                    [
                        dbc.Label("Max Steps", style={"color": "#e0e0e0", "marginBottom": "8px"}),
                        dbc.Input(
                            id="max-steps",
                            type="number",
                            value=self.default_max_steps,
                            min=1,
                            style={
                                "backgroundColor": self.theme.bg_tertiary,
                                "border": f"1px solid {self.theme.border}",
                                "color": "#e0e0e0",
                                "padding": "10px",
                            },
                        ),
                    ],
                    width=6,
                ),
            ]
        )

        return self.card_builder.create_card("Simulation Control", [buttons, inputs], "mb-5")

    def build_metric_status_panel(self) -> dbc.Card:
        """Build metric status panel."""
        return self.card_builder.create_card("Metric Status & Scores", html.Div(id="metric-tracker"), "mb-5")

    def build_metric_selector(self) -> dbc.Row:
        """Build metric selector checklist."""
        return dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label(
                            "Select Metrics:", style={"color": "#e0e0e0", "marginBottom": "15px", "fontSize": "14px"}
                        ),
                        dcc.Checklist(
                            id="metric-selector",
                            options=[],
                            value=[],
                            inline=False,
                            style={
                                "maxHeight": "150px",
                                "overflowY": "auto",
                                "marginBottom": "25px",
                                "color": "#e0e0e0",
                                "padding": "10px",
                                "border": f"1px solid {self.theme.border}",
                                "borderRadius": "4px",
                            },
                            inputStyle={"marginRight": "10px"},
                            labelStyle={
                                "display": "block",
                                "marginBottom": "8px",
                                "color": "#e0e0e0",
                                "padding": "4px 0",
                            },
                        ),
                    ],
                    width=12,
                )
            ]
        )

    def build_metric_plots_panel(self) -> dbc.Card:
        """Build metric plots panel."""
        return self.card_builder.create_card("Metrics Plots", [self.build_metric_selector(), html.Div(id="graph-grid")])

    def build_sector_data_panel(self, sector_table: dag.AgGrid) -> dbc.Card:
        """Build sector data panel."""
        return self.card_builder.create_card(
            "📊 All Sector Data",
            html.Div(
                [sector_table],
                style={"height": "420px", "overflow": "hidden"},
            ),
        )

    def build_tabs(self, sector_table: dag.AgGrid) -> dcc.Tabs:
        """Build main tab navigation."""
        tab_style = {
            "backgroundColor": self.theme.bg_secondary,
            "color": "#e0e0e0",
            "borderColor": "#404040",
            "borderBottomColor": "transparent",
            "padding": "20px 15px",
            "marginBottom": "0px",
        }

        tab_selected_style = {
            "backgroundColor": "rgb(50,54,58)",
            "color": "#ffffff",
            "fontWeight": "bold",
            "borderColor": "#404040",
            "borderBottomColor": "transparent",
            "padding": "20px 20px",
        }

        # Build analysis tab content
        analysis_content = [
            *([self.build_simulation_control()] if not self.read_only else []),
            self.build_metric_status_panel(),
            self.build_metric_plots_panel(),
        ]

        return dcc.Tabs(
            id="main-tabs",
            value="tab-analysis",
            children=[
                dcc.Tab(
                    label="🔬 Analysis Dashboard",
                    value="tab-analysis",
                    style=tab_style,
                    selected_style=tab_selected_style,
                    children=[html.Div(analysis_content)],
                ),
                dcc.Tab(
                    label="⚙️ Sector Details",
                    value="tab-summaries",
                    style=tab_style,
                    selected_style=tab_selected_style,
                    children=[html.Div([self.build_sector_data_panel(sector_table)])],
                ),
            ],
            style={
                "backgroundColor": "rgb(25,25,25)",
                "marginBottom": "25px",
                "borderColor": "#404040",
                "color": "#e0e0e0",
            },
        )

    def build_main_layout(self, sector_table: dag.AgGrid, update_rate_ms: int, update_cycles: int) -> dbc.Container:
        """Build complete application layout."""
        return dbc.Container(
            [
                dcc.Interval(id="interval-component", interval=update_rate_ms, n_intervals=update_cycles),
                self.build_header(),
                self.build_tabs(sector_table),
            ],
            fluid=True,
            style={
                "padding": "25px",
                "backgroundColor": "rgb(15,19,23)",
                "minHeight": "100vh",
                "background": "linear-gradient(135deg, rgb(15,19,23) 0%, rgb(25,29,33) 50%, rgb(20,24,28) 100%)",
            },
        )
