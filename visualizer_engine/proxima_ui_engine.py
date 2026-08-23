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
import orjson  # noqa: F401 - force full import before threaded dev server can race on it (plotly.io lazily imports it)
import plotly.graph_objs as go
import pandas as pd
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import time
import json
import math
import os
import argparse

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from dash import dcc, html
from dash.dependencies import Input, Output, State
from data_engine.proxima_db_engine import ProximaDB

from visualizer_engine.ui_models import (
    UIConfig,
    UIColors,
    DarkTheme,
    DataFrameProcessor,
)

def parse_args():

    parser = argparse.ArgumentParser(description="Proxima Dashboard")
    parser.add_argument("--mongo-uri", type=str, default=None, help="MongoDB URI (overrides db choice)")
    parser.add_argument("--exp-id", type=str, default=None, help="Experiment ID")
    return parser.parse_args()

class ProximaUI:
    """ProximaUI: Dashboard for Proxima simulation with configurable sectors."""

    def __init__(
        self,
        db,
        experiment_id="exp_001",
        update_rate_ms=100,
        update_cycles=1,
        read_only=True,
        ts_data_count=200,
        custom_config: Optional[UIConfig] = None,
        hosted_db=None,
    ):
        self.db = db
        self.hosted_db = hosted_db
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

    def add_mission_log_entry(self, text: str) -> None:
        """Add a mission log comment, tagged with the current SOL (simulation step) and a timestamp."""
        text = (text or "").strip()
        if not text:
            return

        ws = self.get_world_system_data()
        sol = (ws.get("latest_state", {}) or {}).get("step", 0) if ws else 0

        entry = {
            "experiment_id": self.exp_id,
            "sol": sol,
            "text": text,
            "timestamp": datetime.now(timezone.utc),
        }
        try:
            self.db.db["mission_log"].insert_one(entry)
        except Exception as e:
            print(f"❌ add_mission_log_entry error: {e}")

        if self.hosted_db is not None:
            try:
                self.hosted_db.db["mission_log"].insert_one(dict(entry))
                print(f"✅ mission log entry also saved to hosted DB (sol={sol})")
            except Exception as e:
                print(f"❌ add_mission_log_entry (hosted) error: {e}")
        else:
            print("⚠️  mission log entry NOT saved to hosted DB - self.hosted_db is None (no hosted_db configured)")

    def fetch_mission_log_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch mission log entries for this experiment, most recent SOL/timestamp first."""
        try:
            cursor = (
                self.db.db["mission_log"]
                .find({"experiment_id": self.exp_id})
                .sort([("sol", -1), ("timestamp", -1)])
                .limit(limit)
            )
            return list(cursor)
        except Exception as e:
            print(f"❌ fetch_mission_log_entries error: {e}")
            return []

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

    def _create_card(self, title: str, body_content, class_name: str = "mb-4", min_height: str = None) -> html.Div:
        """Create standardized mission-control panel component"""

        body_style = {"padding": "20px"}

        # Add minimum height if specified
        if min_height:
            body_style["minHeight"] = min_height

        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [html.Span(className="mc-led mc-led--cyan"), html.Span(title)],
                            className="mc-panel-title",
                        ),
                    ],
                    className="mc-panel-header",
                ),
                html.Div(body_content, className="mc-panel-body", style=body_style),
            ],
            className=f"mc-panel {class_name}",
        )

    def _create_outline_button(self, text: str, id_: str, color: str) -> dbc.Button:
        """Create standardized outline button"""
        color_hex = getattr(self.colors, color, self.colors.secondary)
        return dbc.Button(
            text,
            id=id_,
            color=color,
            outline=True,
            className="mc-btn me-3",
            style={"borderColor": color_hex, "color": color_hex},
        )

    def _create_sector_table_component(self):
        """Create AG Grid for sector data - simplified"""
        mono_cell_style = {"color": "var(--mc-text)", "backgroundColor": "transparent", "fontFamily": "var(--mc-font-mono)"}
        col_defs = [
            {"field": "Sector", "sortable": True, "filter": True, "width": 180, "cellStyle": mono_cell_style},
            {"field": "Metric", "sortable": True, "filter": True, "flex": 1, "cellStyle": mono_cell_style},
            {"field": "Value", "sortable": True, "filter": True, "flex": 1, "cellStyle": mono_cell_style},
        ]

        return dag.AgGrid(
            id="sector-data-grid",
            className="ag-theme-alpine-dark",
            columnDefs=col_defs,
            rowData=[],
            defaultColDef={"resizable": True, "sortable": True, "filter": True},
            dashGridOptions={
                "domLayout": "autoHeight",
            },
            style={"width": "100%"},
        )

    def _status_badge(self, status: str, score: float = None) -> dbc.Badge:
        """Create status badge with appropriate color"""
        color_map = {"within": "success", "outside": "danger", "unknown": "warning"}
        color = color_map.get((status or "").lower(), "secondary")
        label = (status or "UNKNOWN").upper() if score is None else f"{(status or '').upper()} ({score:.2f})"
        return dbc.Badge(
            label,
            color=color,
            pill=False,
            className="ms-1",
            style={
                "fontFamily": "var(--mc-font-mono)",
                "letterSpacing": "0.5px",
                "borderRadius": "0",
            },
        )

    def build_metric_tracker_table(self) -> html.Table:
        """Build metric tracker table"""
        ws = self.get_world_system_data()
        if not ws:
            return html.Div("No metric scores yet.", className="text-secondary text-center")

        scores = (ws.get("latest_state", {}).get("sectors", {}).get("performance", {}) or {}).get("scores", {}) or {}
        if not scores:
            return html.Div("No metric scores yet.", className="text-secondary text-center")

        headers = ["Metric", "Id", "Score", "Status", "Current", "Goal"]
        header_style = {
            "backgroundColor": "var(--mc-bg-header)",
            "color": "var(--mc-cyan-bright)",
            "border": "1px solid var(--mc-border)",
            "padding": "10px 12px",
            "fontFamily": "var(--mc-font-body)",
            "fontWeight": "600",
            "fontSize": "11px",
            "letterSpacing": "1.5px",
            "textTransform": "uppercase",
        }
        header = html.Thead(html.Tr([html.Th(h, style=header_style) for h in headers]))

        items = sorted(scores.items(), key=lambda kv: (kv[1].get("score") is None, kv[1].get("score", 0.0)))
        rows = []

        for i, (metric_id, entry) in enumerate(items):
            row_bg = "var(--mc-bg-panel)" if i % 2 == 0 else "var(--mc-bg-panel-alt)"
            cell_style = {
                "backgroundColor": row_bg,
                "color": "var(--mc-text)",
                "border": "1px solid var(--mc-border)",
                "padding": "9px 12px",
                "fontFamily": "var(--mc-font-mono)",
                "fontSize": "13px",
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
                goal_txt,
            ]

            rows.append(html.Tr([html.Td(data, style=cell_style) for data in row_data]))

        return html.Table(
            [header, html.Tbody(rows)],
            style={
                "width": "100%",
                "borderCollapse": "collapse",
                "backgroundColor": "var(--mc-bg-panel)",
                "color": "var(--mc-text)",
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
                        dbc.Label("Step Delay (s)", className="mc-label d-block"),
                        dbc.Input(
                            id="step-delay",
                            type="number",
                            value=self.config.default_step_delay,
                            min=0.01,
                            step=0.01,
                            className="mc-input",
                            style={"padding": "10px"},
                        ),
                    ],
                    width=6,
                ),
                dbc.Col(
                    [
                        dbc.Label("Max Steps", className="mc-label d-block"),
                        dbc.Input(
                            id="max-steps",
                            type="number",
                            value=self.config.default_max_steps,
                            min=1,
                            className="mc-input",
                            style={"padding": "10px"},
                        ),
                    ],
                    width=6,
                ),
            ]
        )

        monte_carlo_controls = dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label("MC Steps per Run", className="mc-label d-block"),
                        dbc.Input(
                            id="mc-steps-per-run",
                            type="number",
                            value=100,
                            min=1,
                            step=1,
                            className="mc-input",
                            style={"padding": "10px"},
                        ),
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        dbc.Label("MC Number of Runs", className="mc-label d-block"),
                        dbc.Input(
                            id="mc-num-runs",
                            type="number",
                            value=10,
                            min=1,
                            step=1,
                            className="mc-input",
                            style={"padding": "10px"},
                        ),
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        dbc.Label("Monte Carlo", className="mc-label d-block"),
                        dbc.Button(
                            "Start Monte Carlo",
                            id="btn-start-monte-carlo",
                            color="primary",
                            outline=True,
                            className="mc-btn w-100",
                            style={"borderColor": "var(--mc-cyan)", "color": "var(--mc-cyan)"},
                        ),
                    ],
                    width=4,
                    style={"display": "flex", "flexDirection": "column", "justifyContent": "flex-end"},
                ),
            ],
            className="mt-3",
            align="end",
        )

        return self._create_card("Simulation Control", [buttons, inputs, monte_carlo_controls], "mb-5")

    def _metric_status_and_control(self):
        """Metric status and control panel"""
        return self._create_card("Metric Status & Scores", html.Div(id="metric-tracker"), "mb-5")

    def _categorize_metrics(self, numeric_cols: List[str]) -> Dict[str, List[str]]:
        """Group metric columns into their sector/category buckets, with an 'other' catch-all."""
        categories = self.config.metric_filter_config.categories
        grouped: Dict[str, List[str]] = {cat_id: [] for cat_id in categories}
        grouped["other"] = []

        for col in numeric_cols:
            assigned = False
            for cat_id, category in categories.items():
                if any(col.startswith(pattern) for pattern in category.metric_patterns):
                    grouped[cat_id].append(col)
                    assigned = True
                    break
            if not assigned:
                grouped["other"].append(col)

        return grouped

    def _build_sector_metric_sections(self, numeric_cols: List[str], selected_metrics: List[str]) -> List[html.Div]:
        """Build one scrollable, sector-grouped checklist section per category for the metric side panel."""
        categories = self.config.metric_filter_config.categories
        grouped = self._categorize_metrics(numeric_cols)
        selected_set = set(selected_metrics or [])

        sections = []
        for cat_id, metrics in grouped.items():
            if not metrics:
                continue

            if cat_id == "other":
                display_name, icon, color = "Other", "OTH", "var(--mc-text-dim)"
            else:
                category = categories[cat_id]
                display_name, icon, color = category.display_name, category.icon, category.color

            options = [{"label": m.replace("_", " ").title(), "value": m} for m in metrics]
            value = [m for m in metrics if m in selected_set]

            sections.append(
                html.Div(
                    [
                        html.Div(
                            f"[{icon}] {display_name}",
                            style={
                                "color": color,
                                "fontFamily": "var(--mc-font-body)",
                                "fontWeight": "700",
                                "fontSize": "13px",
                                "letterSpacing": "1.5px",
                                "textTransform": "uppercase",
                                "marginTop": "18px",
                                "marginBottom": "8px",
                                "borderBottom": f"1px solid {color}",
                                "paddingBottom": "6px",
                            },
                        ),
                        dbc.Checklist(
                            id={"type": "sector-metric-check", "category": cat_id},
                            options=options,
                            value=value,
                            switch=True,
                            inputStyle={"marginRight": "8px"},
                            labelStyle={
                                "display": "block",
                                "color": "var(--mc-text)",
                                "fontFamily": "var(--mc-font-mono)",
                                "fontSize": "13px",
                                "padding": "4px 0",
                            },
                        ),
                    ]
                )
            )

        return sections

    def _metric_plots(self):
        """Metric plots panel with a sector-grouped side panel selector (select/deselect per parameter)."""
        # Pre-populate options/defaults so plots render immediately on first load,
        # instead of waiting for a button click or a page refresh.
        df = self.fetch_latest_logs(limit=self.ts_data_count)
        numeric_cols = DataFrameProcessor.get_numeric_columns(df) if df is not None else []
        initial_value = DataFrameProcessor.get_default_metrics(numeric_cols, self.config.experiment_id) if numeric_cols else []

        panel_sections = self._build_sector_metric_sections(numeric_cols, initial_value)

        quick_actions = dbc.ButtonGroup(
            [
                dbc.Button(
                    "Select All",
                    id="btn-select-all-metrics",
                    size="sm",
                    color="primary",
                    outline=True,
                    className="mc-btn me-2",
                    style={"borderColor": "var(--mc-cyan)", "color": "var(--mc-cyan)"},
                ),
                dbc.Button(
                    "Clear Selection",
                    id="btn-clear-metrics",
                    size="sm",
                    color="secondary",
                    outline=True,
                    className="mc-btn me-2",
                    style={"borderColor": "var(--mc-text-dim)", "color": "var(--mc-text-dim)"},
                ),
                dbc.Button(
                    "Restore Defaults",
                    id="btn-default-metrics",
                    size="sm",
                    color="info",
                    outline=True,
                    className="mc-btn",
                    style={"borderColor": "var(--mc-amber)", "color": "var(--mc-amber)"},
                ),
            ],
            className="mb-3 d-flex flex-wrap",
        )

        metric_panel = dbc.Offcanvas(
            [quick_actions, html.Div(panel_sections, id="sector-metric-sections")],
            id="metric-panel-offcanvas",
            title="Configure Plot Parameters",
            placement="end",
            is_open=False,
            scrollable=True,
            style={
                "width": "420px",
                "backgroundColor": "var(--mc-bg-panel)",
                "color": "var(--mc-text)",
            },
        )

        open_button = dbc.Button(
            "⚙ Configure Metrics",
            id="btn-open-metric-panel",
            color="primary",
            outline=True,
            className="mc-btn mb-4",
            style={"borderColor": "var(--mc-cyan)", "color": "var(--mc-cyan)"},
        )

        selector = html.Div(
            [
                open_button,
                metric_panel,
                dcc.Store(id="metric-selector", data=initial_value),
                html.Div(
                    id="graph-grid",
                    style={
                        "minHeight": "400px",
                        "marginTop": "20px",
                        "padding": "20px 0",
                    },
                ),
            ]
        )

        return self._create_card("Metrics Plots", selector)

    def _mission_log(self):
        """Mission log: a slide-in scrolling pane to view entries, plus (non-read-only) a slide-in entry form."""
        log_offcanvas = dbc.Offcanvas(
            html.Div(id="mission-log-display", style={"overflowY": "auto"}),
            id="log-panel-offcanvas",
            title="Mission Log",
            placement="end",
            is_open=False,
            scrollable=True,
            style={
                "width": "420px",
                "backgroundColor": "var(--mc-bg-panel)",
                "color": "var(--mc-text)",
            },
        )

        view_button = dbc.Button(
            "📖 Mission Log",
            id="btn-open-log-panel",
            color="primary",
            outline=True,
            className="mc-btn me-3",
            style={"borderColor": "var(--mc-cyan)", "color": "var(--mc-cyan)"},
        )

        children = [view_button, log_offcanvas]

        if not self.read_only:
            entry_offcanvas = dbc.Offcanvas(
                [
                    dbc.Textarea(
                        id="mission-log-input",
                        placeholder="Add a mission log entry...",
                        className="mc-input mb-3",
                        style={"padding": "10px", "minHeight": "120px", "resize": "vertical"},
                    ),
                    dbc.Button(
                        "Add Entry",
                        id="btn-add-log-entry",
                        color="primary",
                        outline=True,
                        className="mc-btn w-100",
                        style={"borderColor": "var(--mc-cyan)", "color": "var(--mc-cyan)"},
                    ),
                ],
                id="log-entry-offcanvas",
                title="Add Log Entry",
                placement="end",
                is_open=False,
                scrollable=True,
                style={
                    "width": "420px",
                    "backgroundColor": "var(--mc-bg-panel)",
                    "color": "var(--mc-text)",
                },
            )

            entry_button = dbc.Button(
                "✎ Add Log Entry",
                id="btn-open-log-entry-panel",
                color="primary",
                outline=True,
                className="mc-btn",
                style={"borderColor": "var(--mc-amber)", "color": "var(--mc-amber)"},
            )

            children.extend([entry_button, entry_offcanvas])

        return self._create_card("Mission Log", html.Div(children, className="d-flex flex-wrap"), "mb-5")

    def _build_mission_log_display(self) -> html.Div:
        """Render mission log entries as a rolling list, most recent SOL/timestamp first."""
        entries = self.fetch_mission_log_entries(limit=100)
        if not entries:
            return html.Div("No log entries yet.", className="text-secondary text-center")

        rows = []
        for entry in entries:
            sol = entry.get("sol", 0)
            ts = entry.get("timestamp")
            ts_text = ts.strftime("%Y-%m-%d %H:%M:%S UTC") if isinstance(ts, datetime) else str(ts or "")

            rows.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(
                                    f"SOL {sol}",
                                    style={
                                        "color": "var(--mc-cyan-bright)",
                                        "fontFamily": "var(--mc-font-mono)",
                                        "fontWeight": "700",
                                        "fontSize": "12px",
                                        "letterSpacing": "1px",
                                    },
                                ),
                                html.Span(
                                    ts_text,
                                    style={
                                        "color": "var(--mc-text-dim)",
                                        "fontFamily": "var(--mc-font-mono)",
                                        "fontSize": "11px",
                                        "marginLeft": "12px",
                                    },
                                ),
                            ],
                            style={"marginBottom": "4px"},
                        ),
                        html.Div(
                            entry.get("text", ""),
                            style={
                                "color": "var(--mc-text)",
                                "fontFamily": "var(--mc-font-body)",
                                "fontSize": "13px",
                                "whiteSpace": "pre-wrap",
                            },
                        ),
                    ],
                    style={
                        "padding": "10px 12px",
                        "marginBottom": "8px",
                        "backgroundColor": "var(--mc-bg-panel-alt)",
                        "borderLeft": "2px solid var(--mc-cyan)",
                    },
                )
            )

        return html.Div(rows)

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
                className="mc-chip me-2 mb-2",
                style={
                    "padding": "6px 16px",
                    "borderColor": "var(--mc-cyan)",
                    "backgroundColor": "rgba(79,216,236,0.15)",
                    "color": "var(--mc-cyan-bright)",
                },
            )
        ]

        # Create button for each sector
        for sector in table_sectors:
            buttons.append(
                dbc.Button(
                    f"[{sector.icon}] {sector.display_name}",
                    id={"type": "sector-filter", "sector": sector.id},
                    color="secondary",
                    outline=True,
                    size="sm",
                    className="mc-chip me-2 mb-2",
                    style={
                        "padding": "6px 16px",
                        "borderColor": sector.color,
                        "color": sector.color,
                    },
                )
            )

        return html.Div(
            [
                html.Label("Filter by Sector:", className="mc-label d-block mb-3"),
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
                    pill=False,
                    className="me-3",
                    color=None,
                    style={
                        "fontFamily": "var(--mc-font-mono)",
                        "fontSize": "13px",
                        "padding": "8px 14px",
                        "border": "1px solid var(--mc-border)",
                        "borderLeft": "2px solid var(--mc-text-dim)",
                        "borderRadius": "0",
                        "backgroundColor": "var(--mc-bg-panel-alt)",
                        "color": "var(--mc-text)",
                    },
                )
            )

        return html.Div(
            [
                html.Div(
                    [html.Span(className="mc-led mc-led--cyan"), html.Span("LUNAR BASE STATUS")],
                    className="mc-panel-title justify-content-center w-100",
                    style={
                        "color": "var(--mc-cyan-bright)",
                        "fontSize": "12px",
                        "fontWeight": "600",
                        "letterSpacing": "2px",
                        "textTransform": "uppercase",
                        "marginBottom": "16px",
                        "justifyContent": "center",
                    },
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            badge_components,
                            width=12,
                            className="d-flex align-items-center justify-content-center flex-wrap",
                        )
                    ]
                ),
            ],
            className="mc-panel mb-4",
            style={"padding": "20px"},
        )

    def _setup_layout(self):
        """Setup main application layout"""

        tab_style = {
            "backgroundColor": "var(--mc-bg-panel)",
            "color": "var(--mc-text-dim)",
            "borderColor": "var(--mc-border)",
            "borderBottomColor": "transparent",
            "borderRadius": "0",
            "padding": "16px 20px",
            "marginBottom": "0px",
            "fontFamily": "var(--mc-font-body)",
            "fontWeight": "600",
            "fontSize": "13px",
            "letterSpacing": "2px",
            "textTransform": "uppercase",
        }
        tab_selected_style = {
            "backgroundColor": "var(--mc-bg-header)",
            "color": "var(--mc-cyan-bright)",
            "fontWeight": "700",
            "borderColor": "var(--mc-border-bright)",
            "borderTop": "2px solid var(--mc-cyan)",
            "borderBottomColor": "transparent",
            "borderRadius": "0",
            "padding": "16px 20px",
            "fontFamily": "var(--mc-font-body)",
            "fontWeight": "700",
            "fontSize": "13px",
            "letterSpacing": "2px",
            "textTransform": "uppercase",
        }

        self.app.layout = dbc.Container(
            [
                # Inject custom CSS using html.Link or dcc.Store
                html.Div(
                    [
                        dcc.Store(id="selected-sector", data="all"),
                    ],
                    style={"display": "none"},
                ),
                dcc.Interval(id="interval-component", interval=self.update_rate, n_intervals=self.update_cycles),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span(
                                            f"ID-{self.exp_id}".upper(),
                                            style={
                                                "fontFamily": "var(--mc-font-mono)",
                                                "color": "var(--mc-text-dim)",
                                                "fontSize": "13px",
                                                "letterSpacing": "1px",
                                            },
                                        ),
                                    ],
                                    style={"flex": "1"},
                                ),
                                html.Div(
                                    [
                                        html.H1(
                                            "PROXIMA MISSION CONTROL",
                                            className="text-center mb-0",
                                            style={
                                                "color": "var(--mc-cyan-bright)",
                                                "fontFamily": "var(--mc-font-display)",
                                                "fontSize": "28px",
                                                "fontWeight": "700",
                                                "letterSpacing": "6px",
                                                "textShadow": "0 0 18px rgba(79,216,236,0.35)",
                                            },
                                        ),
                                        html.P(
                                            "LUNAR SURFACE OPERATIONS · REAL-TIME TELEMETRY",
                                            className="text-center mb-0",
                                            style={
                                                "color": "var(--mc-text-dim)",
                                                "fontSize": "11px",
                                                "fontWeight": "500",
                                                "letterSpacing": "3px",
                                                "marginTop": "4px",
                                            },
                                        ),
                                    ],
                                    style={"flex": "2", "textAlign": "center"},
                                ),
                                html.Div(
                                    [
                                        html.Span(className="mc-led mc-led--green"),
                                        html.Span(
                                            "LIVE",
                                            style={
                                                "fontFamily": "var(--mc-font-mono)",
                                                "color": "var(--mc-green)",
                                                "fontSize": "12px",
                                                "letterSpacing": "2px",
                                                "marginLeft": "8px",
                                            },
                                        ),
                                    ],
                                    style={
                                        "flex": "1",
                                        "display": "flex",
                                        "alignItems": "center",
                                        "justifyContent": "flex-end",
                                        "gap": "6px",
                                    },
                                ),
                            ],
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "paddingTop": "18px",
                                "paddingBottom": "8px",
                            },
                        ),
                        html.Div(
                            id="status-display",
                            className="mb-4 text-center",
                            style={
                                "color": "var(--mc-cyan)",
                                "fontFamily": "var(--mc-font-mono)",
                                "fontSize": "15px",
                                "letterSpacing": "1px",
                                "padding": "10px",
                                "backgroundColor": "var(--mc-bg-panel-alt)",
                                "border": "1px solid var(--mc-border)",
                                "borderLeft": "3px solid var(--mc-cyan)",
                            },
                        ),
                        self._status_strip(),
                    ],
                    style={
                        "marginBottom": "25px",
                        "background": "linear-gradient(180deg, rgba(10,19,24,0.95) 0%, rgba(5,9,11,0.98) 100%)",
                        "borderRadius": "2px",
                        "padding": "0 25px 25px 25px",
                        "border": "1px solid var(--mc-border)",
                        "borderTop": "2px solid var(--mc-cyan)",
                    },
                ),
                dcc.Tabs(
                    id="main-tabs",
                    value="tab-analysis",
                    children=[
                        dcc.Tab(
                            label="Analysis Dashboard",
                            value="tab-analysis",
                            style=tab_style,
                            selected_style=tab_selected_style,
                            children=[
                                html.Div(
                                    [
                                        *([self._simulation_control()] if not self.read_only else []),
                                        self._mission_log(),
                                        self._metric_status_and_control(),
                                        self._metric_plots(),
                                    ]
                                )
                            ],
                        ),
                        dcc.Tab(
                            label="Sector Details",
                            value="tab-summaries",
                            style=tab_style,
                            selected_style=tab_selected_style,
                            children=[
                                html.Div(
                                    [
                                        self._create_card(
                                            "All Sector Data",
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
                        "backgroundColor": "var(--mc-bg-panel)",
                        "marginBottom": "25px",
                        "borderColor": "var(--mc-border)",
                        "color": "var(--mc-text)",
                    },
                    className="mc-tabs-wrapper",
                ),
            ],
            fluid=True,
            style={
                "padding": "25px",
                "backgroundColor": "var(--mc-bg-void)",
                "minHeight": "100vh",
            },
            className="mc-app-bg",
        )

        # Custom page shell - the mission-control theme itself lives in
        # visualizer_engine/assets/mission_control.css (auto-loaded by Dash).
        self.app.index_string = """
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>{%title%}</title>
                {%favicon%}
                {%css%}
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

        # Rebuild sector metric sections once real data shows up (they may be empty at first
        # page load if no logs exist yet). Stops rebuilding once populated so it doesn't wipe
        # out the user's live checkbox selections.
        @self.app.callback(
            Output("sector-metric-sections", "children"),
            Input("interval-component", "n_intervals"),
            State("sector-metric-sections", "children"),
            State("metric-selector", "data"),
        )
        def populate_sector_metric_sections(n, current_children, current_selection):
            if current_children:
                return dash.no_update

            df = self.fetch_latest_logs(limit=self.ts_data_count)
            numeric_cols = DataFrameProcessor.get_numeric_columns(df) if df is not None else []
            if not numeric_cols:
                return dash.no_update

            selected = current_selection or DataFrameProcessor.get_default_metrics(numeric_cols, self.config.experiment_id)
            return self._build_sector_metric_sections(numeric_cols, selected)

        # Slide-in mission log viewer toggle (always available, including read-only)
        @self.app.callback(
            Output("log-panel-offcanvas", "is_open"),
            Input("btn-open-log-panel", "n_clicks"),
            State("log-panel-offcanvas", "is_open"),
            prevent_initial_call=True,
        )
        def toggle_log_panel(n_clicks, is_open):
            return not is_open

        # Rolling mission log display (always available, including read-only)
        @self.app.callback(
            Output("mission-log-display", "children"),
            Input("interval-component", "n_intervals"),
        )
        def update_mission_log_display(n):
            return self._build_mission_log_display()

        if not self.read_only:

            # Slide-in entry-form toggle
            @self.app.callback(
                Output("log-entry-offcanvas", "is_open"),
                Input("btn-open-log-entry-panel", "n_clicks"),
                State("log-entry-offcanvas", "is_open"),
                prevent_initial_call=True,
            )
            def toggle_log_entry_panel(n_clicks, is_open):
                return not is_open

            # Add a mission log entry, clear the input, and close the entry panel
            @self.app.callback(
                Output("mission-log-input", "value"),
                Output("log-entry-offcanvas", "is_open", allow_duplicate=True),
                Input("btn-add-log-entry", "n_clicks"),
                State("mission-log-input", "value"),
                prevent_initial_call=True,
            )
            def submit_mission_log_entry(n_clicks, text):
                self.add_mission_log_entry(text)
                return "", False

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

        # Side-panel toggle
        @self.app.callback(
            Output("metric-panel-offcanvas", "is_open"),
            Input("btn-open-metric-panel", "n_clicks"),
            State("metric-panel-offcanvas", "is_open"),
            prevent_initial_call=True,
        )
        def toggle_metric_panel(n_clicks, is_open):
            return not is_open

        # Combine every sector checklist's selections into the single metric-selector store
        @self.app.callback(
            Output("metric-selector", "data"),
            Input({"type": "sector-metric-check", "category": dash.dependencies.ALL}, "value"),
        )
        def combine_selected_metrics(values_by_category):
            combined = []
            for values in values_by_category or []:
                combined.extend(values or [])
            return combined

        # Quick actions handler (select all / clear / restore defaults) applied across all sector checklists
        @self.app.callback(
            Output({"type": "sector-metric-check", "category": dash.dependencies.ALL}, "value"),
            [
                Input("btn-select-all-metrics", "n_clicks"),
                Input("btn-clear-metrics", "n_clicks"),
                Input("btn-default-metrics", "n_clicks"),
            ],
            State({"type": "sector-metric-check", "category": dash.dependencies.ALL}, "options"),
            prevent_initial_call=True,
        )
        def handle_metric_actions(select_all, clear, defaults, options_by_category):
            ctx = dash.callback_context
            if not ctx.triggered:
                return dash.no_update

            prop_id = ctx.triggered[0]["prop_id"].split(".")[0]

            if prop_id == "btn-select-all-metrics":
                return [[opt["value"] for opt in opts] for opts in options_by_category]
            elif prop_id == "btn-clear-metrics":
                return [[] for _ in options_by_category]
            elif prop_id == "btn-default-metrics":
                all_metrics = [opt["value"] for opts in options_by_category for opt in opts]
                default_metrics = set(DataFrameProcessor.get_default_metrics(all_metrics, self.config.experiment_id))
                return [[opt["value"] for opt in opts if opt["value"] in default_metrics] for opts in options_by_category]

            return dash.no_update

        @self.app.callback(
            Output("graph-grid", "children"),
            [
                Input("metric-selector", "data"),
                Input("interval-component", "n_intervals")  # Add this as Input, not State
            ],
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
                    for action in ["start-continuous", "start-limited", "pause", "resume", "stop", "start-monte-carlo"]
                ]
                + [Input("step-delay", "value"), Input("max-steps", "value")],
                [State("mc-steps-per-run", "value"), State("mc-num-runs", "value")],
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
                    "btn-start-monte-carlo": "start_monte_carlo",
                    "step-delay": "set_delay",
                }

                if button_id in commands:
                    action = commands[button_id]
                    kwargs = {}
                    step_delay = args[-4]
                    if action == "set_delay":
                        if step_delay is None:
                            return dash.no_update
                        kwargs["delay"] = step_delay
                    elif action in ["start_continuous", "start_limited", "start_monte_carlo"] and step_delay is not None:
                        kwargs["delay"] = step_delay

                    if action == "start_limited":
                        kwargs["max_steps"] = args[-3]
                    elif action == "start_monte_carlo":
                        steps_per_run = args[-2]
                        num_runs = args[-1]
                        if steps_per_run is not None and num_runs is not None:
                            kwargs["steps_per_run"] = int(steps_per_run)
                            kwargs["num_runs"] = int(num_runs)
                        else:
                            return dash.no_update

                    self.send_command(action, **kwargs)

                return dash.no_update

    def _status_readout(self, led_class: str, text: str) -> html.Div:
        """Build a status-display readout with an LED indicator."""
        return html.Div(
            [html.Span(className=f"mc-led {led_class}"), html.Span(text)],
            style={
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "gap": "10px",
            },
        )

    def _get_dashboard_status(self) -> tuple:
        """Get dashboard status and badge information using sector registry"""
        ws = self.get_world_system_data()

        # Determine main status
        if not ws:
            status = self._status_readout("mc-led--red", "OFFLINE - SOL 0")
        else:
            latest_state = ws.get("latest_state", {}) or {}
            sim_status = latest_state.get("simulation_status", {}) or {}
            is_running = sim_status.get("is_running", False)
            is_paused = sim_status.get("is_paused", False)
            step = latest_state.get("step", 0)

            if is_running and not is_paused:
                status = self._status_readout("mc-led--green", f"OPERATIONAL - SOL {step}")
            elif is_running and is_paused:
                status = self._status_readout("mc-led--amber", f"STANDBY - SOL {step}")
            else:
                status = self._status_readout("mc-led--red", f"OFFLINE - SOL {step}")

        base_style = {
            "fontFamily": "var(--mc-font-mono)",
            "fontSize": "13px",
            "padding": "8px 14px",
            "backgroundColor": "var(--mc-bg-panel-alt)",
            "borderRadius": "0",
        }

        # If no world system, return defaults
        if not ws:
            badge_sectors = self.config.sector_registry.get_badge_sectors()
            custom_badges = list(self.config.badge_registry.badges.keys())
            default_style = {**base_style, "border": "1px solid var(--mc-border)", "borderLeft": "2px solid var(--mc-text-dim)", "color": "var(--mc-text-dim)"}

            results = [status]
            # Add default text for each badge
            for sector in badge_sectors:
                results.append(f"[{sector.icon}] -")
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
                badge_text = f"[{sector_config.icon}] {sector_config.display_name}: -"
                badge_color = "#6c757d"

            results.append(badge_text)
            styles.append({**base_style, "border": f"1px solid {badge_color}", "borderLeft": f"2px solid {badge_color}", "color": badge_color})

        for badge_id, badge_config in self.config.badge_registry.badges.items():
            badge_text = f"{badge_config.display_name}: -"
            badge_color = badge_config.default_color
            results.append(badge_text)
            styles.append({**base_style, "border": f"1px solid {badge_color}", "borderLeft": f"2px solid {badge_color}", "color": badge_color})

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
                # Handle nested dicts - flatten one level deep
                if isinstance(v, dict):
                    for subkey, subval in v.items():
                        # Don't go deeper than 1 level
                        if isinstance(subval, (dict, list)):
                            continue
                        
                        # Handle special float values (NaN, Inf)
                        if isinstance(subval, float) and (math.isnan(subval) or math.isinf(subval)):
                            subval = str(subval)
                        
                        # Add nested value with dotted notation
                        if isinstance(subval, (str, int, float, bool, type(None))):
                            all_rows.append(
                                {
                                    "Sector": sector_config.display_name,
                                    "Metric": f"{k}.{subkey}",
                                    "Value": str(subval),
                                    "_id": f"{sector_config.id}_{k}_{subkey}",
                                }
                            )
                    continue
                
                # Skip lists
                if isinstance(v, list):
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
                    "text": f"<b>{pretty_name.upper()}</b>",
                    "y": 0.94,
                    "x": 0.5,
                    "xanchor": "center",
                    "font": {"size": 13, "color": "#8ff2ff", "family": "Rajdhani, sans-serif"},
                },
                margin=dict(l=55, r=25, t=50, b=45),
                height=320,
                showlegend=False,
                paper_bgcolor="rgba(11,20,26,0.0)",
                plot_bgcolor="rgba(5,9,11,0.35)",
                font=dict(color="#d7f2f6", family="Share Tech Mono, monospace"),
                xaxis=dict(
                    title="STEP",
                    gridcolor="rgba(79,216,236,0.12)",
                    linecolor="rgba(79,216,236,0.3)",
                    tickfont=dict(size=10, color="#6d8991"),
                    zeroline=False,
                ),
                yaxis=dict(
                    title="VALUE",
                    gridcolor="rgba(79,216,236,0.12)",
                    linecolor="rgba(79,216,236,0.3)",
                    tickfont=dict(size=10, color="#6d8991"),
                    rangemode="tozero" if not col.startswith("score_") else None,
                    range=[0, 1.05] if col.startswith("score_") else None,
                    zeroline=False,
                ),
            )

            graph_card = html.Div(
                [
                    html.Div(
                        dcc.Graph(
                            figure=fig,
                            style={"height": "100%", "width": "100%"},
                            config={
                                "displayModeBar": True,
                                "displaylogo": False,
                                "modeBarButtonsToRemove": ["pan2d", "select2d", "lasso2d", "autoScale2d"],
                            },
                        ),
                        style={"padding": "10px"},
                    )
                ],
                className="mc-panel",
                style={"height": "100%"},
            )

            cols.append(dbc.Col(graph_card, width=6, className="mb-4"))

        if not cols:
            return html.Div("No selectable numeric series.", className="text-secondary text-center")

        rows = [dbc.Row(cols[i : i + 2], className="g-3") for i in range(0, len(cols), 2)]
        return html.Div(rows, style={"padding": "15px 0", "backgroundColor": "transparent"})

    def send_command(self, action: str, **kwargs):
        """Send command to appropriate collection"""
        collection = (
            "startup_commands"
            if action in ["start_continuous", "start_limited", "start_monte_carlo"]
            else "runtime_commands"
        )
        command = {"action": action, "timestamp": time.time(), "experiment_id": self.exp_id, **kwargs}
        try:
            self.db.db[collection].insert_one(command)
            print(f"✅ Sent {collection} command: {command}")
        except Exception as e:
            print(f"❌ Command error: {e}")

    def run(self):
        """Run the dashboard application"""
        if os.environ.get("PORT"):
            print("🌐 Running in read-only cloud runner mode")
            return self.app
        else:
            print("🔧 Running in development mode")
            self.app.run(debug=False, host="0.0.0.0", port=8050)


def main():
    """Entry Point"""

    args = parse_args()
    exp_id = args.exp_id or "exp_001"
    hosted_uri = args.mongo_uri

    db = ProximaDB(uri="mongodb://localhost:27017", local=True)
    hosted_db = ProximaDB(uri=hosted_uri, local=False) if hosted_uri else None


    ProximaUI(
        db, experiment_id=exp_id, update_rate_ms=1000, update_cycles=1, read_only=False, hosted_db=hosted_db
    ).run()

if __name__ == "__main__":

    main()
