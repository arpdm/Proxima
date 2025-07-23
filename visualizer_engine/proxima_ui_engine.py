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
    def __init__(self, db, experiment_id="exp_001"):
        self.db = db
        self.exp_id = experiment_id
        self.viz_config_default = [
            {"field": "Total Power Supplied (kWh)", "label": "Power Supplied", "color": "green"},
            {"field": "Total SoC (%)", "label": "State of Charge", "color": "blue"},
        ]
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.QUARTZ])
        self._setup_layout()
        self._register_callbacks()

    def fetch_collection(self, collection_name, query=None, sort=None, limit=0):
        cursor = self.db.db[collection_name].find(query or {})
        if sort:
            cursor = cursor.sort(*sort)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def fetch_document(self, collection_name, doc_id):
        return self.db.db[collection_name].find_one({"_id": doc_id})

    def fetch_latest_logs(self, limit=1000):
        return pd.DataFrame(
            self.fetch_collection(
                "logs_simulation", {"experiment_id": self.exp_id}, sort=("timestamp", -1), limit=limit
            )
        )

    def extract_component_counts(self, ws):
        summary = {}
        for comp in ws.get("active_components", []):
            tid = comp.get("template_id")
            if tid:
                summary[tid] = summary.get(tid, 0) + 1
                template = self.db.db.component_templates.find_one({"_id": tid})
                for child in template.get("children", []):
                    child_id = child.get("template_id")
                    quantity = child.get("quantity", 1)
                    if child_id:
                        summary[child_id] = summary.get(child_id, 0) + quantity
        return summary

    def build_graphs(self, df, viz_config):
        if df.empty:
            return [html.Div("No log data available.")]
        graphs = []
        for config in viz_config:
            field = config["field"]
            fig = go.Figure()
            for agent_id in df["agent_index"].dropna().unique():
                agent_df = df[df["agent_index"] == agent_id]
                fig.add_trace(
                    go.Scatter(
                        x=agent_df["timestamp"],
                        y=agent_df[field],
                        mode="lines+markers",
                        name=f"{config['label']} (Agent {agent_id})",
                        line=dict(color=config.get("color", "gray")),
                    )
                )
            fig.update_layout(title=config["label"], template="plotly_dark", font=dict(color="#e0e0e0"))
            graphs.append(dcc.Graph(figure=fig))
        return graphs

    def generate_aggrid(self, data, height=250):
        return (
            dag.AgGrid(
                className="ag-theme-quartz-dark",
                columnDefs=[{"field": k} for k in data[0].keys()],
                rowData=data,
                columnSize="sizeToFit",
                style={"height": f"{height}px"},
            )
            if data
            else html.Div("No data available.")
        )

    def _setup_layout(self):
        self.app.layout = dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H1("Proxima", className="text-primary text-center fs-3"),
                                html.H4("Experiment Info Table", className="mt-3 mb-2"),
                                html.Div(id="experiment-info"),
                                html.H4("Environment Info Table", className="mt-3 mb-2"),
                                html.Div(id="environment-info"),
                                html.H4("Component Summary", className="mt-3 mb-2"),
                                html.Div(id="component-summary"),
                                html.H4("Policy List", className="mt-3 mb-2"),
                                html.Div(id="policy-list"),
                                html.H4("Goal Table", className="mt-3 mb-2"),
                                html.Div(id="goal-table"),
                                html.H4("Live Metric Snapshot", className="mt-3 mb-2"),
                                html.Div(id="live-values-panel"),
                                html.H4("Graphs", className="mt-3 mb-2"),
                                html.Div(id="graph-container"),
                                dcc.Interval(id="interval-component", interval=5000, n_intervals=0),
                            ]
                        )
                    ]
                )
            ],
            fluid=True,
            class_name="bg-dark p-4",
        )

    def _register_callbacks(self):
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
                ]
            ],
            [Input("interval-component", "n_intervals")],
        )
        def update_dashboard(n):
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

            return exp_table, env_table, comp_table, policy_list, goal_table, html.Div(graphs), latest_table

    def run(self):
        self.app.run(debug=True)


if __name__ == "__main__":
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "exp_001"
    db = ProximaDB()
    ProximaUI(db, experiment_id=exp_id).run()
