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
            {"field": "Total Power Supplied (kWh)", "label": "Power Supplied", "color": "green"},
            {"field": "Total SoC (%)", "label": "State of Charge", "color": "blue"},
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

    def fetch_latest_logs(self, limit=1000):
        """
        Fetch the latest simulation logs as a DataFrame.
        """
        return pd.DataFrame(
            self.fetch_collection(
                "logs_simulation", {"experiment_id": self.exp_id}, sort=("timestamp", -1), limit=limit
            )
        )

    # ---------------------- Data Processing Methods ----------------------

    def extract_component_counts(self, ws):
        """
        Extract and count all components (including children) from a world system document.
        """
        summary = {}
        component_templates = {c["_id"]: c for c in self.db.db.component_templates.find({})}

        for comp in ws.get("active_components", []):
            tid = comp.get("template_id")
            quantity = comp.get("quantity", 1)
            if tid:
                summary[tid] = summary.get(tid, 0) + quantity
                # Expand children if they exist
                template = component_templates.get(tid)
                if template:
                    for child in template.get("children", []):
                        child_id = child.get("template_id")
                        child_quantity = child.get("quantity", 1)
                        if child_id:
                            summary[child_id] = summary.get(child_id, 0) + child_quantity
        return summary

    # ---------------------- UI Component Builders ----------------------

    def build_rover_states_table(self, df):
        """
        Build a table showing the latest rover states.
        """
        if df.empty or "rover_states" not in df.columns:
            return html.Div("No rover state data available.")

        # Grab the most recent non-empty rover_states entry
        for _, row in df.sort_values("step", ascending=False).iterrows():
            rover_states = row.get("rover_states", [])
            if rover_states:
                break
        else:
            return html.Div("No rover states found.")

        display_rows = [
            {
                "ID": rover["id"],
                "Battery (kWh)": round(rover["battery_kWh"], 2),
                "Science": round(rover["science_buffer"], 2),
                "Status": rover["status"],
            }
            for rover in rover_states
        ]

        return self.generate_aggrid(display_rows, height=400)

    def build_graphs(self, df, viz_config):
        """
        Build a list of Plotly graphs based on the visualization config.
        """
        if df is None or df.empty:
            return [html.Div("No log data available.")]

        graphs = []
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
                xaxis=dict(color="#aaaaaa", tickmode="linear"),
                yaxis=dict(color="#aaaaaa"),
            )
            graphs.append(dcc.Graph(figure=fig))
        return graphs

    def generate_aggrid(self, data, height=250):
        """
        Generate an AG Grid table for the given data.
        """
        if not data:
            return html.Div("No data available.")
        return dag.AgGrid(
            className="ag-theme-quartz-dark",
            columnDefs=[{"field": k} for k in data[0].keys()],
            rowData=data,
            columnSize="sizeToFit",
            style={"height": f"{height}px"},
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
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(html.Div(id="experiment-info", className="proxima-card"), width=6),
                                        dbc.Col(html.Div(id="environment-info", className="proxima-card"), width=6),
                                    ]
                                ),
                                html.Div(id="component-summary", className="proxima-card"),
                                html.Div(
                                    [
                                        html.H4("Policy List", className="text-info mb-2"),
                                        html.Div(id="policy-list"),
                                    ],
                                    className="proxima-card",
                                ),
                                html.Div(
                                    [
                                        html.H4("Goal Table", className="text-info mb-2"),
                                        html.Div(id="goal-table"),
                                    ],
                                    className="proxima-card",
                                ),
                                html.Div(
                                    [
                                        html.H4("Live Metric Snapshot", className="text-info mb-2"),
                                        html.Div(id="live-values-panel"),
                                    ],
                                    className="proxima-card",
                                ),
                                html.Div(
                                    [
                                        html.H4("Graphs", className="text-info mb-2"),
                                        html.Div(id="graph-container"),
                                    ],
                                    className="proxima-card",
                                ),
                            ],
                            width=9,
                            style={"paddingRight": "1rem"},
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.H4("Science Rover Status", className="text-center text-secondary mb-3"),
                                        html.Div(
                                            id="rover-status-panel", style={"overflowY": "auto", "maxHeight": "90vh"}
                                        ),
                                    ],
                                    className="proxima-card",
                                ),
                            ],
                            width=3,
                        ),
                    ]
                ),
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
                    "policy-list",
                    "goal-table",
                    "graph-container",
                    "live-values-panel",
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
            goals = self.fetch_collection("goals")
            policies = self.fetch_collection("policies")

            comp_summary = self.extract_component_counts(ws) if ws else {}
            comp_table = self.generate_aggrid([{"Component": k, "Count": v} for k, v in comp_summary.items()])

            goal_table = (
                self.generate_aggrid(pd.DataFrame(goals).to_dict("records")) if goals else html.Div("No goals defined.")
            )
            policy_list = (
                html.Ul([html.Li(f"{p['name']}: {p.get('trigger_condition')}") for p in policies])
                if policies
                else html.Div("No policies.")
            )
            exp_table = self.generate_aggrid([{k: v for k, v in exp.items() if k != "visualization_config"}])
            env_table = (
                self.generate_aggrid(
                    [{k: v if isinstance(v, (str, int, float)) else str(v) for k, v in env.items() if k != "_id"}]
                )
                if env
                else html.Div("No environment.")
            )

            viz_config = exp.get("visualization_config", self.viz_config_default) if exp else []
            graphs = self.build_graphs(df, viz_config)
            latest = df.sort_values("timestamp").iloc[-1] if not df.empty else {}
            live_data = [{"Metric": c["label"], "Latest Value": latest.get(c["field"], "N/A")} for c in viz_config]
            latest_table = self.generate_aggrid(live_data)
            rover_table = self.build_rover_states_table(df)

            return (
                exp_table,
                env_table,
                comp_table,
                policy_list,
                goal_table,
                html.Div(graphs),
                latest_table,
                rover_table,
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
