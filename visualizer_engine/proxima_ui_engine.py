"""
proxima_ui_engine.py

PROXIMA LUNAR SIMULATION - DASHBOARD UI ENGINE

PURPOSE:
========
Main dashboard application for the Proxima lunar simulation.
Provides real-time visualization, metrics tracking, and simulation control.
"""

import dash
import sys
import plotly.graph_objs as go
import pandas as pd
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import time
import json
import math
import os

from typing import Optional, Dict, Any, List
from datetime import datetime

from dash import dcc, html
from dash.dependencies import Input, Output, State
from data_engine.proxima_db_engine import ProximaDB

from visualizer_engine.ui_models import (
    UIConfig,
    UIColors,
    DarkTheme,
    DataFrameProcessor,
)


class ProximaUI:
    """ProximaUI: Dashboard for Proxima simulation with configurable sectors."""

    def __init__(
        self,
        db,
        experiment_id="exp_001",
        update_rate_ms=1000,
        update_cycles=1,
        read_only=True,
        ts_data_count=200,
        custom_config: Optional[UIConfig] = None,
    ):
        self.db = db
        self.exp_id = experiment_id

        # Initialize Dash app with external stylesheets AND suppress callback exceptions
        self.app = dash.Dash(
            __name__, external_stylesheets=[dbc.themes.DARKLY], suppress_callback_exceptions=True  # Add this
        )

        # Use custom config or create default
        if custom_config:
            self.config = custom_config
        else:
            self.config = UIConfig(
                experiment_id=experiment_id,
                update_rate_ms=update_rate_ms,
                update_cycles=update_cycles,
                ts_data_count=ts_data_count,
                read_only=read_only,
            )

        self.update_rate = self.config.update_rate_ms
        self.update_cycles = self.config.update_cycles
        self.ts_data_count = self.config.ts_data_count
        self.read_only = self.config.read_only

        # Style constants
        self.colors = UIColors()
        self.theme = DarkTheme()

        self._sector_table_component = self._create_sector_table_component()
        self._setup_layout()
        self._register_callbacks()

    # ========================= DATA METHODS ========================

    def fetch_collection(self, collection_name: str, query: dict = None, sort: tuple = None, limit: int = 0) -> list:
        """Unified collection fetching method"""
        cursor = self.db.db[collection_name].find(query or {})
        if sort:
            cursor = cursor.sort(*sort)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def get_world_system_data(self) -> Optional[Dict[str, Any]]:
        """Get world system data with fallback logic"""
        try:
            ws = self.db.db["world_systems"].find_one({"latest_state.experiment_id": self.exp_id})
            if ws:
                return ws

            all_ws = list(self.db.db["world_systems"].find({}))
            if not all_ws:
                return None

            return max(all_ws, key=lambda w: (w.get("latest_state") or {}).get("step", -1), default=all_ws[0])
        except Exception:
            return None

    def fetch_latest_logs(self, limit: int = 200) -> Optional[pd.DataFrame]:
        """Fetch latest logs with sliding window"""
        try:
            docs = self.fetch_collection(
                "logs_simulation",
                {"experiment_id": self.exp_id},
                sort=("step", -1),
                limit=limit,
            )
            docs = list(reversed(docs))
            return DataFrameProcessor.flatten_logs_to_dataframe(docs)
        except Exception as e:
            print(f"❌ fetch_latest_logs error: {e}")
            return None

    # ========================= UI COMPONENT BUILDERS ========================

    def _create_card(self, title: str, body_content, class_name: str = "mb-4") -> dbc.Card:
        """Create standardized card component"""
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

    def _create_outline_button(self, text: str, id_: str, color: str) -> dbc.Button:
        """Create standardized outline button"""
        color_hex = getattr(self.colors, color, self.colors.secondary)
        return dbc.Button(
            text,
            id=id_,
            color=color,
            outline=True,
            className="me-3",
            style={"borderColor": color_hex, "color": color_hex},
        )

    def _create_sector_table_component(self):
        """Create AG Grid for sector data with improved settings"""
        col_defs = [
            {
                "headerName": "Sector",
                "field": "Sector",
                "sortable": True,
                "filter": True,
                "resizable": True,
                "width": 180,
                "pinned": "left",  # Pin sector column for easy reference
                "cellStyle": {"color": "#e0e0e0", "backgroundColor": "transparent", "fontWeight": "500"},
            },
            {
                "headerName": "Metric",
                "field": "Metric",
                "sortable": True,
                "filter": True,
                "resizable": True,
                "wrapText": True,
                "autoHeight": True,
                "flex": 1,
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
                "flex": 1,
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
            defaultColDef={"minWidth": 100},
            dashGridOptions={
                "domLayout": "autoHeight",  # Changed from "normal" to prevent scrolling
                "suppressScrollOnNewData": True,
                "deltaRowDataMode": True,
                "getRowId": "function(params) { return params.data._id; }",
                "animateRows": False,
                "suppressCellFocus": True,
                "maintainColumnOrder": True,  # Maintain column order on updates
                "suppressColumnVirtualisation": True,  # Better for smaller grids
                "rowSelection": "multiple",
                "enableRangeSelection": True,
                "enableCellTextSelection": True,  # Allow text selection
                "ensureDomOrder": True,  # Helps with stability
            },
            style={"width": "100%", "backgroundColor": "transparent"},
        )

    def _status_badge(self, status: str, score: float = None) -> dbc.Badge:
        """Create status badge with appropriate color"""
        color_map = {"within": "success", "outside": "danger", "unknown": "warning"}
        color = color_map.get((status or "").lower(), "secondary")
        label = status if score is None else f"{status} ({score:.2f})"
        return dbc.Badge(label, color=color, pill=True, className="ms-1")

    def build_metric_tracker_table(self) -> html.Table:
        """Build metric tracker table"""
        ws = self.get_world_system_data()
        if not ws:
            return html.Div("No metric scores yet.", className="text-secondary text-center")

        scores = (ws.get("latest_state", {}).get("sectors", {}).get("performance", {}) or {}).get("scores", {}) or {}
        if not scores:
            return html.Div("No metric scores yet.", className="text-secondary text-center")

        headers = ["Metric", "Id", "Score", "Status", "Current", "Range", "Goal"]
        header_style = {
            "backgroundColor": "rgb(30,40,60)",
            "color": "#e0e0e0",
            "border": "1px solid #405070",
            "padding": "12px",
        }
        header = html.Thead(html.Tr([html.Th(h, style=header_style) for h in headers]))

        items = sorted(scores.items(), key=lambda kv: (kv[1].get("score") is None, kv[1].get("score", 0.0)))
        rows = []

        for i, (metric_id, entry) in enumerate(items):
            row_bg = "rgb(35,45,65)" if i % 2 == 0 else "rgb(40,50,70)"
            cell_style = {
                "backgroundColor": row_bg,
                "color": "#e0e0e0",
                "border": "1px solid #405070",
                "padding": "10px",
            }

            goal = entry.get("goal") or {}
            goal_txt = f'{goal.get("name", "")} {goal.get("target", "")}'.strip() or "-"

            score = entry.get("score")
            score_text = f"{float(score):.3f}" if isinstance(score, (int, float)) else "-"

            row_data = [
                entry.get("name", metric_id),
                metric_id,
                score_text,
                self._status_badge(
                    entry.get("status", "unknown"), float(score) if isinstance(score, (int, float)) else None
                ),
                str(entry.get("current", "")),
                f"[{entry.get('threshold_low', '')}, {entry.get('threshold_high', '')}]",
                goal_txt,
            ]

            rows.append(html.Tr([html.Td(data, style=cell_style) for data in row_data]))

        return html.Table(
            [header, html.Tbody(rows)],
            style={
                "width": "100%",
                "borderCollapse": "collapse",
                "backgroundColor": "rgb(25,35,55)",
                "color": "#e0e0e0",
                "whiteSpace": "normal",
                "wordWrap": "break-word",
                "margin": "15px 0",
            },
        )

    # ========================= LAYOUT SECTIONS ========================

    def _simulation_control(self):
        """Simulation control panel"""
        buttons = dbc.ButtonGroup(
            [
                self._create_outline_button("Start Continuous", "btn-start-continuous", "primary"),
                self._create_outline_button("Start Limited", "btn-start-limited", "primary"),
                self._create_outline_button("Pause", "btn-pause", "warning"),
                self._create_outline_button("Resume", "btn-resume", "success"),
                self._create_outline_button("Stop", "btn-stop", "danger"),
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
                            value=self.config.default_step_delay,
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
                            value=self.config.default_max_steps,
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

        return self._create_card("Simulation Control", [buttons, inputs], "mb-5")

    def _metric_status_and_control(self):
        """Metric status and control panel"""
        return self._create_card("Metric Status & Scores", html.Div(id="metric-tracker"), "mb-5")

    def _metric_plots(self):
        """Metric plots panel with advanced filtering"""
        selector = html.Div(
            [
                # Category Filter - Multiple Selection
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(
                                    "Filter by Categories (select multiple):",
                                    style={
                                        "color": "#e0e0e0",
                                        "marginBottom": "12px",
                                        "fontSize": "14px",
                                        "fontWeight": "500",
                                    },
                                ),
                                html.Div(id="metric-category-buttons", className="mb-3"),
                            ],
                            width=12,
                        )
                    ]
                ),
                # Metric Selector with dark theme styling
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(
                                    "Select Metrics (from all selected categories):",
                                    style={
                                        "color": "#e0e0e0",
                                        "marginBottom": "12px",
                                        "fontSize": "14px",
                                        "fontWeight": "500",
                                    },
                                ),
                                dcc.Dropdown(
                                    id="metric-selector",
                                    options=[],
                                    value=[],
                                    multi=True,
                                    searchable=True,
                                    placeholder="Search and select metrics from any category...",
                                    style={
                                        "marginBottom": "15px",
                                    },
                                    className="custom-dropdown",
                                ),
                            ],
                            width=12,
                        )
                    ]
                ),
                # Quick Actions
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.ButtonGroup(
                                    [
                                        dbc.Button(
                                            "Select All Visible",
                                            id="btn-select-all-metrics",
                                            size="sm",
                                            color="primary",
                                            outline=True,
                                            className="me-2",
                                        ),
                                        dbc.Button(
                                            "Clear Selection",
                                            id="btn-clear-metrics",
                                            size="sm",
                                            color="secondary",
                                            outline=True,
                                            className="me-2",
                                        ),
                                        dbc.Button(
                                            "Restore Defaults",
                                            id="btn-default-metrics",
                                            size="sm",
                                            color="info",
                                            outline=True,
                                        ),
                                    ],
                                    className="mb-4",
                                )
                            ],
                            width=12,
                        )
                    ]
                ),
            ]
        )

        return self._create_card("Metrics Plots", [selector, html.Div(id="graph-grid")])

    def _sector_filter_buttons(self):
        """Create sector filter button group"""
        # Get all table sectors
        table_sectors = self.config.sector_registry.get_table_sectors()

        # Create "All" button
        buttons = [
            dbc.Button(
                "All Sectors",
                id={"type": "sector-filter", "sector": "all"},
                color="primary",
                outline=False,
                size="sm",
                className="me-2 mb-2",
                style={
                    "borderRadius": "20px",
                    "padding": "6px 16px",
                    "fontSize": "13px",
                    "fontWeight": "500",
                },
            )
        ]

        # Create button for each sector
        for sector in table_sectors:
            buttons.append(
                dbc.Button(
                    f"{sector.icon} {sector.display_name}",
                    id={"type": "sector-filter", "sector": sector.id},
                    color="secondary",
                    outline=True,
                    size="sm",
                    className="me-2 mb-2",
                    style={
                        "borderRadius": "20px",
                        "padding": "6px 16px",
                        "fontSize": "13px",
                        "borderColor": sector.color,
                        "color": sector.color,
                    },
                )
            )

        return html.Div(
            [
                html.Label(
                    "Filter by Sector:",
                    style={"color": "#e0e0e0", "marginBottom": "12px", "fontSize": "14px", "fontWeight": "500"},
                ),
                html.Div(buttons, className="d-flex flex-wrap"),
            ],
            className="mb-4",
        )

    def _status_strip(self):
        """Build status strip with configurable badges"""
        # Get badge sectors from registry
        badge_sectors = self.config.sector_registry.get_badge_sectors()

        # Create badge components
        badge_components = []

        # Add sector badges
        for sector in badge_sectors:
            badge_components.append(
                dbc.Badge(
                    id=f"badge-{sector.id}",
                    pill=True,
                    className="me-3",
                    color=None,
                    style={
                        "fontSize": "13px",
                        "padding": "8px 12px",
                        "border": "1px solid #6c757d",
                        "backgroundColor": "transparent",
                        "color": "#ffffff",
                    },
                )
            )

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
                                    badge_components,
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

    def _setup_layout(self):
        """Setup main application layout"""

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

        self.app.layout = dbc.Container(
            [
                # Inject custom CSS using html.Link or dcc.Store
                html.Div(
                    [
                        dcc.Store(id="selected-sector", data="all"),
                        dcc.Store(id="selected-category", data="all"),
                    ],
                    style={"display": "none"},
                ),
                dcc.Interval(id="interval-component", interval=self.update_rate, n_intervals=self.update_cycles),
                html.Div(
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
                        self._status_strip(),
                    ],
                    style={
                        "marginBottom": "25px",
                        "background": "linear-gradient(180deg, rgb(15,19,23) 0%, rgb(25,29,33) 50%, rgb(20,24,28) 100%)",
                        "borderRadius": "16px",
                        "padding": "25px",
                        "border": "1px solid #404854",
                    },
                ),
                dcc.Tabs(
                    id="main-tabs",
                    value="tab-analysis",
                    children=[
                        dcc.Tab(
                            label="🔬 Analysis Dashboard",
                            value="tab-analysis",
                            style=tab_style,
                            selected_style=tab_selected_style,
                            children=[
                                html.Div(
                                    [
                                        *([self._simulation_control()] if not self.read_only else []),
                                        self._metric_status_and_control(),
                                        self._metric_plots(),
                                    ]
                                )
                            ],
                        ),
                        dcc.Tab(
                            label="⚙️ Sector Details",
                            value="tab-summaries",
                            style=tab_style,
                            selected_style=tab_selected_style,
                            children=[
                                html.Div(
                                    [
                                        self._create_card(
                                            "📊 All Sector Data",
                                            html.Div(
                                                [self._sector_filter_buttons(), self._sector_table_component],
                                            ),
                                        )
                                    ]
                                )
                            ],
                        ),
                    ],
                    style={
                        "backgroundColor": "rgb(25,25,25)",
                        "marginBottom": "25px",
                        "borderColor": "#404040",
                        "color": "#e0e0e0",
                    },
                ),
            ],
            fluid=True,
            style={
                "padding": "25px",
                "backgroundColor": "rgb(15,19,23)",
                "minHeight": "100vh",
                "background": "linear-gradient(135deg, rgb(15,19,23) 0%, rgb(25,29,33) 50%, rgb(20,24,28) 100%)",
            },
        )

        # Inject custom CSS after layout is created
        self.app.index_string = """
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>{%title%}</title>
                {%favicon%}
                {%css%}
                <style>
                    /* Dark theme for dropdown */
                    .Select-control {
                        background-color: rgb(45,49,53) !important;
                        border: 1px solid #404040 !important;
                        color: #e0e0e0 !important;
                    }
                    .Select-menu-outer {
                        background-color: rgb(35,39,43) !important;
                        border: 1px solid #404040 !important;
                        z-index: 9999 !important;
                    }
                    .Select-option {
                        background-color: rgb(35,39,43) !important;
                        color: #e0e0e0 !important;
                        padding: 8px 12px !important;
                    }
                    .Select-option:hover {
                        background-color: rgb(50,54,58) !important;
                        color: #ffffff !important;
                    }
                    .Select-option.is-selected {
                        background-color: #0d6efd !important;
                        color: #ffffff !important;
                    }
                    .Select-option.is-focused {
                        background-color: rgb(50,54,58) !important;
                        color: #ffffff !important;
                    }
                    .Select-value-label {
                        color: #e0e0e0 !important;
                    }
                    .Select-placeholder {
                        color: #9ca3af !important;
                    }
                    .Select-input > input {
                        color: #e0e0e0 !important;
                    }
                    .Select-multi-value-wrapper {
                        color: #e0e0e0 !important;
                    }
                    .Select-value {
                        background-color: #0d6efd !important;
                        border: 1px solid #0d6efd !important;
                        color: #ffffff !important;
                        border-radius: 4px !important;
                        padding: 2px 8px !important;
                    }
                    .Select-value-icon {
                        border-right: 1px solid rgba(255,255,255,0.3) !important;
                        padding: 0 5px !important;
                    }
                    .Select-value-icon:hover {
                        background-color: rgba(0,0,0,0.2) !important;
                        color: #ffffff !important;
                    }
                    .Select-clear-zone {
                        color: #e0e0e0 !important;
                    }
                    .Select-clear-zone:hover {
                        color: #dc3545 !important;
                    }
                    .Select-arrow-zone {
                        color: #e0e0e0 !important;
                    }
                    .Select-arrow {
                        border-color: #e0e0e0 transparent transparent !important;
                    }
                    .is-open .Select-arrow {
                        border-color: transparent transparent #e0e0e0 !important;
                    }
                    
                    /* Additional dropdown improvements */
                    .Select.is-focused:not(.is-open) > .Select-control {
                        border-color: #0d6efd !important;
                        box-shadow: 0 0 0 0.2rem rgba(13, 110, 253, 0.25) !important;
                    }
                    
                    /* Scrollbar styling for dropdown */
                    .Select-menu::-webkit-scrollbar {
                        width: 8px;
                    }
                    .Select-menu::-webkit-scrollbar-track {
                        background: rgb(25,29,33);
                    }
                    .Select-menu::-webkit-scrollbar-thumb {
                        background: rgb(60,64,68);
                        border-radius: 4px;
                    }
                    .Select-menu::-webkit-scrollbar-thumb:hover {
                        background: rgb(80,84,88);
                    }
                </style>
            </head>
            <body>
                {%app_entry%}
                <footer>
                    {%config%}
                    {%scripts%}
                    {%renderer%}
                </footer>
            </body>
        </html>
        """

    # ========================= CALLBACKS ========================

    def _register_callbacks(self):
        """Register all dashboard callbacks"""

        @self.app.callback(Output("metric-tracker", "children"), [Input("interval-component", "n_intervals")])
        def update_metric_tracker(n):
            return self.build_metric_tracker_table()

        # Dynamic badge callback based on configuration
        badge_sectors = self.config.sector_registry.get_badge_sectors()
        all_badge_ids = [s.id for s in badge_sectors]

        @self.app.callback(
            [Output("status-display", "children")]
            + [Output(f"badge-{bid}", "children") for bid in all_badge_ids]
            + [Output(f"badge-{bid}", "style") for bid in all_badge_ids],
            [Input("interval-component", "n_intervals")],
        )
        def update_dashboard(n):
            return self._get_dashboard_status()

        # Add store for selected categories (multiple selection)
        # Update the layout setup to include this store

        # Category button builder
        @self.app.callback(Output("metric-category-buttons", "children"), [Input("interval-component", "n_intervals")])
        def build_category_buttons(n):
            if n > 3:
                return dash.no_update

            categories = self.config.metric_filter_config.categories

            buttons = [
                dbc.Button(
                    "All Categories",
                    id={"type": "metric-category", "category": "all"},
                    color="primary",
                    outline=False,
                    size="sm",
                    className="me-2 mb-2",
                    style={"borderRadius": "20px", "padding": "6px 16px", "fontSize": "13px", "fontWeight": "500"},
                )
            ]

            for cat_id, category in categories.items():
                buttons.append(
                    dbc.Button(
                        f"{category.icon} {category.display_name}",
                        id={"type": "metric-category", "category": cat_id},
                        color="secondary",
                        outline=True,
                        size="sm",
                        className="me-2 mb-2",
                        style={
                            "borderRadius": "20px",
                            "padding": "6px 16px",
                            "fontSize": "13px",
                            "borderColor": category.color,
                            "color": category.color,
                        },
                    )
                )

            return html.Div(buttons, className="d-flex flex-wrap")

        # Multi-category filter handler
        @self.app.callback(
            [
                Output("selected-category", "data"),
                Output("metric-selector", "options"),
                Output({"type": "metric-category", "category": dash.dependencies.ALL}, "outline"),
                Output({"type": "metric-category", "category": dash.dependencies.ALL}, "color"),
            ],
            [Input({"type": "metric-category", "category": dash.dependencies.ALL}, "n_clicks")],
            [
                State({"type": "metric-category", "category": dash.dependencies.ALL}, "id"),
                State("selected-category", "data"),
            ],
        )
        def filter_metrics_by_categories(n_clicks, button_ids, current_categories):
            ctx = dash.callback_context
            df = self.fetch_latest_logs(limit=self.ts_data_count)
            if df is None or df.empty:
                return ["all"], [], [True] * len(button_ids), ["secondary"] * len(button_ids)

            numeric_cols = DataFrameProcessor.get_numeric_columns(df)

            # Initialize selected categories
            if isinstance(current_categories, str):
                selected_categories = [current_categories] if current_categories else ["all"]
            else:
                selected_categories = current_categories or ["all"]

            # Handle button clicks - toggle selection
            if ctx.triggered and ctx.triggered[0]["value"]:
                prop_id = ctx.triggered[0]["prop_id"]
                if "metric-category" in prop_id:
                    try:
                        clicked_category = json.loads(prop_id.split(".")[0])["category"]

                        if clicked_category == "all":
                            # If "All" is clicked, select only "all"
                            selected_categories = ["all"]
                        else:
                            # Remove "all" if it's there
                            if "all" in selected_categories:
                                selected_categories = []

                            # Toggle the clicked category
                            if clicked_category in selected_categories:
                                selected_categories.remove(clicked_category)
                            else:
                                selected_categories.append(clicked_category)

                            # If no categories selected, fall back to "all"
                            if not selected_categories:
                                selected_categories = ["all"]

                    except (json.JSONDecodeError, KeyError):
                        pass

            # Filter metrics based on selected categories
            if "all" in selected_categories:
                filtered_metrics = numeric_cols
            else:
                filtered_metrics = []
                for category_id in selected_categories:
                    category = self.config.metric_filter_config.categories.get(category_id)
                    if category:
                        category_metrics = [
                            m
                            for m in numeric_cols
                            if any(m.startswith(pattern) for pattern in category.metric_patterns)
                        ]
                        filtered_metrics.extend(category_metrics)

                # Remove duplicates while preserving order
                filtered_metrics = list(dict.fromkeys(filtered_metrics))

            # Create options with category prefixes for clarity
            options = []
            for col in filtered_metrics:
                # Determine which category this metric belongs to
                category_name = "Other"
                for cat_id, category in self.config.metric_filter_config.categories.items():
                    if any(col.startswith(pattern) for pattern in category.metric_patterns):
                        category_name = f"{category.icon} {category.display_name.split()[0]}"  # Just first word
                        break

                label = f"[{category_name}] {col.replace('_', ' ').title()}"
                options.append({"label": label, "value": col})

            # Update button states - show which categories are selected
            outlines = []
            colors = []

            for btn_id in button_ids:
                cat_id = btn_id["category"]
                if cat_id in selected_categories:
                    outlines.append(False)  # Solid button
                    colors.append("primary" if cat_id == "all" else "info")
                else:
                    outlines.append(True)  # Outline button
                    colors.append("secondary")

            return selected_categories, options, outlines, colors

        # Metric selector value handler (for quick actions)
        @self.app.callback(
            Output("metric-selector", "value"),
            [
                Input("btn-select-all-metrics", "n_clicks"),
                Input("btn-clear-metrics", "n_clicks"),
                Input("btn-default-metrics", "n_clicks"),
            ],
            [State("metric-selector", "options"), State("metric-selector", "value")],
            prevent_initial_call=True,
        )
        def handle_metric_actions(select_all, clear, defaults, options, current_value):
            ctx = dash.callback_context
            if not ctx.triggered:
                return dash.no_update

            prop_id = ctx.triggered[0]["prop_id"].split(".")[0]

            if prop_id == "btn-select-all-metrics":
                return [opt["value"] for opt in (options or [])]
            elif prop_id == "btn-clear-metrics":
                return []
            elif prop_id == "btn-default-metrics":
                # Get a sensible default from each selected category
                all_metrics = [opt["value"] for opt in (options or [])]
                return DataFrameProcessor.get_default_metrics(all_metrics)

            return dash.no_update

        @self.app.callback(
            Output("graph-grid", "children"),
            [Input("metric-selector", "value")],
            [State("interval-component", "n_intervals")],
        )
        def update_graph_grid(selected_metrics, n):
            if not selected_metrics:
                return html.Div("Select metrics to display graphs.", className="text-secondary text-center")

            df = self.fetch_latest_logs()
            if df is None or df.empty:
                return html.Div("No data available for plotting.", className="text-secondary text-center")

            return self.build_graph_grid(df, selected_metrics)

        # Sector filter callback (this only affects the table, not the plots)
        @self.app.callback(
            [
                Output("selected-sector", "data"),
                Output({"type": "sector-filter", "sector": dash.dependencies.ALL}, "outline"),
                Output({"type": "sector-filter", "sector": dash.dependencies.ALL}, "color"),
            ],
            [Input({"type": "sector-filter", "sector": dash.dependencies.ALL}, "n_clicks")],
            [State({"type": "sector-filter", "sector": dash.dependencies.ALL}, "id")],
            prevent_initial_call=True,
        )
        def handle_sector_filter(n_clicks, button_ids):
            ctx = dash.callback_context
            if not ctx.triggered or not ctx.triggered[0]["value"]:
                return dash.no_update, dash.no_update, dash.no_update

            triggered_id_str = ctx.triggered[0]["prop_id"].split(".")[0]
            if not triggered_id_str:
                return dash.no_update, dash.no_update, dash.no_update

            triggered_button = json.loads(triggered_id_str)
            selected_sector = triggered_button["sector"]

            outlines = [btn["sector"] != selected_sector for btn in button_ids]
            colors = ["primary" if btn["sector"] == selected_sector else "secondary" for btn in button_ids]

            return selected_sector, outlines, colors

        # Update sector data with filtering (this only affects the table)
        @self.app.callback(
            Output("sector-data-grid", "rowData"),
            [Input("interval-component", "n_intervals"), Input("selected-sector", "data")],
        )
        def update_sector_data(n, selected_sector):
            return self._build_sector_data(selected_sector)

        if not self.read_only:

            @self.app.callback(
                Output("btn-start-continuous", "disabled"),
                [
                    Input(f"btn-{action}", "n_clicks")
                    for action in ["start-continuous", "start-limited", "pause", "resume", "stop"]
                ]
                + [Input("step-delay", "value"), Input("max-steps", "value")],
                prevent_initial_call=False,
            )
            def handle_controls(*args):
                ctx = dash.callback_context
                if not ctx.triggered:
                    return dash.no_update

                button_id = ctx.triggered[0]["prop_id"].split(".")[0]
                commands = {
                    "btn-start-continuous": "start_continuous",
                    "btn-start-limited": "start_limited",
                    "btn-pause": "pause",
                    "btn-resume": "resume",
                    "btn-stop": "stop",
                    "step-delay": "set_delay",
                }

                if button_id in commands:
                    action = commands[button_id]
                    kwargs = {}
                    if action == "set_delay":
                        kwargs["delay"] = args[-2]
                    elif action == "start_limited":
                        kwargs["max_steps"] = args[-1]

                    self.send_command(action, **kwargs)

                return dash.no_update

    def _get_dashboard_status(self) -> tuple:
        """Get dashboard status and badge information using sector registry"""
        ws = self.get_world_system_data()

        # Determine main status
        if not ws:
            status = "🔴 OFFLINE - Sol 0"
        else:
            latest_state = ws.get("latest_state", {}) or {}
            sim_status = latest_state.get("simulation_status", {}) or {}
            is_running = sim_status.get("is_running", False)
            is_paused = sim_status.get("is_paused", False)
            step = latest_state.get("step", 0)

            if is_running and not is_paused:
                status = f"🟢 OPERATIONAL - Sol {step}"
            elif is_running and is_paused:
                status = f"🟡 STANDBY - Sol {step}"
            else:
                status = f"🔴 OFFLINE - Sol {step}"

        base_style = {"fontSize": "13px", "padding": "8px 12px", "backgroundColor": "transparent"}

        # If no world system, return defaults
        if not ws:
            badge_sectors = self.config.sector_registry.get_badge_sectors()
            custom_badges = list(self.config.badge_registry.badges.keys())
            default_style = {**base_style, "border": "1px solid #6c757d", "color": "#6c757d"}

            results = [status]
            # Add default text for each badge
            for sector in badge_sectors:
                results.append(f"{sector.icon} -")
            for badge_id in custom_badges:
                badge_cfg = self.config.badge_registry.get_badge(badge_id)
                results.append(f"{badge_cfg.display_name}: -" if badge_cfg else "-")
            # Add default styles
            for _ in range(len(badge_sectors) + len(custom_badges)):
                results.append(default_style)

            return tuple(results)

        # Extract sector data
        latest_state = ws.get("latest_state", {})
        sectors_data = latest_state.get("sectors", {}) if latest_state else {}

        results = [status]
        styles = []

        # Build sector badges
        for sector_config in self.config.sector_registry.get_badge_sectors():
            sector_data = sectors_data.get(sector_config.id, {}) or {}

            try:
                badge_text = sector_config.badge_format.format(**sector_data)
                badge_color = sector_config.color
            except (KeyError, ValueError, TypeError):
                # Fallback if formatting fails
                badge_text = f"{sector_config.icon} {sector_config.display_name}: -"
                badge_color = "#6c757d"

            results.append(badge_text)
            styles.append({**base_style, "border": f"1px solid {badge_color}", "color": badge_color})

        for badge_id, badge_config in self.config.badge_registry.badges.items():
            badge_text = f"{badge_config.display_name}: -"
            badge_color = badge_config.default_color
            results.append(badge_text)
            styles.append({**base_style, "border": f"1px solid {badge_color}", "color": badge_color})

        return tuple(results + styles)

    def _build_sector_data(self, selected_sector: str = "all") -> List[Dict]:
        """Build sector data for the table using sector registry with optional filtering"""
        ws = self.get_world_system_data()
        if not ws:
            return [{"Sector": "No Data", "Metric": "No Data", "Value": "N/A", "_id": "no_data"}]

        latest = ws.get("latest_state", {}).get("sectors", {})
        all_rows = []

        # Get table sectors
        table_sectors = self.config.sector_registry.get_table_sectors()

        # Filter by selected sector if not "all"
        if selected_sector != "all":
            table_sectors = [s for s in table_sectors if s.id == selected_sector]

        # Use sector registry to determine which sectors to display
        for sector_config in table_sectors:
            sector_data = latest.get(sector_config.id, {})
            if not isinstance(sector_data, dict):
                continue

            for k, v in sector_data.items():
                # Skip dictionaries and lists - only show raw string and numerical data
                if isinstance(v, (dict, list)):
                    continue

                # Handle special float values (NaN, Inf)
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    v = str(v)

                # Only add if value is string, number, or boolean
                if isinstance(v, (str, int, float, bool, type(None))):
                    all_rows.append(
                        {
                            "Sector": sector_config.display_name,
                            "Metric": k,
                            "Value": str(v),
                            "_id": f"{sector_config.id}_{k}",
                        }
                    )

        return all_rows if all_rows else [{"Sector": "No Data", "Metric": "No Data", "Value": "N/A", "_id": "no_data"}]

    def build_graph_grid(self, df: pd.DataFrame, selected_metrics: List[str]) -> html.Div:
        """Build responsive graph grid"""
        if df is None or df.empty or not selected_metrics:
            return html.Div("No data available for plotting.", className="text-secondary text-center")

        x = df.get("step", pd.Series(range(len(df))))
        cols = []

        for i, col in enumerate(selected_metrics):
            if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                continue

            y = df[col]
            color = self.colors.chart_colors[i % len(self.colors.chart_colors)]
            pretty_name = col.replace("_", " ").title()
            if col.startswith("metric_"):
                pretty_name = f"Metric {col[7:].replace('_',' ').title()}"
            elif col.startswith("score_"):
                pretty_name = f"Score {col[6:].replace('_',' ').title()}"

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines+markers",
                    name=pretty_name,
                    line=dict(color=color, width=3),
                    marker=dict(color=color, size=4),
                    hovertemplate=f"<b>{pretty_name}</b><br>Step: %{{x}}<br>Value: %{{y}}<extra></extra>",
                )
            )

            fig.update_layout(
                title={
                    "text": f"<b>{pretty_name}</b>",
                    "y": 0.92,
                    "x": 0.5,
                    "xanchor": "center",
                    "font": {"size": 16, "color": "#ffffff"},
                },
                margin=dict(l=60, r=30, t=60, b=50),
                height=320,
                showlegend=False,
                paper_bgcolor="rgba(35,39,43,0.95)",
                plot_bgcolor="rgba(25,29,33,0.8)",
                font=dict(color="#e0e0e0", family="Arial, sans-serif"),
                xaxis=dict(
                    title="<b>Step</b>",
                    gridcolor="rgba(100,100,100,0.3)",
                    linecolor="rgba(100,100,100,0.5)",
                    tickfont=dict(size=10, color="#c0c0c0"),
                ),
                yaxis=dict(
                    title="<b>Value</b>",
                    gridcolor="rgba(100,100,100,0.3)",
                    linecolor="rgba(100,100,100,0.5)",
                    tickfont=dict(size=10, color="#c0c0c0"),
                    rangemode="tozero" if not col.startswith("score_") else None,
                    range=[0, 1.05] if col.startswith("score_") else None,
                ),
            )

            graph_card = dbc.Card(
                [
                    dbc.CardBody(
                        [
                            dcc.Graph(
                                figure=fig,
                                style={"height": "100%", "width": "100%"},
                                config={
                                    "displayModeBar": True,
                                    "displaylogo": False,
                                    "modeBarButtonsToRemove": ["pan2d", "select2d", "lasso2d", "autoScale2d"],
                                },
                            )
                        ],
                        style={"padding": "10px"},
                    )
                ],
                style={
                    "height": "100%",
                    "backgroundColor": "rgb(35,39,43)",
                    "border": "1px solid #404040",
                    "borderRadius": "8px",
                    "boxShadow": "0 2px 4px rgba(0,0,0,0.3)",
                },
            )

            cols.append(dbc.Col(graph_card, width=6, className="mb-4"))

        if not cols:
            return html.Div("No selectable numeric series.", className="text-secondary text-center")

        rows = [dbc.Row(cols[i : i + 2], className="g-3") for i in range(0, len(cols), 2)]
        return html.Div(rows, style={"padding": "15px 0", "backgroundColor": "transparent"})

    def send_command(self, action: str, **kwargs):
        """Send command to appropriate collection"""
        collection = "startup_commands" if action in ["start_continuous", "start_limited"] else "runtime_commands"
        command = {"action": action, "timestamp": time.time(), "experiment_id": self.exp_id, **kwargs}
        try:
            self.db.db[collection].insert_one(command)
        except Exception as e:
            print(f"❌ Command error: {e}")

    def run(self):
        """Run the dashboard application"""
        if os.environ.get("PORT"):
            print("🌐 Running in read-only cloud runner mode")
            return self.app
        else:
            print("🔧 Running in development mode")
            self.app.run(debug=True, host="0.0.0.0", port=8050)


if __name__ == "__main__":
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "exp_001"
    db = ProximaDB(uri="mongodb://localhost:27017", local=True)
    ProximaUI(db, experiment_id=exp_id, update_rate_ms=1000, update_cycles=1, read_only=False).run()
