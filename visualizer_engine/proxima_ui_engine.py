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
    """ProximaUI: Dashboard for Proxima simulation with time series plotting."""

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
        """Fetch logs with nested structure for plotting."""
        logs = self.fetch_collection(
            "logs_simulation", {"experiment_id": self.exp_id}, sort=("timestamp", -1), limit=limit
        )
                
        if not logs:
            return pd.DataFrame()

        flattened_logs = []
        for log in logs:
            # Start with basic fields
            flat_log = {
                "step": log.get("step", 0), 
                "timestamp": log.get("timestamp", 0)
            }
            
            # Process each key in the log
            for key, value in log.items():
                # Skip metadata fields
                if key in ["_id", "experiment_id", "timestamp", "step"]:
                    continue
                    
                # If it's a nested dict (sector), flatten it WITHOUT sector prefix
                if isinstance(value, dict):
                    for inner_key, inner_value in value.items():
                        if isinstance(inner_value, (int, float)) and not isinstance(inner_value, bool):
                            flat_log[inner_key] = inner_value  # Use inner_key directly, no prefix
                # Otherwise add directly if numeric
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    flat_log[key] = value
        
            flattened_logs.append(flat_log)
        
        df = pd.DataFrame(flattened_logs)
        
        # Sort by step for proper time series plotting
        if not df.empty and "step" in df.columns:
            df = df.sort_values('step').reset_index(drop=True)
            
        return df

    def get_world_system_data(self):
        """Get current world system data."""
        try:
            exp = self.fetch_document("experiments", self.exp_id)
            if not exp:
                return None
            
            ws = self.fetch_document("world_systems", exp["world_system_id"])
            return ws
        except Exception as e:
            print(f"Error fetching world system: {e}")
            return None

    def build_sector_summary_tables(self):
        """Build summary tables directly from sector-organized data."""
        latest_logs = self.fetch_collection(
            "logs_simulation", 
            {"experiment_id": self.exp_id}, 
            sort=("timestamp", -1), 
            limit=1
        )
        
        if not latest_logs:
            empty_table = self.generate_aggrid([{"Metric": "No Data", "Value": "N/A"}], height=200)
            return {"energy": empty_table, "science": empty_table, "system": empty_table, "manufacturing": empty_table}
        
        latest_log = latest_logs[0]
        
        # Extract sector data directly
        environment_data = latest_log.get("environment", {})
        energy_data = latest_log.get("energy", {})
        science_data = latest_log.get("science", {})
        manufacturing_data = latest_log.get("manufacturing", {})  # Add this line
        
        # Convert to table format
        def sector_to_table(sector_data):
            return [{"Metric": k, "Value": v} for k, v in sector_data.items()]
        
        # Generate tables
        tables = {
            "energy": self.generate_aggrid(sector_to_table(energy_data), height=250),
            "science": self.generate_aggrid(sector_to_table(science_data), height=250),
            "system": self.generate_aggrid(sector_to_table(environment_data), height=200),
            "manufacturing": self.generate_aggrid(sector_to_table(manufacturing_data), height=300),  # Add this line
        }
        
        return tables

    # ---------------------- UI Components ----------------------

    def generate_aggrid(self, table_data, height=300):
        """Generate AgGrid table with simple formatting."""
        if not table_data:
            return html.Div("No data", className="text-secondary text-center")
        
        # Auto-generate columns
        columns = []
        for key in table_data[0].keys():
            columns.append({
                "field": key, 
                "headerName": key.replace("_", " ").title(),
                "flex": 1
            })
        
        return dag.AgGrid(
            className="ag-theme-quartz-dark",
            columnDefs=columns,
            rowData=table_data,
            style={"height": f"{height}px"},
            dashGridOptions={
                "suppressColumnVirtualisation": True,
                "rowHeight": 35,
                "headerHeight": 40
            }
        )

    def build_graph_grid(self, df, selected_metrics):
        """Build grid of time series graphs."""
        if df is None or df.empty or not selected_metrics:
            return html.Div("No data available for plotting.", className="text-secondary text-center")
        
        graphs = []
        colors = ["#00cc96", "#ab63fa", "#ff6692", "#19d3f3", "#ff9f40", "#ffff00"]
        
        for i, metric in enumerate(selected_metrics):
            if metric not in df.columns:
                continue
            
            color = colors[i % len(colors)]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["step"], 
                y=df[metric], 
                mode="lines+markers",
                name=metric,
                line=dict(color=color, width=2),
                marker=dict(size=4, color=color)
            ))
            
            fig.update_layout(
                title=dict(
                    text=metric.replace("_", " ").title(),
                    font=dict(size=14, color="#e0e0e0")
                ),
                xaxis=dict(
                    title="Step",
                    color="#aaaaaa",
                    gridcolor="#404040",
                    showgrid=True
                ),
                yaxis=dict(
                    title=metric,
                    color="#aaaaaa", 
                    gridcolor="#404040",
                    showgrid=True
                ),
                template="plotly_dark",
                paper_bgcolor="rgb(35,39,43)",
                plot_bgcolor="rgb(25,25,25)",
                font=dict(color="#e0e0e0", size=10),
                height=300,
                margin=dict(l=50, r=20, t=50, b=50),
                showlegend=False,
                hovermode="x unified"
            )
            
            graphs.append(dbc.Col([
                dcc.Graph(
                    figure=fig, 
                    style={"height": "300px"},
                    config={'displayModeBar': True, 'displaylogo': False}
                )
            ], width=6, lg=6, xl=4, className="mb-3"))
        
        return dbc.Row(graphs)

    # ---------------------- Layout ----------------------

    def _setup_layout(self):
        self.app.layout = dbc.Container([
            dcc.Interval(id="interval-component", interval=1000, n_intervals=0),
            html.H1("Proxima Dashboard", className="text-center mb-4", style={"color": "#e0e0e0"}),
            
            # Control Panel
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Simulation Control", style={"color": "#e0e0e0"}),
                            html.Div(id="status-display", className="mb-3", style={"color": "#e0e0e0", "fontSize": "16px", "fontWeight": "bold"}),
                            dbc.ButtonGroup([
                                dbc.Button("Start Continuous", id="btn-start-continuous", color="success", className="me-2"),
                                dbc.Button("Start Limited", id="btn-start-limited", color="primary", className="me-2"),
                                dbc.Button("Pause", id="btn-pause", color="warning", className="me-2"),
                                dbc.Button("Resume", id="btn-resume", color="info", className="me-2"),
                                dbc.Button("Stop", id="btn-stop", color="danger"),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Step Delay (s)", style={"color": "#e0e0e0"}),
                                    dbc.Input(id="step-delay", type="number", value=0.1, min=0.01, step=0.01, style={"backgroundColor": "rgb(45,49,53)", "border": "1px solid #404040", "color": "#e0e0e0"})
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Max Steps", style={"color": "#e0e0e0"}),
                                dbc.Input(id="max-steps", type="number", value=100, min=1, style={"backgroundColor": "rgb(45,49,53)", "border": "1px solid #404040", "color": "#e0e0e0"})
                            ], width=6)
                        ])
                    ], style={"backgroundColor": "rgb(35,39,43)", "color": "#e0e0e0"})
                ], style={"backgroundColor": "rgb(35,39,43)", "border": "1px solid #404040"})
            ], width=12)
        ], className="mb-4"),
        
        # Main Dashboard - Full Width Graphs
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Metrics Plots", style={"color": "#e0e0e0"}),
                        dbc.Label("Select Metrics:", style={"color": "#e0e0e0", "marginBottom": "10px"}),
                        dcc.Checklist(
                            id="metric-selector",
                            options=[],
                            value=[],
                            inline=False,
                            style={
                                "maxHeight": "150px", 
                                "overflowY": "auto", 
                                "marginBottom": "20px",
                                "color": "#e0e0e0"
                            },
                            inputStyle={"marginRight": "8px"},
                            labelStyle={"display": "block", "marginBottom": "5px", "color": "#e0e0e0"}
                        ),
                        html.Div(id="graph-grid")
                    ], style={"backgroundColor": "rgb(35,39,43)", "color": "#e0e0e0"})
                ], style={"backgroundColor": "rgb(35,39,43)", "border": "1px solid #404040"})
            ], width=12)  # Full width now
        ], className="mb-4"),
        
        # Sector Summaries
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Energy Sector Summary", style={"backgroundColor": "rgb(45,49,53)", "color": "#e0e0e0", "fontWeight": "bold", "borderBottom": "1px solid #404040"}),
                    dbc.CardBody(id="energy-summary", style={"backgroundColor": "rgb(35,39,43)", "color": "#e0e0e0"})
                ], style={"backgroundColor": "rgb(35,39,43)", "border": "1px solid #404040"})
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Science Sector Summary", style={"backgroundColor": "rgb(45,49,53)", "color": "#e0e0e0", "fontWeight": "bold", "borderBottom": "1px solid #404040"}),
                    dbc.CardBody(id="science-summary", style={"backgroundColor": "rgb(35,39,43)", "color": "#e0e0e0"})
                ], style={"backgroundColor": "rgb(35,39,43)", "border": "1px solid #404040"})
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Manufacturing Summary", style={"backgroundColor": "rgb(45,49,53)", "color": "#e0e0e0", "fontWeight": "bold", "borderBottom": "1px solid #404040"}),
                    dbc.CardBody(id="manufacturing-summary", style={"backgroundColor": "rgb(35,39,43)", "color": "#e0e0e0"})
                ], style={"backgroundColor": "rgb(35,39,43)", "border": "1px solid #404040"})
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("System Summary", style={"backgroundColor": "rgb(45,49,53)", "color": "#e0e0e0", "fontWeight": "bold", "borderBottom": "1px solid #404040"}),
                    dbc.CardBody(id="system-summary", style={"backgroundColor": "rgb(35,39,43)", "color": "#e0e0e0"})
                ], style={"backgroundColor": "rgb(35,39,43)", "border": "1px solid #404040"})
            ], width=3)
        ])
        
    ], fluid=True, style={"padding": "20px", "backgroundColor": "rgb(25,25,25)", "minHeight": "100vh"})

    # ---------------------- Callbacks ----------------------

    def _register_callbacks(self):
        # All UI updates happen at the same interval rate (1000ms)
        @self.app.callback(
            [Output("energy-summary", "children"),
             Output("science-summary", "children"), 
             Output("manufacturing-summary", "children"),  # Add this line
             Output("system-summary", "children"),
             Output("status-display", "children")],
            [Input("interval-component", "n_intervals")]
        )
        def update_dashboard(n):
            # Get time series summary data directly from logs (no world system needed)
            sector_tables = self.build_sector_summary_tables()
            
            # For status only, we need the world system data
            ws = self.get_world_system_data()
            if not ws:
                empty = html.Div("No data", className="text-secondary text-center")
                return empty, empty, empty, empty, "Status: No data"
            
            # Status from world system
            latest_state = ws.get("latest_state", {})
            sim_status = latest_state.get("simulation_status", {})
            is_running = sim_status.get("is_running", False)
            is_paused = sim_status.get("is_paused", False)
            step = latest_state.get("step", 0)
            
            if is_running and not is_paused:
                status = f"🟢 Running - Step {step}"
            elif is_running and is_paused:
                status = f"🟡 Paused - Step {step}"
            else:
                status = f"⚪ Stopped - Step {step}"
            
            return (sector_tables["energy"], 
                   sector_tables["science"], 
                   sector_tables["manufacturing"],  # Add this line
                   sector_tables["system"],
                   status)

        # Metric options - ONLY update once at startup, then use no_update
        @self.app.callback(
            Output("metric-selector", "options"), 
            [Input("interval-component", "n_intervals")], 
            prevent_initial_call=False
        )
        def update_metric_options(n):
            # Only update options on first few intervals to avoid constant layout changes
            if n > 3:  
                return dash.no_update
                
            df = self.fetch_latest_logs()
            if df is not None and not df.empty:
                # Get numeric columns excluding meta fields
                numeric_cols = []
                for col in df.columns:
                    if col not in ['step', 'timestamp', 'experiment_id']:
                        if pd.api.types.is_numeric_dtype(df[col]):
                            numeric_cols.append(col)                
                options = [{"label": col.replace("_", " ").title(), "value": col} for col in numeric_cols]
                return options
            else:
                print("❌ No data available for metrics")
                return []

        # Initialize metrics selection ONCE
        @self.app.callback(
            Output("metric-selector", "value"), 
            [Input("metric-selector", "options")], 
                [State("metric-selector", "value")], 
                prevent_initial_call=True
            )
        def initialize_metrics_once(options, current_value):
            # Only set initial values if none are selected
            if not current_value and options:
                key_metrics = []
                available_values = [opt["value"] for opt in options]
                
                # Prioritize these metrics if available (no prefixes now)
                preferred = ["daylight", "science_generated", "total_power_supply_kW", "total_charge_level_kWh", "operational_rovers"]
                for metric in preferred:
                    if metric in available_values:
                        key_metrics.append(metric)
                
                # Fill up to 4 metrics
                for opt in options:
                    if len(key_metrics) >= 4:
                        break
                    if opt["value"] not in key_metrics:
                        key_metrics.append(opt["value"])
                
                return key_metrics[:4]
            return current_value

        # Graph grid - ONLY update content when metrics change or new data arrives
        @self.app.callback(
            Output("graph-grid", "children"), 
            [Input("metric-selector", "value"), Input("interval-component", "n_intervals")], 
            prevent_initial_call=False
        )
        def update_graph_grid(selected_metrics, n):
            if not selected_metrics:
                return html.Div("Select metrics to display graphs.", className="text-secondary text-center")
            
            df = self.fetch_latest_logs()
            if df is None or df.empty:
                return html.Div("No data available for plotting.", className="text-secondary text-center")
            
            return self.build_graph_grid(df, selected_metrics)

        # Control buttons - ONLY respond to actual clicks, not interval updates
        @self.app.callback(
            Output("btn-start-continuous", "disabled"),
            [Input("btn-start-continuous", "n_clicks"),
            Input("btn-start-limited", "n_clicks"),
            Input("btn-pause", "n_clicks"),
            Input("btn-resume", "n_clicks"),
            Input("btn-stop", "n_clicks"),
            Input("step-delay", "value"),
            Input("max-steps", "value")],
            prevent_initial_call=True
        )
        def handle_controls(start_cont, start_lim, pause, resume, stop, delay, max_steps):
            import dash
            ctx = dash.callback_context
            if not ctx.triggered:
                return dash.no_update  # Use no_update instead of False
                
            button_id = ctx.triggered[0]["prop_id"].split(".")[0]
            
            commands = {
                "btn-start-continuous": "start_continuous",
                "btn-start-limited": "start_limited", 
                "btn-pause": "pause",
                "btn-resume": "resume",
                "btn-stop": "stop",
                "step-delay": "set_delay"
            }
            
            if button_id in commands:
                action = commands[button_id]
                kwargs = {"delay": delay} if action == "set_delay" else {}
                if action == "start_limited":
                    kwargs["max_steps"] = max_steps
                
                self.send_command(action, **kwargs)
            
            return dash.no_update  # Don't change button state

    # ---------------------- Command Sending ----------------------

    def send_command(self, action, **kwargs):
        """Send command to simulation."""
        collection = "startup_commands" if action in ["start_continuous", "start_limited"] else "runtime_commands"
        command = {
            "action": action,
            "timestamp": time.time(),
            "experiment_id": self.exp_id,
            **kwargs
        }
        
        try:
            self.db.db[collection].insert_one(command)
        except Exception as e:
            print(f"❌ Command error: {e}")

    def run(self):
        self.app.run(debug=True, host='0.0.0.0', port=8050)


if __name__ == "__main__":
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "exp_001"
    db = ProximaDB()
    ProximaUI(db, experiment_id=exp_id).run()
