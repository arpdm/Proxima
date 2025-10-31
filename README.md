# Proxima

## Running the UI Locally

1. **Install dependencies using Poetry:**
   ```bash
   poetry install
   ```
2. **Mongo DB Database:**

Ensure local MongoDB Database is up and running with specified schemas.

3. **Start the UI:**
   ```bash
   poetry run python visualizer_engine/proxima_ui_engine.py
   ```
   - You can pass the experiment ID as an argument:
     ```bash
     poetry run python visualizer_engine/proxima_ui_engine.py exp_001
     ```

## Running on Google Cloud Run

1. **Configure environment variables:**
   - Edit `.env` or use Google Secret Manager for sensitive values (see `cloud_runner_deploy.sh`).

2. **Deploy using the provided script:**
   ```bash
   ./cloud_runner_deploy.sh
   ```
   - This will build and deploy the service to Google Cloud Run using your source files and configuration.

## Environment Variables

| Variable         | Description                                      | Example Value                          |
|------------------|--------------------------------------------------|----------------------------------------|
| EXPERIMENT_ID    | Experiment identifier                            | exp_001                                |
| MONGODB_URI      | MongoDB connection string                        | mongodb://localhost:27017              |
| UPDATE_RATE_MS   | Dashboard update rate in milliseconds            | 1000                                   |
| UPDATE_CYCLES    | Number of update cycles per interval             | 1                                      |
| READ_ONLY        | Disable simulation controls (True/False)         | False                                  |

## Dependencies

- Python 3.11+
- Poetry (for dependency management)
- Dash
- dash-bootstrap-components
- dash-ag-grid
- Plotly
- pandas
- numpy
- pymongo
- Flask
- mesa
- simpy
- python-dotenv (for local .env support)
- gunicorn (for production/server)

See `pyproject.toml` for the full list.

## Tools and Platforms Used

- **Dash**: Interactive Python web UI framework
- **MongoDB**: Non-relational database for simulation data
- **Google Cloud Run**: Serverless container hosting
- **Docker**: Containerization for deployment
- **Poetry**: Python dependency and packaging manager


## Source Code Configuration Options Per Added Feature

For each world system feature, make sure following configuration sections are updated.

**proxima_runner.py** : 

1. Logger Config
2. Command Line Arguments

---

For more details, see the documentation folder.

