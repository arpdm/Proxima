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

class ProximaUI:
    """ProximaUI: Dashboard for Proxima simulation with time series plotting."""

    def __init__(self, db, experiment_id="exp_001"):
        self.db = db
        self.exp_id = experiment_id
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
        self.update_rate = 1000
        self.update_cycles = 60
        
        # Style constants
        self.COLORS = {
            'primary': '#0d6efd',
            'success': '#198754',
            'warning': '#ffc107',
            'danger': '#dc3545',
            'info': '#0dcaf0',
            'secondary': '#6c757d'
        }
        
        self.DARK_THEME = {
            'bg_primary': 'rgb(25,29,33)',
            'bg_secondary': 'rgb(35,39,43)',
            'bg_tertiary': 'rgb(45,49,53)',
            'border': '#404040',
            'text': '#e0e0e0',
            'text_muted': '#9ca3af'
        }
        
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
            # Try experiment-specific first
            ws = self.db.db["world_systems"].find_one({"latest_state.experiment_id": self.exp_id})
            if ws:
                return ws
                
            # Fallback to latest by step
            all_ws = list(self.db.db["world_systems"].find({}))
            if not all_ws:
                return None
                
            return max(all_ws, 
                      key=lambda w: (w.get("latest_state") or {}).get("step", -1),
                      default=all_ws[0])
        except Exception:
            return None

    def fetch_latest_logs(self, limit: int = 500) -> Optional[pd.DataFrame]:
        """Fetch latest logs with sliding window"""
        try:
            # Get latest step
            latest_log = self.fetch_collection(
                "logs_simulation",
                {"experiment_id": self.exp_id},
                sort=("step", -1),
                limit=1
            )
            if not latest_log:
                return None

            latest_step = latest_log[0].get("step", 0)
            start_step = max(0, latest_step - limit + 1)

            # Fetch logs in range
            docs = self.fetch_collection(
                "logs_simulation",
                {"experiment_id": self.exp_id, "step": {"$gte": start_step, "$lte": latest_step}},
                sort=("step", 1)
            )
            
            return self._flatten_logs_to_dataframe(docs)
            
        except Exception as e:
            print(f"❌ fetch_latest_logs error: {e}")
            return None

    def _flatten_logs_to_dataframe(self, docs: list) -> Optional[pd.DataFrame]:
        """Convert log documents to flattened DataFrame"""
        if not docs:
            return None
            
        flat_rows = []
        for d in docs:
            row = {
                "experiment_id": d.get("experiment_id"),
                "step": d.get("step"),
                "timestamp": d.get("timestamp"),
            }
            
            for k, v in d.items():
                if k in ("experiment_id", "step", "timestamp"):
                    continue
                    
                if isinstance(v, dict):
                    if k == "performance":
                        # Handle performance metrics specially
                        self._extract_performance_data(v, row)
                    else:
                        # Flatten other nested dicts
                        for sk, sv in v.items():
                            row[f"{k}_{sk}"] = sv
                else:
                    row[k] = v
                    
            flat_rows.append(row)
            
        try:
            return pd.DataFrame(flat_rows)
        except Exception as e:
            print(f"❌ DataFrame build error: {e}")
            return None

    def _extract_performance_data(self, perf_data: dict, row: dict):
        """Extract performance metrics and scores"""
        metrics = perf_data.get("metrics", {})
        if isinstance(metrics, dict):
            for mid, mval in metrics.items():
                row[f"metric_{mid}"] = mval
                
        scores = perf_data.get("scores", {})
        if isinstance(scores, dict):
            for mid, entry in scores.items():
                try:
                    row[f"score_{mid}"] = float(entry.get("score", None))
                except (TypeError, ValueError):
                    pass

    # ========================= UI COMPONENT BUILDERS ========================

    def _create_card(self, title: str, body_content, class_name: str = "mb-4") -> dbc.Card:
        """Create standardized card component"""
        return dbc.Card([
            dbc.CardHeader(title, style={
                "backgroundColor": self.DARK_THEME['bg_tertiary'], 
                "color": self.DARK_THEME['text'], 
                "padding": "15px"
            }),
            dbc.CardBody(body_content, style={
                "backgroundColor": self.DARK_THEME['bg_secondary'], 
                "padding": "20px"
            })
        ], className=class_name, style={"border": f"1px solid {self.DARK_THEME['border']}"})

    def _create_outline_button(self, text: str, id_: str, color: str) -> dbc.Button:
        """Create standardized outline button"""
        return dbc.Button(
            text, id=id_, color=color, outline=True, className="me-3",
            style={"borderColor": self.COLORS[color], "color": self.COLORS[color]}
        )

    def _create_sector_table_component(self):
        """Create AG Grid for sector data with Sector column"""
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
                "cellStyle": {"whiteSpace": "normal", "lineHeight": "1.3rem", "color": "#e0e0e0", "backgroundColor": "transparent"},
            },
            {
                "headerName": "Value", 
                "field": "Value",
                "sortable": True,
                "filter": True,
                "resizable": True,
                "wrapText": True,
                "autoHeight": True,
                "cellStyle": {"whiteSpace": "normal", "lineHeight": "1.3rem", "color": "#e0e0e0", "backgroundColor": "transparent"},
            }
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
                    "hiddenByDefault": False
                },
                "rowSelection": "multiple",
                "enableRangeSelection": True,
            },
            style={"width": "100%", "height": "400px", "backgroundColor": "transparent"},
        )

    def _status_badge(self, status: str, score: float = None) -> dbc.Badge:
        """Create status badge with appropriate color"""
        color_map = {"within": "success", "outside": "danger", "unknown": "warning"}
        color = color_map.get((status or "").lower(), "secondary")
        label = status if score is None else f"{status} ({score:.2f})"
        return dbc.Badge(label, color=color, pill=True, className="ms-1")

    def build_metric_tracker_table(self) -> html.Table:
        """Build metric tracker table with improved styling"""
        latest_logs = self.fetch_collection(
            "logs_simulation", {"experiment_id": self.exp_id},
            sort=("timestamp", -1), limit=1
        )
        
        if not latest_logs:
            return html.Div("No metric scores yet.", className="text-secondary text-center")
            
        scores = (latest_logs[0].get("performance", {}) or {}).get("scores", {}) or {}
        if not scores:
            return html.Div("No metric scores yet.", className="text-secondary text-center")

        # Table headers
        headers = ["Metric", "Id", "Score", "Status", "Current", "Range", "Goal"]
        header_style = {"backgroundColor": "rgb(30,40,60)", "color": "#e0e0e0", "border": "1px solid #405070", "padding": "12px"}
        header = html.Thead(html.Tr([html.Th(h, style=header_style) for h in headers]))

        # Table rows
        items = sorted(scores.items(), key=lambda kv: (kv[1].get("score") is None, kv[1].get("score", 0.0)))
        rows = []
        
        for i, (metric_id, entry) in enumerate(items):
            row_bg = "rgb(35,45,65)" if i % 2 == 0 else "rgb(40,50,70)"
            cell_style = {"backgroundColor": row_bg, "color": "#e0e0e0", "border": "1px solid #405070", "padding": "10px"}
            
            goal = entry.get("goal") or {}
            goal_txt = f'{goal.get("name", "")} {goal.get("target", "")}'.strip() or "-"
            
            score = entry.get("score")
            score_text = f"{float(score):.3f}" if isinstance(score, (int, float)) else "-"
            
            row_data = [
                entry.get("name", metric_id),
                metric_id,
                score_text,
                self._status_badge(entry.get("status", "unknown"), float(score) if isinstance(score, (int, float)) else None),
                str(entry.get("current", "")),
                f"[{entry.get('threshold_low', '')}, {entry.get('threshold_high', '')}]",
                goal_txt
            ]
            
            rows.append(html.Tr([html.Td(data, style=cell_style) for data in row_data]))

        return html.Table(
            [header, html.Tbody(rows)],
            style={
                "width": "100%", "borderCollapse": "collapse", "backgroundColor": "rgb(25,35,55)", 
                "color": "#e0e0e0", "whiteSpace": "normal", "wordWrap": "break-word", "margin": "15px 0"
            }
        )

    # ========================= LAYOUT SECTIONS ========================

    def _simulation_control(self):
        """Simulation control panel"""
        buttons = dbc.ButtonGroup([
            self._create_outline_button("Start Continuous", "btn-start-continuous", "primary"),
            self._create_outline_button("Start Limited", "btn-start-limited", "primary"),
            self._create_outline_button("Pause", "btn-pause", "warning"),
            self._create_outline_button("Resume", "btn-resume", "success"),
            self._create_outline_button("Stop", "btn-stop", "danger")
        ], className="mb-4")
        
        inputs = dbc.Row([
            dbc.Col([
                dbc.Label("Step Delay (s)", style={"color": "#e0e0e0", "marginBottom": "8px"}),
                dbc.Input(id="step-delay", type="number", value=0.1, min=0.01, step=0.01, 
                        style={"backgroundColor": self.DARK_THEME['bg_tertiary'], "border": f"1px solid {self.DARK_THEME['border']}", 
                               "color": "#e0e0e0", "padding": "10px"})
            ], width=6),
            dbc.Col([
                dbc.Label("Max Steps", style={"color": "#e0e0e0", "marginBottom": "8px"}),
                dbc.Input(id="max-steps", type="number", value=100, min=1, 
                        style={"backgroundColor": self.DARK_THEME['bg_tertiary'], "border": f"1px solid {self.DARK_THEME['border']}", 
                               "color": "#e0e0e0", "padding": "10px"})
            ], width=6)
        ])
        
        return self._create_card("Simulation Control", [buttons, inputs], "mb-5")

    def _metric_status_and_control(self):
        """Metric status and control panel"""
        return self._create_card("Metric Status & Scores", html.Div(id="metric-tracker"), "mb-5")

    def _metric_plots(self):
        """Metric plots panel"""
        selector = dbc.Row([
            dbc.Col([
                dbc.Label("Select Metrics:", style={"color": "#e0e0e0", "marginBottom": "15px", "fontSize": "14px"}),
                dcc.Checklist(
                    id="metric-selector", options=[], value=[], inline=False,
                    style={
                        "maxHeight": "150px", "overflowY": "auto", "marginBottom": "25px", 
                        "color": "#e0e0e0", "padding": "10px", "border": f"1px solid {self.DARK_THEME['border']}", 
                        "borderRadius": "4px"
                    },
                    inputStyle={"marginRight": "10px"},
                    labelStyle={"display": "block", "marginBottom": "8px", "color": "#e0e0e0", "padding": "4px 0"}
                ),
            ], width=12)
        ])
        
        return self._create_card("Metrics Plots", [selector, html.Div(id="graph-grid")])

    def _status_strip(self):
        return dbc.Card([
            dbc.CardBody([
                html.H5("🌙 LUNAR BASE STATUS", className="text-center mb-3", 
                       style={"color": "#b8c5d6", "fontSize": "14px", "fontWeight": "600", "letterSpacing": "1px"}),
                dbc.Row([
                    dbc.Col([
                        dbc.Badge(id="badge-power", pill=True, className="me-3", color = None,
                                style={"fontSize": "13px", "padding": "8px 12px", "border": "1px solid #6c757d", 
                                       "backgroundColor": "transparent", "color": "#ffffff"}),
                        dbc.Badge(id="badge-science", pill=True, className="me-3", color = None,
                                style={"fontSize": "13px", "padding": "8px 12px", "border": "1px solid #6c757d", 
                                       "backgroundColor": "transparent" , "color": "#ffffff"}),
                        dbc.Badge(id="badge-mfg", pill=True, className="me-3", color = None,
                                style={"fontSize": "13px", "padding": "8px 12px", "border": "1px solid #6c757d", 
                                       "backgroundColor": "transparent", "color": "#ffffff"}),
                        dbc.Badge(id="badge-dust", pill=True, color = None,
                                style={"fontSize": "13px", "padding": "8px 12px", "border": "1px solid #6c757d", 
                                       "backgroundColor": "transparent", "color": "#ffffff"}),
                    ], width=12, className="d-flex align-items-center justify-content-center")
                ])
            ], style={"padding": "20px"})
        ], className="mb-4", style={"border": "1px solid #404854", "borderRadius": "12px", "backgroundColor": "transparent"})
    
    def _setup_layout(self):
        """Setup main application layout"""

        # Tab styles
        tab_style = {"backgroundColor": self.DARK_THEME['bg_secondary'], "color": "#e0e0e0", "borderColor": "#404040", 
                    "borderBottomColor": "transparent", "padding": "20px 15px", "marginBottom": "0px"}
        tab_selected_style = {"backgroundColor": "rgb(50,54,58)", "color": "#ffffff", "fontWeight": "bold", 
                             "borderColor": "#404040", "borderBottomColor": "transparent", "padding": "20px 20px"}

        # Main layout
        self.app.layout = dbc.Container([
            dcc.Interval(id="interval-component", interval=self.update_rate, n_intervals=self.update_cycles),
            
            # Header
            html.Div([
                html.H1("🚀 PROXIMA LUNAR COMMAND", className="text-center mb-2", 
                        style={"color": "#e8f4f8", "paddingTop": "20px", "fontSize": "32px", 
                               "fontWeight": "300", "letterSpacing": "2px", "textShadow": "0 2px 4px rgba(0,0,0,0.5)"}),
                html.P("Mission Control Dashboard", className="text-center mb-3",
                       style={"color": "#9ca3af", "fontSize": "14px", "fontWeight": "400", "letterSpacing": "1px"}),
                html.Div(id="status-display", className="mb-4 text-center", 
                        style={"color": "#e0e0e0", "fontSize": "16px", "fontWeight": "bold", 
                               "padding": "10px", "backgroundColor": "rgba(0,0,0,0.2)", 
                               "borderRadius": "8px", "border": "1px solid rgba(255,255,255,0.1)"}),
                self._status_strip(),
            ], style={
                "marginBottom": "25px", 
                "background": "linear-gradient(180deg, rgb(15,19,23) 0%, rgb(25,29,33) 50%, rgb(20,24,28) 100%)",
                "borderRadius": "16px", "padding": "25px", "border": "1px solid #404854"
            }),
            
            # Tabs
            dcc.Tabs(id="main-tabs", value="tab-analysis", children=[
                dcc.Tab(label="🔬 Analysis Dashboard", value="tab-analysis", style=tab_style, selected_style=tab_selected_style,
                       children=[html.Div([
                           self._simulation_control(),
                           self._metric_status_and_control(),
                           self._metric_plots()
                       ])]),
                dcc.Tab(label="⚙️ Sector Details", value="tab-summaries", style=tab_style, selected_style=tab_selected_style,
                       children=[html.Div([
                           self._create_card("📊 All Sector Data ", 
                                           html.Div([self._sector_table_component], style={"height": "420px", "overflow": "hidden"}))
                       ])])
            ], style={"backgroundColor": "rgb(25,25,25)", "marginBottom": "25px", "borderColor": "#404040", "color": "#e0e0e0"}),
        ], fluid=True, style={
            "padding": "25px", "backgroundColor": "rgb(15,19,23)", "minHeight": "100vh",
            "background": "linear-gradient(135deg, rgb(15,19,23) 0%, rgb(25,29,33) 50%, rgb(20,24,28) 100%)"
        })

    # ========================= CALLBACKS ========================

    def _register_callbacks(self):
        """Register all dashboard callbacks"""
        
        @self.app.callback(
            Output("metric-tracker", "children"),
            [Input("interval-component", "n_intervals")]
        )
        def update_metric_tracker(n):
            return self.build_metric_tracker_table()

        @self.app.callback(
            [Output("status-display", "children")] + 
            [Output(f"badge-{sector}", "children") for sector in ["power", "science", "mfg", "dust"]] +
            [Output(f"badge-{sector}", "style") for sector in ["power", "science", "mfg", "dust"]],
            [Input("interval-component", "n_intervals")]
        )
        def update_dashboard(n):
            return self._get_dashboard_status()

        @self.app.callback(
            [Output("metric-selector", "options"), Output("metric-selector", "value")],
            [Input("interval-component", "n_intervals")],
            [State("metric-selector", "value")]
        )
        def update_metric_options_and_selection(n, current_value):
            if n > 3:  # Only update options in first few cycles
                return dash.no_update, dash.no_update
                
            df = self.fetch_latest_logs()
            if df is None or df.empty:
                return [], []
                
            # Get numeric columns excluding system columns
            numeric_cols = [col for col in df.columns 
                           if col not in ["step", "timestamp", "experiment_id"] 
                           and not col.startswith(("metric_", "score_"))
                           and pd.api.types.is_numeric_dtype(df[col])]
            
            options = [{"label": col.replace("_", " ").title(), "value": col} for col in numeric_cols]
            
            # Initialize selection if empty
            if not current_value and options:
                preferred = ["energy_total_power_supply_kw", "energy_total_charge_level_kwh", 
                           "science_science_generated", "science_operational_rovers"]
                available = {opt["value"] for opt in options}
                chosen = [m for m in preferred if m in available][:4]
                
                # Fill remaining slots
                for opt in options:
                    if len(chosen) >= 4:
                        break
                    if opt["value"] not in chosen:
                        chosen.append(opt["value"])
                        
                return options, chosen[:4]
                
            return options, current_value or []

        @self.app.callback(
            Output("graph-grid", "children"),
            [Input("metric-selector", "value"), Input("interval-component", "n_intervals")]
        )
        def update_graph_grid(selected_metrics, n):
            if not selected_metrics:
                return html.Div("Select metrics to display graphs.", className="text-secondary text-center")
                
            df = self.fetch_latest_logs()
            if df is None or df.empty:
                return html.Div("No data available for plotting.", className="text-secondary text-center")
                
            return self.build_graph_grid(df, selected_metrics)

        @self.app.callback(
            Output("sector-data-grid", "rowData"),
            [Input("interval-component", "n_intervals")]
        )
        def update_sector_data(n):
            return self._build_sector_data()

        @self.app.callback(
            Output("btn-start-continuous", "disabled"),
            [Input(f"btn-{action}", "n_clicks") for action in ["start-continuous", "start-limited", "pause", "resume", "stop"]] +
            [Input("step-delay", "value"), Input("max-steps", "value")],
            prevent_initial_call=True
        )
        def handle_controls(*args):
            import dash
            ctx = dash.callback_context
            if not ctx.triggered:
                return dash.no_update
                
            button_id = ctx.triggered[0]["prop_id"].split(".")[0]
            commands = {
                "btn-start-continuous": "start_continuous", "btn-start-limited": "start_limited", 
                "btn-pause": "pause", "btn-resume": "resume", "btn-stop": "stop", "step-delay": "set_delay"
            }
            
            if button_id in commands:
                action = commands[button_id]
                kwargs = {}
                if action == "set_delay":
                    kwargs["delay"] = args[-2]  # step-delay value
                elif action == "start_limited":
                    kwargs["max_steps"] = args[-1]  # max-steps value
                    
                self.send_command(action, **kwargs)
                
            return dash.no_update

    def _get_dashboard_status(self) -> tuple:
        """Get dashboard status and badge information"""
        ws = self.get_world_system_data()
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

        # Get latest sector data
        latest_logs = self.fetch_collection("logs_simulation", {"experiment_id": self.exp_id}, sort=("timestamp", -1), limit=1)
    
        # Base style using dark background color
        base_style = {
            "fontSize": "13px", 
            "padding": "8px 12px", 
            "backgroundColor": "transparent"
        }
        
        if not latest_logs:
            default_style = {**base_style, "border": "1px solid #6c757d", "color": "#6c757d"}
            return (
                status,                    # status-display children
                "⚡ PWR: -",                # badge-power children
                "🔬 SCI: -",               # badge-science children  
                "⚙️ MFG: -",               # badge-mfg children
                "🌪️ DUST: -",             # badge-dust children
                default_style,             # badge-power style
                default_style,             # badge-science style
                default_style,             # badge-mfg style
                default_style              # badge-dust style
            )

        rec = latest_logs[0]
        energy = rec.get("energy", {}) or {}
        science = rec.get("science", {}) or {}
        mfg = rec.get("manufacturing", {}) or {}
        perf = rec.get("performance", {}) or {}

        # Power badge
        sup = energy.get("total_power_supply_kW", 0)
        need = energy.get("total_power_need_kW", 0)
        power_txt = f"⚡ PWR: {round(sup,1)}/{round(need,1)} kW"
        power_color = "#00FF88" if isinstance(sup, (int, float)) and isinstance(need, (int, float)) and sup >= need else "#ffc107"
        power_style = {**base_style, "border": f"1px solid {power_color}", "color": power_color}

        # Science badge
        s_ops = science.get("operational_rovers", 0)
        s_gen = science.get("science_generated", 0)
        sci_txt = f"🔬 SCI: {s_ops} rovers | {round(s_gen,2)}"
        sci_style = {**base_style, "border": "1px solid #0dcaf0", "color": "#0dcaf0"}

        # Manufacturing badge
        m_ops = mfg.get("active_operations", 0)
        sector_state = mfg.get("sector_state", "")
        mfg_txt = f"⚙️ MFG: {m_ops} ops | {sector_state}"
        mfg_color = "#0dcaf0" if m_ops > 0 else "#6c757d"
        mfg_style = {**base_style, "border": f"1px solid {mfg_color}", "color": mfg_color}

        # Dust badge
        dust_score = (perf.get("scores", {}) or {}).get("IND-DUST-COV", {}) or {}
        d_score = dust_score.get("score")
        d_status = dust_score.get("status", "unknown")
        dust_txt = f"🌪️ DUST: {round(d_score,2) if isinstance(d_score,(int,float)) else '-'}"
        dust_color = {"within": "#00FF88", "outside": "#dc3545"}.get(d_status, "#ffbf00")
        dust_style = {**base_style, "border": f"1px solid {dust_color}", "color": dust_color}

        # Return in the correct order: status, all badge texts, then all badge styles
        return (
            status,         # status-display children
            power_txt,      # badge-power children
            sci_txt,        # badge-science children
            mfg_txt,        # badge-mfg children
            dust_txt,       # badge-dust children
            power_style,    # badge-power style
            sci_style,      # badge-science style
            mfg_style,      # badge-mfg style
            dust_style      # badge-dust style
        )

    def _build_sector_data(self) -> List[Dict]:
        """Build sector data for the table with Sector column"""
        latest_logs = self.fetch_collection("logs_simulation", {"experiment_id": self.exp_id}, sort=("timestamp", -1), limit=1)
        
        if not latest_logs:
            return [{"Sector": "No Data", "Metric": "No Data", "Value": "N/A", "_id": "no_data"}]

        latest = latest_logs[0]
        all_rows = []
        
        # Define sectors to process
        sectors = {
            "Energy": latest.get("energy", {}),
            "Science": latest.get("science", {}), 
            "Manufacturing": latest.get("manufacturing", {}),
            "System": latest.get("environment", {})
        }
        
        for sector_name, sector_data in sectors.items():
            if not isinstance(sector_data, dict):
                continue
                
            for k, v in sector_data.items():
                # Handle complex values
                if isinstance(v, (dict, list)):
                    v = json.dumps(v)
                elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    v = str(v)
                    
                all_rows.append({
                    "Sector": sector_name,
                    "Metric": k,
                    "Value": str(v),
                    "_id": f"{sector_name.lower()}_{k}"
                })

        return all_rows if all_rows else [{"Sector": "No Data", "Metric": "No Data", "Value": "N/A", "_id": "no_data"}]

    def build_graph_grid(self, df: pd.DataFrame, selected_metrics: List[str]) -> html.Div:
        """Build responsive graph grid with improved performance"""
        if df is None or df.empty or not selected_metrics:
            return html.Div("No data available for plotting.", className="text-secondary text-center")

        palette = ["#00d4aa", "#8b5cf6", "#06b6d4", "#f59e0b", "#10b981", "#ef4444", "#3b82f6", "#f97316"]
        x = df.get("step", pd.Series(range(len(df))))
        cols = []

        for i, col in enumerate(selected_metrics):
            if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                continue

            y, color = df[col], palette[i % len(palette)]
            pretty_name = col.replace("_", " ").title()
            if col.startswith("metric_"):
                pretty_name = f"Metric {col[7:].replace('_',' ').title()}"
            elif col.startswith("score_"):
                pretty_name = f"Score {col[6:].replace('_',' ').title()}"

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines+markers", name=pretty_name,
                line=dict(color=color, width=3), marker=dict(color=color, size=4),
                hovertemplate=f"<b>{pretty_name}</b><br>Step: %{{x}}<br>Value: %{{y}}<extra></extra>"
            ))

            # Layout styling
            fig.update_layout(
                title={'text': f"<b>{pretty_name}</b>", 'y': 0.92, 'x': 0.5, 'xanchor': 'center', 
                      'font': {'size': 16, 'color': '#ffffff'}},
                margin=dict(l=60, r=30, t=60, b=50), height=320, showlegend=False,
                paper_bgcolor="rgba(35,39,43,0.95)", plot_bgcolor="rgba(25,29,33,0.8)",
                font=dict(color="#e0e0e0", family="Arial, sans-serif"),
                xaxis=dict(title="<b>Step</b>", gridcolor="rgba(100,100,100,0.3)", 
                          linecolor="rgba(100,100,100,0.5)", tickfont=dict(size=10, color="#c0c0c0")),
                yaxis=dict(title="<b>Value</b>", gridcolor="rgba(100,100,100,0.3)", 
                          linecolor="rgba(100,100,100,0.5)", tickfont=dict(size=10, color="#c0c0c0"), 
                          rangemode="tozero" if not col.startswith("score_") else None,
                          range=[0, 1.05] if col.startswith("score_") else None)
            )

            graph_card = dbc.Card([
                dbc.CardBody([
                    dcc.Graph(figure=fig, style={"height": "100%", "width": "100%"},
                             config={"displayModeBar": True, "displaylogo": False,
                                    "modeBarButtonsToRemove": ["pan2d", "select2d", "lasso2d", "autoScale2d"]})
                ], style={"padding": "10px"})
            ], style={"height": "100%", "backgroundColor": "rgb(35,39,43)", "border": "1px solid #404040",
                     "borderRadius": "8px", "boxShadow": "0 2px 4px rgba(0,0,0,0.3)"})

            cols.append(dbc.Col(graph_card, width=6, className="mb-4"))

        if not cols:
            return html.Div("No selectable numeric series.", className="text-secondary text-center")

        # Create responsive grid (2 columns per row)
        rows = [dbc.Row(cols[i:i+2], className="g-3") for i in range(0, len(cols), 2)]
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
        # Check if running in production (Cloud Run)
        if os.environ.get('PORT'):
            # Production mode - don't run here, let gunicorn handle it
            print("running in read only cloud runner mode")
            return self.app
        else:
            # Development mode
            print("running in development mode")
            self.app.run(debug=True, host='0.0.0.0', port=8050)


if __name__ == "__main__":
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "exp_001"
    db = ProximaDB()
    ProximaUI(db, experiment_id=exp_id).run()