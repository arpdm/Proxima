import dash
import sys
import plotly.graph_objs as go
import pandas as pd
import dash_bootstrap_components as dbc
import dash_ag_grid as dag

from dash import dcc, html
from dash.dependencies import Input, Output, State  # Add State here
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
            "Science Generated": safe_numeric(ws_metrics.get("total_science_cumulative")),
        })
        
        return flattened

    # ---------------------- UI Component Builders ----------------------

    def build_component_status_tables(self, ws):
        """
        Build tables for all component types dynamically from latest state.
        """
        latest_state = ws.get("latest_state", {})
        microgrid = latest_state.get("microgrid", {})
        
        # Define component configurations - completely generic
        component_configs = {
            "generators": {
                "data_source": microgrid.get("generator_status", []),
                "id_prefix": "Gen",
            },
            "storages": {
                "data_source": microgrid.get("storage_status", []),
                "id_prefix": "Storage", 
            },
            "rovers": {
                "data_source": latest_state.get("science_rovers", []),
                "id_prefix": "Rover",
            }
        }
        
        tables = {}
        
        for component_type, config in component_configs.items():
            table_data = self._build_generic_component_table(
                config["data_source"], 
                config["id_prefix"]
            )
            
            tables[component_type] = (
                self.generate_aggrid(table_data, height=300) 
                if table_data 
                else html.Div(f"No {component_type}")
            )
        
        return tables

    def _build_generic_component_table(self, components, id_prefix):
        """
        Build a table from any list of component dictionaries - completely generic.
        """
        if not components:
            return []
        
        table_data = []
        
        for i, component in enumerate(components):
            if not isinstance(component, dict):
                continue
                
            # Start with just the ID
            row = {"ID": f"{id_prefix}-{i+1}"}
            
            # Add ALL fields dynamically without any special handling
            for key, value in component.items():
                # Format the field name: snake_case -> Title Case
                formatted_key = key.replace("_", " ").title()
                formatted_value = self._format_value(value)
                
                row[formatted_key] = formatted_value
            
            table_data.append(row)
        
        return table_data

    def _format_value(self, value):
        """
        Generic value formatting without field-specific knowledge.
        """
        if value is None:
            return "N/A"
        
        # Handle numeric values
        if isinstance(value, float):
            # Auto-detect percentages (values between 0-1)
            if 0 <= value <= 1:
                return f"{value * 100:.1f}%"
            else:
                return round(value, 2)
        
        # Everything else as-is
        return str(value)

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
        Generate an AG Grid table with responsive column sizing.
        """
        if not data:
            return html.Div("No data available.")
        
        # Configure grid options
        grid_options = {}
        style = {}
        
        if auto_height:
            grid_options = {"domLayout": "autoHeight"}
        else:
            style = {"height": f"{height}px"}
        
        # Create responsive column definitions
        column_defs = []
        for key in data[0].keys():
            # Calculate estimated width based on content AND header
            max_content_length = max(
                len(str(key)),  # Header length
                max(len(str(row.get(key, ""))) for row in data)  # Max content length
            )
            
            # Ensure minimum width accommodates the header text
            header_width = len(str(key)) * 12  # ~12px per character for header
            content_width = max_content_length * 8  # ~8px per character for content
            min_width = max(100, header_width, content_width)  # At least 100px minimum
            
            column_defs.append({
                "field": key,
                "headerName": key,
                "minWidth": min_width,
                "width": min_width,  # Set initial width
                "flex": 1,  # Allow flex growth
                "autoHeight": True,
                "wrapText": True,
                "cellStyle": {"whiteSpace": "normal"},
                "sortable": True,
                "resizable": True,
                # Header-specific styling
                "headerClass": "wrap-header",
            })
        
        return dag.AgGrid(
            className="ag-theme-quartz-dark",
            columnDefs=column_defs,
            rowData=data,
            style=style,
            dashGridOptions={
                **grid_options,
                "suppressColumnVirtualisation": True,
                "autoSizeStrategy": {
                    "type": "fitGridWidth",
                    "defaultMinWidth": 100,
                },
                # Enable header height auto-sizing
                "autoHeaderHeight": True,
                "wrapHeaderText": True,
            },
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
                    /* AG Grid header text wrapping */
                    .ag-theme-quartz-dark .ag-header-cell-text {
                        white-space: normal !important;
                        word-wrap: break-word !important;
                        line-height: 1.2 !important;
                    }
                    .ag-theme-quartz-dark .ag-header-cell {
                        height: auto !important;
                        min-height: 40px !important;
                    }
                    .wrap-header {
                        white-space: normal !important;
                        word-wrap: break-word !important;
                    }
                    /* Vertical metric selector styling */
                    .metric-checklist-vertical {
                        max-height: 200px;
                        overflow-y: auto;
                        border: 1px solid #444;
                        border-radius: 8px;
                        padding: 10px;
                        background-color: #2a2e33;
                    }
                    .metric-checklist-vertical .form-check {
                        margin-bottom: 8px !important;
                    }
                    .metric-checklist-vertical .form-check-input {
                        background-color: #404040 !important;
                        border-color: #666 !important;
                    }
                    .metric-checklist-vertical .form-check-input:checked {
                        background-color: #0d6efd !important;
                        border-color: #0d6efd !important;
                    }
                    .metric-checklist-vertical .form-check-label {
                        color: #e0e0e0 !important;
                        font-size: 0.9rem;
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
                            # Control panel for selecting metrics - VERTICAL LAYOUT
                            html.Div([
                                html.H5("Select Metrics to Plot:", className="text-info mb-2"),
                                dcc.Checklist(
                                    id="metric-selector",
                                    options=[],  # Will be populated by callback
                                    value=[],
                                    inline=False,  # Changed to vertical
                                    className="metric-checklist-vertical",
                                    style={"marginBottom": "20px"}
                                ),
                                html.Hr(style={"borderColor": "#444"}),
                            ]),
                            # Graph grid container
                            html.Div(id="graph-grid"),
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
                    "generator-status-panel",
                    "storage-status-panel",
                    "rover-status-panel",
                ]
            ] + [
                Output("metric-selector", "options"),
            ],
            [Input("interval-component", "n_intervals")],
            [State("metric-selector", "value")],
            prevent_initial_call=False
        )
        def update_dashboard(n, current_selection):
            """
            Update all dashboard panels on interval - CONTENT ONLY.
            """
            df = self.fetch_latest_logs()
            exp = self.fetch_document("experiments", self.exp_id)
            ws = self.fetch_document("world_systems", exp["world_system_id"]) if exp else None
            env = self.fetch_document("environments", ws["environment_id"]) if ws else None

            # Component summary
            comp_summary = self.extract_component_counts(ws) if ws else {}
            comp_table = self.generate_aggrid([{"Component": k, "Count": v} for k, v in comp_summary.items()], auto_height=True)

            # Latest state panel
            latest_state_data = self.extract_latest_state(ws) if ws else {}
            latest_state_table = self.generate_aggrid(
                [{"Metric": k, "Value": v} for k, v in latest_state_data.items()], 
                auto_height=True
            )

            # Component status tables
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

            # Get available fields for metric selector
            if df is not None and not df.empty:
                available_fields = [col for col in df.columns if col not in ['step', 'timestamp', 'experiment_id'] 
                                   and pd.api.types.is_numeric_dtype(df[col])]
                metric_options = [{"label": field.replace("_", " ").title(), "value": field} 
                                 for field in available_fields]
            else:
                metric_options = []

            return (
                exp_table,
                env_table,
                comp_table,
                latest_state_table,
                status_tables["generators"],
                status_tables["storages"],
                status_tables["rovers"],
                metric_options,
            )

        @self.app.callback(
            Output("metric-selector", "value"),
            [Input("metric-selector", "options")],
            [State("metric-selector", "value")],
            prevent_initial_call=True
        )
        def initialize_metrics_once(options, current_value):
            """
            Only set initial values if no selection exists yet.
            """
            # If user already has selections, keep them
            if current_value:
                return current_value
                
            # Only set defaults if no current selection
            if not options:
                return []
            return [opt["value"] for opt in options[:4]]

        @self.app.callback(
            Output("graph-grid", "children"),
            [Input("metric-selector", "value"), Input("interval-component", "n_intervals")]
        )
        def update_graph_grid(selected_metrics, n):
            """
            Update the graph grid based on selected metrics.
            """
            df = self.fetch_latest_logs()
            return self.build_graph_grid(df, selected_metrics or [])

    def build_interactive_graphs(self, df, available_fields=None):
        """
        Build interactive graph selection and grid layout.
        """
        if df is None or df.empty:
            return html.Div("No log data available.")
        
        # Get available numeric fields from the dataframe
        if available_fields is None:
            available_fields = [col for col in df.columns if col not in ['step', 'timestamp', 'experiment_id'] 
                               and pd.api.types.is_numeric_dtype(df[col])]
        
        # Default selected fields (first 4 available)
        default_selected = available_fields[:4] if len(available_fields) >= 4 else available_fields
        
        return html.Div([
            # Control panel for selecting metrics
            html.Div([
                html.H5("Select Metrics to Plot:", className="text-info mb-2"),
                dcc.Checklist(
                    id="metric-selector",
                    options=[{"label": field.replace("_", " ").title(), "value": field} 
                            for field in available_fields],
                    value=default_selected,
                    inline=True,
                    className="metric-checklist",
                    style={"color": "#e0e0e0", "marginBottom": "20px"}
                ),
                html.Hr(style={"borderColor": "#444"}),
            ]),
            
            # Graph grid container
            html.Div(id="graph-grid"),
        ])

    def build_graph_grid(self, df, selected_metrics):
        """
        Build a responsive grid of graphs based on selected metrics.
        """
        if not selected_metrics or df is None or df.empty:
            return html.Div("Select metrics to display graphs.", className="text-secondary text-center")
        
        # Calculate tick interval for all graphs
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
        
        # Color palette for different metrics
        colors = ["#00cc96", "#ab63fa", "#ff6692", "#19d3f3", "#ff9f40", "#ffff00", 
                  "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2"]
        
        # Create graph tiles
        graph_tiles = []
        for i, metric in enumerate(selected_metrics):
            if metric not in df.columns:
                continue
                
            color = colors[i % len(colors)]
            label = metric.replace("_", " ").title()
            
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["step"],
                    y=df[metric],
                    mode="lines+markers",
                    name=label,
                    line=dict(color=color, width=2),
                    marker=dict(size=3, color=color),
                )
            )
            
            fig.update_layout(
                title=dict(
                    text=label,
                    font=dict(size=14, color="#e0e0e0")
                ),
                xaxis=dict(
                    title="Step",
                    color="#aaaaaa",
                    dtick=dtick,
                    gridcolor="#404040",
                    showgrid=True,
                ),
                yaxis=dict(
                    title=label,
                    color="#aaaaaa",
                    gridcolor="#404040",
                    showgrid=True,
                ),
                template="plotly_dark",
                paper_bgcolor="rgb(35,39,43)",
                plot_bgcolor="rgb(25,25,25)",
                font=dict(color="#e0e0e0", size=10),
                margin=dict(l=50, r=20, t=40, b=40),
                showlegend=False,
                hovermode="x unified",
            )
            
            # Create responsive tile
            graph_tile = dbc.Col([
                dcc.Graph(
                    figure=fig,
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                    },
                    style={"height": "300px"}
                )
            ], width=6, lg=6, xl=4, className="mb-3")  # Responsive: 2 per row on medium, 3 on large
            
            graph_tiles.append(graph_tile)
        
        return dbc.Row(graph_tiles)

    def run(self):
        """
        Run the Dash app.
        """
        self.app.run(debug=True)


if __name__ == "__main__":
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "exp_001"
    db = ProximaDB()
    ProximaUI(db, experiment_id=exp_id).run()
