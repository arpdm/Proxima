import dash
import sys
import plotly.graph_objs as go
import pandas as pd
import dash_bootstrap_components as dbc
import dash_ag_grid as dag

from dash import dcc, html
from dash.dependencies import Input, Output
from data_engine.proxima_db_engine import ProximaDB


class ProximaUI:
    """
    ProximaUI: Main dashboard UI engine for the Proxima project.
    Handles layout, data fetching, and live updates.
    """

    def __init__(self, db, experiment_id="exp_001"):
        """
        Initialize the UI with database connection and experiment ID.
        """
        self.db = db
        self.exp_id = experiment_id
        self.viz_config_default = [
            {"field": "total_power_supply_kW", "label": "Power Supplied (kW)", "color": "green"},
            {"field": "total_state_of_charge_%", "label": "State of Charge (%)", "color": "blue"},
            {"field": "science_generated", "label": "Science Generated", "color": "orange"},
        ]
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.QUARTZ])
        self._setup_layout()
        self._register_callbacks()

    # ---------------------- Data Fetching Methods ----------------------

    def fetch_collection(self, collection_name, query=None, sort=None, limit=0):
        """
        Fetch a collection from the database with optional query, sort, and limit.
        """
        cursor = self.db.db[collection_name].find(query or {})
        if sort:
            cursor = cursor.sort(*sort)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def fetch_document(self, collection_name, doc_id):
        """
        Fetch a single document by ID from a collection.
        """
        return self.db.db[collection_name].find_one({"_id": doc_id})

    def fetch_latest_logs(self, limit=50):
        """
        Fetch the latest simulation logs as a DataFrame.
        """
        logs = self.fetch_collection(
            "logs_simulation", {"experiment_id": self.exp_id}, sort=("timestamp", -1), limit=limit
        )
        if not logs:
            return pd.DataFrame()
        
        # Flatten nested agent states for easier analysis
        flattened_logs = []
        for log in logs:
            flat_log = {
                "step": log.get("step", 0),
                "timestamp": log.get("timestamp"),
                "experiment_id": log.get("experiment_id"),
            }
            
            # Extract model-level metrics
            for key, value in log.items():
                if key not in ["agent_states", "step", "timestamp", "experiment_id"]:
                    flat_log[key] = value
            
            # Extract agent state metrics (microgrid, rovers, etc.)
            for agent_state in log.get("agent_states", []):
                if isinstance(agent_state, dict):
                    for key, value in agent_state.items():
                        if isinstance(value, (int, float, str)):
                            flat_log[key] = value
            
            flattened_logs.append(flat_log)
        
        return pd.DataFrame(flattened_logs)

    # ---------------------- Data Processing Methods ----------------------

    def extract_component_counts(self, ws):
        """
        Extract and count all components from a world system document.
        """
        summary = {}
        
        for domain_dict in ws.get("active_components", []):
            for domain, components in domain_dict.items():
                for comp in components:
                    template_id = comp.get("template_id")
                    subtype = comp.get("subtype", "N/A")
                    quantity = comp.get("quantity", 1)
                    
                    # Create a descriptive key
                    key = f"{template_id} ({subtype})" if subtype and subtype != "N/A" else template_id
                    summary[key] = summary.get(key, 0) + quantity
        
        return summary

    def extract_latest_state(self, ws):
        """
        Extract the latest state snapshot from world system.
        """
        latest_state = ws.get("latest_state", {})
        if not latest_state:
            return {}
        
        # Flatten the state for display
        flattened = {
            "Step": latest_state.get("step", 0),  # Use 0 instead of "N/A"
        }
        
        # Microgrid metrics
        microgrid = latest_state.get("microgrid", {})
        if microgrid:
            # Safely handle numeric values - return 0 for invalid data
            def safe_numeric(value, default=0):
                try:
                    return round(float(value), 2) if value is not None else default
                except (ValueError, TypeError):
                    return default
            
            # Handle State of Charge as percentage
            soc_raw = microgrid.get('total_state_of_charge_%', 0)
            soc_percent = safe_numeric(soc_raw * 100) if soc_raw is not None else 0
            
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
            "Science Generated": safe_numeric(ws_metrics.get("total_science_cumulative")),  # Keep as number
        })
        
        return flattened

    # ---------------------- UI Component Builders ----------------------

    def build_component_status_tables(self, ws):
        """
        Build tables for generator and storage status from latest state.
        """
        latest_state = ws.get("latest_state", {})
        microgrid = latest_state.get("microgrid", {})
        
        # Generator status table
        generators = microgrid.get("generator_status", [])
        gen_table_data = []
        for i, gen in enumerate(generators):
            gen_table_data.append({
                "ID": f"Gen-{i+1}",
                "Type": gen.get("subtype", "Unknown"),
                "Power (kWh)": round(gen.get("generated_power_kWh", 0), 2),
                "Efficiency": f"{gen.get('efficiency', 0) * 100:.0f}%",
                "Availability": f"{gen.get('availability', 0) * 100:.0f}%",
                "Capacity": gen.get("capacity", "N/A"),
            })
        
        # Storage status table
        storages = microgrid.get("storage_status", [])
        storage_table_data = []
        for i, storage in enumerate(storages):
            storage_table_data.append({
                "ID": f"Storage-{i+1}",
                "Type": storage.get("subtype", "Unknown"),
                "Charge (kWh)": round(storage.get("charge_level", 0), 2),
                "SoC (%)": f"{storage.get('state_of_charge', 0) * 100:.1f}%",
                "Capacity": storage.get("capacity", "N/A"),
            })
        
        # Science rovers table
        rovers = latest_state.get("science_rovers", [])
        rover_table_data = []
        for i, rover in enumerate(rovers):
            rover_table_data.append({
                "ID": f"Rover-{i+1}",
                "Status": rover.get("status", "Unknown"),
                "Battery (kWh)": round(rover.get("battery_kWh", 0), 2),
                "Science Buffer": round(rover.get("science_buffer", 0), 2),
            })
        
        return {
            "generators": self.generate_aggrid(gen_table_data, height=300) if gen_table_data else html.Div("No generators"),
            "storages": self.generate_aggrid(storage_table_data, height=300) if storage_table_data else html.Div("No storage units"),
            "rovers": self.generate_aggrid(rover_table_data, height=300) if rover_table_data else html.Div("No rovers"),
        }

    def build_graphs(self, df, viz_config):
        """
        Build a list of Plotly graphs based on the visualization config.
        """
        if df is None or df.empty:
            return [html.Div("No log data available.")]

        graphs = []
        
        # Calculate tick interval based on data size
        if "step" in df.columns and not df.empty:
            step_range = df["step"].max() - df["step"].min()
            if step_range <= 50:
                dtick = 5
            elif step_range <= 200:
                dtick = 10
            elif step_range <= 500:
                dtick = 25
            else:
                dtick = 50
        else:
            dtick = 10
    
        for config in viz_config:
            field = config["field"]
            label = config.get("label", field)
            color = config.get("color", None)
            if field not in df.columns:
                continue  # Skip missing fields

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["step"],
                    y=df[field],
                    mode="lines",
                    name=label,
                    line=dict(color=color) if color else None,
                )
            )
            fig.update_layout(
                title=label,
                xaxis_title="Simulation Step",
                yaxis_title=label,
                template="plotly_dark",
                paper_bgcolor="rgb(20,20,20)",
                plot_bgcolor="rgb(25,25,25)",
                font=dict(color="#e0e0e0"),
                xaxis=dict(
                    color="#aaaaaa", 
                    dtick=dtick,  # Show every dtick steps on x-axis
                ),
                yaxis=dict(color="#aaaaaa"),
            )
            graphs.append(dcc.Graph(figure=fig))
        return graphs

    def generate_aggrid(self, data, height=250, auto_height=False):
        """
        Generate an AG Grid table for the given data.
        """
        if not data:
            return html.Div("No data available.")
        
        # Configure grid options for auto-height
        grid_options = {}
        style = {}
        
        if auto_height:
            # Use dashGridOptions to set domLayout for auto-height
            grid_options = {"domLayout": "autoHeight"}
        else:
            # Use fixed height
            style = {"height": f"{height}px"}
        
        return dag.AgGrid(
            className="ag-theme-quartz-dark",
            columnDefs=[{"field": k} for k in data[0].keys()],
            rowData=data,
            columnSize="sizeToFit",
            style=style,
            dashGridOptions=grid_options,  # Use this instead of domLayout directly
        )

    # ---------------------- Layout & Callbacks ----------------------

    def _setup_layout(self):
        """
        Set up the dashboard layout and dark theme.
        """
        self.app.index_string = """
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>Proxima Dashboard</title>
                {%favicon%}
                {%css%}
                <style>
                    body {
                        background-color: #181a1b !important;
                        color: #e0e0e0 !important;
                    }
                    .proxima-card {
                        background: #23272b;
                        border-radius: 12px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.18);
                        padding: 1.5rem;
                        margin-bottom: 1.5rem;
                    }
                    .proxima-header {
                        letter-spacing: 2px;
                        font-weight: 700;
                    }
                    .full-height-card {
                        background: #23272b;
                        border-radius: 12px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.18);
                        padding: 1.5rem;
                        height: calc(100vh - 200px);
                        overflow-y: auto;
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

        self.app.layout = dbc.Container(
            [
                dcc.Interval(id="interval-component", interval=2000, n_intervals=0),
                html.H1("Proxima", className="text-primary text-center fs-3 mb-4 proxima-header"),
                
                # Top info row
                dbc.Row([
                    dbc.Col(html.Div(id="experiment-info", className="proxima-card"), width=4),
                    dbc.Col(html.Div(id="environment-info", className="proxima-card"), width=4),
                    dbc.Col(html.Div(id="component-summary", className="proxima-card"), width=4),
                ], className="mb-3"),
                
                # Main content row with 3 columns
                dbc.Row([
                    # Graphs column (left)
                    dbc.Col([
                        html.Div([
                            html.H4("Graphs", className="text-info mb-2"),
                            html.Div(id="graph-container"),
                        ], className="proxima-card"),
                    ], width=5, style={"paddingRight": "0.5rem"}),
                    
                    # Status panels column (middle)
                    dbc.Col([
                        html.Div([
                            html.H4("Generator Status", className="text-center text-secondary mb-3"),
                            html.Div(id="generator-status-panel"),
                        ], className="proxima-card"),
                        html.Div([
                            html.H4("Storage Status", className="text-center text-secondary mb-3"),
                            html.Div(id="storage-status-panel"),
                        ], className="proxima-card"),
                        html.Div([
                            html.H4("Rover Status", className="text-center text-secondary mb-3"),
                            html.Div(id="rover-status-panel"),
                        ], className="proxima-card"),
                    ], width=4, style={"paddingLeft": "0.5rem", "paddingRight": "0.5rem"}),
                    
                    # Latest System State column (right) - FULL HEIGHT
                    dbc.Col([
                        html.Div([
                            html.H4("Latest System State", className="text-info mb-3"),
                            html.Div(id="latest-state-panel"),
                        ], className="full-height-card"),
                    ], width=3, style={"paddingLeft": "0.5rem"}),
                ]),
            ],
            fluid=True,
            style={"padding": "2rem", "backgroundColor": "#181a1b", "minHeight": "100vh"},
        )

    def _register_callbacks(self):
        """
        Register all Dash callbacks for live dashboard updates.
        """

        @self.app.callback(
            [
                Output(k, "children")
                for k in [
                    "experiment-info",
                    "environment-info",
                    "component-summary",
                    "latest-state-panel",
                    "graph-container",
                    "generator-status-panel",
                    "storage-status-panel",
                    "rover-status-panel",
                ]
            ],
            [Input("interval-component", "n_intervals")],
        )
        def update_dashboard(n):
            """
            Update all dashboard panels on interval.
            """
            df = self.fetch_latest_logs()
            exp = self.fetch_document("experiments", self.exp_id)
            ws = self.fetch_document("world_systems", exp["world_system_id"]) if exp else None
            env = self.fetch_document("environments", ws["environment_id"]) if ws else None

            # Component summary
            comp_summary = self.extract_component_counts(ws) if ws else {}
            comp_table = self.generate_aggrid([{"Component": k, "Count": v} for k, v in comp_summary.items()], auto_height=True)

            # Latest state panel - USE AUTO HEIGHT (no scrolling)
            latest_state_data = self.extract_latest_state(ws) if ws else {}
            latest_state_table = self.generate_aggrid(
                [{"Metric": k, "Value": v} for k, v in latest_state_data.items()], 
                auto_height=True  # This will show all rows without scrolling
            )

            # Component status tables (keep these with fixed height)
            status_tables = self.build_component_status_tables(ws) if ws else {
                "generators": html.Div("No data"), 
                "storages": html.Div("No data"), 
                "rovers": html.Div("No data")
            }

            # Experiment and environment info
            exp_table = self.generate_aggrid([{k: v for k, v in exp.items() if k != "visualization_config"}]) if exp else html.Div("No experiment")
            env_table = (
                self.generate_aggrid(
                    [{k: v if isinstance(v, (str, int, float)) else str(v) for k, v in env.items() if k != "_id"}]
                )
                if env
                else html.Div("No environment.")
            )

            # Graphs
            viz_config = exp.get("visualization_config", self.viz_config_default) if exp else self.viz_config_default
            graphs = self.build_graphs(df, viz_config)

            return (
                exp_table,
                env_table,
                comp_table,
                html.Div([
                    latest_state_table  # Now auto-height, no scrolling
                ]),
                html.Div(graphs),
                status_tables["generators"],
                status_tables["storages"],
                status_tables["rovers"],
            )

    def run(self):
        """
        Run the Dash app.
        """
        self.app.run(debug=True)


if __name__ == "__main__":
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "exp_001"
    db = ProximaDB()
    ProximaUI(db, experiment_id=exp_id).run()
