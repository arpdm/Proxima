import os
from visualizer_engine.proxima_ui_engine import ProximaUI
from data_engine.proxima_db_engine import ProximaDB


def create_app():
    """Create and configure the Proxima UI application"""

    # Get configuration from environment variables
    exp_id = os.environ.get("EXPERIMENT_ID", "exp_001")
    mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    update_rate_ms = int(os.environ.get("UPDATE_RATE_MS", "1000"))
    update_cycles = int(os.environ.get("UPDATE_CYCLES", "1"))
    read_only = os.environ.get("READ_ONLY", "True").lower() == "true"
    time_series_limit = int(os.environ.get("TIME_SERIES_LIMIT", "100"))

    db = ProximaDB(mongo_uri, local=False)
    ui = ProximaUI(
        db,
        experiment_id=exp_id,
        update_rate_ms=update_rate_ms,
        update_cycles=update_cycles,
        read_only=read_only,
        ts_data_count=time_series_limit,
    )

    # Return the Dash app's Flask server
    return ui.app.server


# For Cloud Run
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=True)
