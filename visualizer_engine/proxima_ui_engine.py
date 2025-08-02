import dash
import sys
import plotly.graph_objs as go
import pandas as pd
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import time

from dash import dcc, html
from dash.dependencies import Input, Output, State
from data_engine.proxima_db_engine import ProximaDB


class ProximaUI:
    """ProximaUI: Main dashboard UI engine for the Proxima project."""

    def __init__(self, db, experiment_id="exp_001"):
        self.db = db
        self.exp_id = experiment_id
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.QUARTZ])
        self._setup_layout()
        self._register_callbacks()

    # ---------------------- Data Methods ----------------------
    
    def fetch_collection(self, collection_name, query=None, sort=None, limit=0):
        cursor = self.db.db[collection_name].find(query or {})
        if sort:
            cursor = cursor.sort(*sort)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def fetch_document(self, collection_name, doc_id):
        return self.db.db[collection_name].find_one({"_id": doc_id})

    def fetch_latest_logs(self, limit=50):
        logs = self.fetch_collection(
            "logs_simulation", {"experiment_id": self.exp_id}, sort=("timestamp", -1), limit=limit
        )
        if not logs:
            return pd.DataFrame()
        
        flattened_logs = []
        for log in logs:
            flat_log = {"step": log.get("step", 0), "timestamp": log.get("timestamp"), "experiment_id": log.get("experiment_id")}
            
            # Extract model metrics and agent states
            for key, value in log.items():
                if key not in ["agent_states", "step", "timestamp", "experiment_id"]:
                    flat_log[key] = value
            
            for agent_state in log.get("agent_states", []):
                if isinstance(agent_state, dict):
                    for key, value in agent_state.items():
                        if isinstance(value, (int, float, str)):
                            flat_log[key] = value
            
            flattened_logs.append(flat_log)
        
        return pd.DataFrame(flattened_logs)

    def extract_component_counts(self, ws):
        summary = {}
        for domain_dict in ws.get("active_components", []):
            for domain, components in domain_dict.items():
                for comp in components:
                    template_id = comp.get("template_id")
                    subtype = comp.get("subtype", "N/A")
                    quantity = comp.get("quantity", 1)
                    key = f"{template_id} ({subtype})" if subtype != "N/A" else template_id
                    summary[key] = summary.get(key, 0) + quantity
        return summary

    def extract_latest_state(self, ws):
        latest_state = ws.get("latest_state", {})
        if not latest_state:
            return {}
        
        def safe_numeric(value, default=0):
            try:
                return round(float(value), 2) if value is not None else default
            except (ValueError, TypeError):
                return default
        
        flattened = {"Step": latest_state.get("step", 0)}
        
        # Microgrid metrics
        microgrid = latest_state.get("microgrid", {})
        if microgrid:
            soc_raw = microgrid.get('total_state_of_charge_%', 0)
            soc_percent = safe_numeric(soc_raw * 100) if soc_raw else 0
            
            flattened.update({
                "Power Supply (kW)": safe_numeric(microgrid.get("total_power_supply_kW")),
                "Power Need (kW)": safe_numeric(microgrid.get("total_power_need_kW")),
                "Charge Level (kWh)": safe_numeric(microgrid.get("total_charge_level_kWh")),
                "State of Charge (%)": soc_percent,
                "Generators": len(microgrid.get("generator_status", [])),
                "Storage Units": len(microgrid.get("storage_status", [])),
            })
        
        # Science metrics
        science_rovers = latest_state.get("science_rovers", [])
        ws_metrics = latest_state.get("ws_metrics", {})
        flattened.update({
            "Science Rovers": len(science_rovers),
            "Science Generated": safe_numeric(ws_metrics.get("total_science_cumulative")),
        })
        
        return flattened

    # ---------------------- UI Components ----------------------

    def build_component_status_tables(self, ws):
        latest_state = ws.get("latest_state", {})
        microgrid = latest_state.get("microgrid", {})
        
        configs = {
            "generators": {"data": microgrid.get("generator_status", []), "prefix": "Gen"},
            "storages": {"data": microgrid.get("storage_status", []), "prefix": "Storage"},
            "rovers": {"data": latest_state.get("science_rovers", []), "prefix": "Rover"}
        }
        
        tables = {}
        for name, config in configs.items():
            table_data = self._build_component_table(config["data"], config["prefix"])
            tables[name] = self.generate_aggrid(table_data, height=300) if table_data else html.Div(f"No {name}")
        
        return tables

    def _build_component_table(self, components, id_prefix):
        if not components:
            return []
        
        table_data = []
        for i, component in enumerate(components):
            if not isinstance(component, dict):
                continue
            
            row = {"ID": f"{id_prefix}-{i+1}"}
            for key, value in component.items():
                formatted_key = key.replace("_", " ").title()
                row[formatted_key] = self._format_value(value)
            
            table_data.append(row)
        
        return table_data

    def _format_value(self, value):
        if value is None:
            return "N/A"
        if isinstance(value, float):
            return f"{value * 100:.1f}%" if 0 <= value <= 1 else round(value, 2)
        return str(value)

    def generate_aggrid(self, data, height=250, auto_height=False):
        if not data:
            return html.Div("No data available.")
        
        grid_options = {"domLayout": "autoHeight"} if auto_height else {}
        style = {} if auto_height else {"height": f"{height}px"}
        
        column_defs = []
        for key in data[0].keys():
            max_length = max(len(str(key)), max(len(str(row.get(key, ""))) for row in data))
            min_width = max(100, max_length * 10)
            
            column_defs.append({
                "field": key, "headerName": key, "minWidth": min_width, "flex": 1,
                "sortable": True, "resizable": True, "autoHeight": True, "wrapText": True
            })
        
        return dag.AgGrid(
            className="ag-theme-quartz-dark",
            columnDefs=column_defs,
            rowData=data,
            style=style,
            dashGridOptions={
                **grid_options,
                "suppressColumnVirtualisation": True,
                "autoSizeStrategy": {"type": "fitGridWidth", "defaultMinWidth": 100},
                "autoHeaderHeight": True, "wrapHeaderText": True
            }
        )

    def build_graph_grid(self, df, selected_metrics):
        if not selected_metrics or df is None or df.empty:
            return html.Div("Select metrics to display graphs.", className="text-secondary text-center")
        
        # FIXED: Better tick interval calculation
        if "step" in df.columns and not df.empty:
            step_range = df["step"].max() - df["step"].min()
            total_points = len(df)
            
            # Calculate appropriate tick interval based on data density
            if step_range <= 20:
                dtick = 2
            elif step_range <= 50:
                dtick = 5
            elif step_range <= 100:
                dtick = 10
            elif step_range <= 200:
                dtick = 20
            elif step_range <= 500:
                dtick = 50
            elif step_range <= 1000:
                dtick = 100
            else:
                dtick = 200
            
            # If we have too many points, increase the interval
            if total_points > 100:
                dtick = max(dtick, step_range // 10)
        else:
            dtick = 10
        
        colors = ["#00cc96", "#ab63fa", "#ff6692", "#19d3f3", "#ff9f40", "#ffff00"]
        
        graph_tiles = []
        for i, metric in enumerate(selected_metrics):
            if metric not in df.columns:
                continue
                
            color = colors[i % len(colors)]
            label = metric.replace("_", " ").title()
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["step"], y=df[metric], mode="lines+markers", name=label,
                line=dict(color=color, width=2), marker=dict(size=3, color=color)
            ))
            
            fig.update_layout(
                title=dict(text=label, font=dict(size=14, color="#e0e0e0")),
                xaxis=dict(
                    title="Step", 
                    color="#aaaaaa", 
                    dtick=dtick,  # Use calculated dtick
                    gridcolor="#404040", 
                    showgrid=True,
                    tickmode="linear"  # Ensure linear ticking
                ),
                yaxis=dict(title=label, color="#aaaaaa", gridcolor="#404040", showgrid=True),
                template="plotly_dark", paper_bgcolor="rgb(35,39,43)", plot_bgcolor="rgb(25,25,25)",
                font=dict(color="#e0e0e0", size=10), margin=dict(l=50, r=20, t=40, b=40),
                showlegend=False, hovermode="x unified"
            )
            
            graph_tiles.append(dbc.Col([
                dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False}, style={"height": "300px"})
            ], width=6, lg=6, xl=4, className="mb-3"))
        
        return dbc.Row(graph_tiles)

    # ---------------------- Layout & Callbacks ----------------------

    def _setup_layout(self):
        # Compact CSS
        self.app.index_string = """
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>Proxima Dashboard</title>
                {%favicon%}
                {%css%}
                <style>
                    body { background-color: #181a1b !important; color: #e0e0e0 !important; }
                    .proxima-card { background: #23272b; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.18); padding: 1.5rem; margin-bottom: 1.5rem; }
                    .proxima-header { letter-spacing: 2px; font-weight: 700; }
                    .full-height-card { background: #23272b; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.18); padding: 1.5rem; height: calc(100vh - 200px); overflow-y: auto; }
                    .control-panel { background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%); border: 1px solid #4a5568; border-radius: 16px; padding: 2rem; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
                    .control-header { color: #64b5f6; font-size: 1.4rem; font-weight: 600; margin-bottom: 1.5rem; }
                    .status-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 1rem 1.5rem; margin-bottom: 1.5rem; }
                    .status-indicator { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 1.1rem; }
                    .status-running { color: #4caf50; } .status-paused { color: #ff9800; } .status-stopped { color: #9e9e9e; }
                    .status-details { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 10px; font-size: 0.9rem; color: #b0bec5; }
                    .control-buttons { display: flex; gap: 8px; margin-bottom: 1.5rem; flex-wrap: wrap; }
                    .control-btn { flex: 1; min-width: 120px; height: 44px; border: none; border-radius: 8px; font-weight: 600; font-size: 0.9rem; transition: all 0.3s ease; display: flex; align-items: center; justify-content: center; gap: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
                    .btn-start-continuous { background: linear-gradient(135deg, #4caf50, #66bb6a); color: white; }
                    .btn-start-limited { background: linear-gradient(135deg, #2196f3, #42a5f5); color: white; }
                    .btn-pause { background: linear-gradient(135deg, #ff9800, #ffb74d); color: white; }
                    .btn-resume { background: linear-gradient(135deg, #00bcd4, #26c6da); color: white; }
                    .btn-stop { background: linear-gradient(135deg, #f44336, #ef5350); color: white; }
                    .control-btn:hover:not(:disabled) { transform: translateY(-2px); }
                    .control-btn:disabled { opacity: 0.5; cursor: not-allowed; }
                    .input-group { display: flex; gap: 20px; margin-top: 1rem; }
                    .input-container { flex: 1; display: flex; flex-direction: column; gap: 6px; }
                    .input-label { font-size: 0.85rem; font-weight: 600; color: #90a4ae; text-transform: uppercase; }
                    .control-input { background: rgba(255,255,255,0.08) !important; border: 1px solid rgba(255,255,255,0.2) !important; border-radius: 8px !important; color: #e0e0e0 !important; padding: 8px 12px !important; }
                    .metric-checklist-vertical { max-height: 200px; overflow-y: auto; border: 1px solid #444; border-radius: 8px; padding: 10px; background-color: #2a2e33; }
                    .metric-checklist-vertical .form-check { margin-bottom: 8px !important; }
                    .metric-checklist-vertical .form-check-input { background-color: #404040 !important; border-color: #666 !important; }
                    .metric-checklist-vertical .form-check-input:checked { background-color: #0d6efd !important; border-color: #0d6efd !important; }
                    .metric-checklist-vertical .form-check-label { color: #e0e0e0 !important; font-size: 0.9rem; }
                </style>
            </head>
            <body>
                {%app_entry%}
                <footer>{%config%}{%scripts%}{%renderer%}</footer>
            </body>
        </html>
        """

        self.app.layout = dbc.Container([
            dcc.Interval(id="interval-component", interval=1000, n_intervals=0),
            html.H1("Proxima", className="text-primary text-center fs-3 mb-4 proxima-header"),
            
            # Control Panel
            dbc.Row([dbc.Col([
                html.Div([
                    html.H4("Simulation Control", className="control-header"),
                    html.Div(id="simulation-status", className="status-card"),
                    html.Div([
                        html.Button([html.I(className="fas fa-play", style={"marginRight": "6px"}), "Start Continuous"], 
                                   id="btn-start-continuous", className="control-btn btn-start-continuous"),
                        html.Button([html.I(className="fas fa-step-forward", style={"marginRight": "6px"}), "Start Limited"], 
                                   id="btn-start-limited", className="control-btn btn-start-limited"),
                        html.Button([html.I(className="fas fa-pause", style={"marginRight": "6px"}), "Pause"], 
                                   id="btn-pause", className="control-btn btn-pause"),
                        html.Button([html.I(className="fas fa-play", style={"marginRight": "6px"}), "Resume"], 
                                   id="btn-resume", className="control-btn btn-resume"),
                        html.Button([html.I(className="fas fa-stop", style={"marginRight": "6px"}), "Stop"], 
                                   id="btn-stop", className="control-btn btn-stop"),
                    ], className="control-buttons"),
                    html.Div([
                        html.Div([
                            html.Label("Step Delay", className="input-label"),
                            dcc.Input(id="step-delay-input", type="number", value=0.1, min=0.01, max=5.0, step=0.01, className="control-input")
                        ], className="input-container"),
                        html.Div([
                            html.Label("Max Steps", className="input-label"),
                            dcc.Input(id="max-steps-input", type="number", value=100, min=1, className="control-input")
                        ], className="input-container"),
                    ], className="input-group"),
                ], className="control-panel"),
            ], width=12, className="mb-3")]),
            
            # Info Row
            dbc.Row([
                dbc.Col(html.Div(id="experiment-info", className="proxima-card"), width=4),
                dbc.Col(html.Div(id="environment-info", className="proxima-card"), width=4),
                dbc.Col(html.Div(id="component-summary", className="proxima-card"), width=4),
            ], className="mb-3"),
            
            # Main Content Row
            dbc.Row([
                # Graphs
                dbc.Col([
                    html.Div([
                        html.H4("Graphs", className="text-info mb-2"),
                        html.Div([
                            html.H5("Select Metrics to Plot:", className="text-info mb-2"),
                            dcc.Checklist(id="metric-selector", options=[], value=[], inline=False, 
                                         className="metric-checklist-vertical", style={"marginBottom": "20px"}),
                            html.Hr(style={"borderColor": "#444"}),
                        ]),
                        html.Div(id="graph-grid"),
                    ], className="proxima-card"),
                ], width=5, style={"paddingRight": "0.5rem"}),
                
                # Status Panels
                dbc.Col([
                    html.Div([html.H4("Generator Status", className="text-center text-secondary mb-3"), 
                             html.Div(id="generator-status-panel")], className="proxima-card"),
                    html.Div([html.H4("Storage Status", className="text-center text-secondary mb-3"), 
                             html.Div(id="storage-status-panel")], className="proxima-card"),
                    html.Div([html.H4("Rover Status", className="text-center text-secondary mb-3"), 
                             html.Div(id="rover-status-panel")], className="proxima-card"),
                ], width=4, style={"paddingLeft": "0.5rem", "paddingRight": "0.5rem"}),
                
                # Latest State
                dbc.Col([
                    html.Div([html.H4("Latest System State", className="text-info mb-3"), 
                             html.Div(id="latest-state-panel")], className="full-height-card"),
                ], width=3, style={"paddingLeft": "0.5rem"}),
            ]),
        ], fluid=True, style={"padding": "2rem", "backgroundColor": "#181a1b", "minHeight": "100vh"})

    def _register_callbacks(self):
        # Main dashboard update
        @self.app.callback(
            [Output(k, "children") for k in ["experiment-info", "environment-info", "component-summary", 
                                           "latest-state-panel", "generator-status-panel", 
                                           "storage-status-panel", "rover-status-panel"]],
            [Input("interval-component", "n_intervals")], [State("metric-selector", "value")], prevent_initial_call=False
        )
        def update_dashboard(n, current_selection):
            df = self.fetch_latest_logs()
            exp = self.fetch_document("experiments", self.exp_id)
            ws = self.fetch_document("world_systems", exp["world_system_id"]) if exp else None
            env = self.fetch_document("environments", ws["environment_id"]) if ws else None

            # Generate all components
            comp_summary = self.extract_component_counts(ws) if ws else {}
            comp_table = self.generate_aggrid([{"Component": k, "Count": v} for k, v in comp_summary.items()], auto_height=True)
            
            latest_state_data = self.extract_latest_state(ws) if ws else {}
            latest_state_table = self.generate_aggrid([{"Metric": k, "Value": v} for k, v in latest_state_data.items()], auto_height=True)
            
            status_tables = self.build_component_status_tables(ws) if ws else {"generators": html.Div("No data"), "storages": html.Div("No data"), "rovers": html.Div("No data")}
            
            exp_table = self.generate_aggrid([{k: v for k, v in exp.items() if k != "visualization_config"}]) if exp else html.Div("No experiment")
            env_table = self.generate_aggrid([{k: v if isinstance(v, (str, int, float)) else str(v) for k, v in env.items() if k != "_id"}]) if env else html.Div("No environment.")

            return (exp_table, env_table, comp_table, latest_state_table, 
                   status_tables["generators"], status_tables["storages"], status_tables["rovers"])

        # Status display
        @self.app.callback(Output("simulation-status", "children"), [Input("interval-component", "n_intervals")])
        def update_simulation_status(n):
            status = self.get_simulation_status()
            status_class = f"status-{status['status']}"
            icon = "🟢" if status["status"] == "running" else "🟡" if status["status"] == "paused" else "⚪"
            
            return html.Div([
                html.Div([
                    html.Span(icon, style={"fontSize": "1.2rem", "marginRight": "8px"}),
                    html.Span(f"Status: {status['status'].upper()}", className=f"status-indicator {status_class}"),
                    html.Small(f" ({status.get('mode', 'unknown')} mode)", style={"color": "#999", "marginLeft": "8px"})
                ]),
                html.Div([
                    html.Div([html.Strong("Current Step: "), html.Span(f"{status.get('current_step', 0):,}")]),
                    html.Div([html.Strong("Step Delay: "), html.Span(f"{status.get('step_delay', 0.1)}s")])
                ], className="status-details")
            ])

        # Control buttons
        @self.app.callback(
            [Output("btn-start-continuous", "disabled"), Output("btn-start-limited", "disabled"), 
             Output("btn-pause", "disabled"), Output("btn-resume", "disabled"), Output("btn-stop", "disabled")],
            [Input("btn-start-continuous", "n_clicks"), Input("btn-start-limited", "n_clicks"),
             Input("btn-pause", "n_clicks"), Input("btn-resume", "n_clicks"), Input("btn-stop", "n_clicks"),
             Input("step-delay-input", "value"), Input("max-steps-input", "value")],
            prevent_initial_call=True
        )
        def handle_simulation_controls(start_cont, start_lim, pause, resume, stop, delay, max_steps):
            import dash
            ctx = dash.callback_context
            if not ctx.triggered:
                return False, False, True, True, True
                
            button_id = ctx.triggered[0]["prop_id"].split(".")[0]
            
            button_actions = {
                "btn-start-continuous": ("start_continuous", (True, True, False, True, False)),
                "btn-start-limited": ("start_limited", (True, True, False, True, False)),
                "btn-pause": ("pause", (True, True, True, False, False)),
                "btn-resume": ("resume", (True, True, False, True, False)),
                "btn-stop": ("stop", (False, False, True, True, True)),
                "step-delay-input": ("set_delay", None)
            }
            
            if button_id in button_actions:
                action, button_states = button_actions[button_id]
                kwargs = {"delay": delay}
                if action == "start_limited":
                    kwargs["max_steps"] = max_steps
                
                self.send_simulation_command(action, **kwargs)
                return button_states or (False, False, True, True, True)
            
            return False, False, True, True, True

        # Graph callbacks
        @self.app.callback(Output("metric-selector", "options"), [Input("interval-component", "n_intervals")], prevent_initial_call=False)
        def update_metric_options(n):
            if n > 2:
                return dash.no_update
            df = self.fetch_latest_logs()
            if df is not None and not df.empty:
                fields = [col for col in df.columns if col not in ['step', 'timestamp', 'experiment_id'] and pd.api.types.is_numeric_dtype(df[col])]
                return [{"label": field.replace("_", " ").title(), "value": field} for field in fields]
            return []

        @self.app.callback(Output("metric-selector", "value"), [Input("metric-selector", "options")], [State("metric-selector", "value")], prevent_initial_call=True)
        def initialize_metrics_once(options, current_value):
            return current_value if current_value else [opt["value"] for opt in options[:4]] if options else []

        @self.app.callback(Output("graph-grid", "children"), [Input("metric-selector", "value"), Input("interval-component", "n_intervals")], prevent_initial_call=False)
        def update_graph_grid(selected_metrics, n):
            if not selected_metrics:
                return html.Div("Select metrics to display graphs.", className="text-secondary text-center")
            return self.build_graph_grid(self.fetch_latest_logs(), selected_metrics)

    # ---------------------- Simulation Control ----------------------

    def send_simulation_command(self, action, **kwargs):
        collection = "startup_commands" if action in ["start_continuous", "start_limited"] else "runtime_commands"
        command = {"action": action, "timestamp": time.time(), "experiment_id": self.exp_id, **kwargs}
        
        try:
            self.db.db[collection].insert_one(command)
            print(f"Command sent: {action}")
            return {"status": "success", "message": f"Command '{action}' sent"}
        except Exception as e:
            print(f"Command error: {e}")
            return {"status": "error", "message": str(e)}

    def get_simulation_status(self):
        try:
            exp = self.fetch_document("experiments", self.exp_id)
            ws_id = exp.get("world_system_id") if exp else None
            ws = self.fetch_document("world_systems", ws_id) if ws_id else None
            
            if not ws:
                return {"status": "stopped", "current_step": 0, "step_delay": 0.1}
                
            latest_state = ws.get("latest_state", {})
            simulation_status = latest_state.get("simulation_status", {})
            
            if not simulation_status:
                return {"status": "stopped", "current_step": latest_state.get("step", 0), "step_delay": 0.1}
            
            is_running = simulation_status.get("is_running", False)
            is_paused = simulation_status.get("is_paused", False)
            
            status = "paused" if is_running and is_paused else "running" if is_running else "stopped"
            
            return {
                "status": status,
                "current_step": latest_state.get("step", 0),
                "step_delay": simulation_status.get("step_delay", 0.1),
                "mode": simulation_status.get("mode", "unknown")
            }
            
        except Exception as e:
            print(f"Status fetch error: {e}")
            return {"status": "stopped", "current_step": 0, "step_delay": 0.1}

    def run(self):
        self.app.run(debug=True)


if __name__ == "__main__":
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "exp_001"
    db = ProximaDB()
    ProximaUI(db, experiment_id=exp_id).run()
