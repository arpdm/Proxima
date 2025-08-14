import os
from visualizer_engine.proxima_ui_engine import ProximaUI
from data_engine.proxima_db_engine import ProximaDB

def create_app():
    """Create and configure the Proxima UI application"""
    # Get configuration from environment variables
    exp_id = os.environ.get('EXPERIMENT_ID', 'exp_001')
    mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
    
    # Initialize database connection
    db = ProximaDB(mongo_uri)
    
    # Create UI instance
    ui = ProximaUI(db, experiment_id=exp_id)
    
    # Return the Dash app's Flask server
    return ui.app.server

# For Cloud Run
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=False)