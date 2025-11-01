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

### General Configurability 

**proxima_runner.py** : 

1. Logger Config
2. Command Line Arguments

### Adding a Peformance Goal/Policy 

1. Add a new Performance Goal entry in "goals" collection of the database

```json 
{
  "_id": "WS-PG-004",
  "name": "Increase Science Production Rate",
  "type": "performance_goal",
  "metric_id": "SCI-PROD-RATE",
  "direction": "maximize",
  "goal_type": "growth_rate",
  "growth_factor": 5.0,
  "time_period": 500,
  "weight": 0.8
}
```

2. Ensure the goal type has a dedicated function in the ```evaluation_engine.py```
3. Add contribution value to the metric ```metric_id``` by the Sector that contributes to the metric mapped to the goal. The contribution value is used to sum up the contribution and to the performance metric which then is evaluated against the goal setpoints to see how the world system is doing.   ```metric_map['SCI-PROD-RATE'] = self.step_science_generated```
4. Add appropriate policy to the ```Policy_Engine`` for the corresponding sector file. Use the '''policy_protocol.py``` for the protocol so that policy engine can apply the policy dynamically.
5. Add the policy class to the ```init``` function of the ```policy_engine.py```
6. In ```ws_beta_1``` add the metric contribution for each sector that applies
```json
   "metric_contribution": [
      {
         "metric_id": "IND-DUST-COV",
         "contribution_type": "predefined",
         "contribution_value": 0.005
      },
      {
         "metric_id": "SCI-PROD-RATE",
         "contribution_type": "science_gen",
         "contribution_value": 0
      }
   ]
```
7. Add the goal ID to ```ws_bea_1``` active goals
8. Add the metric tracked to ```env_moon``` 
```json
    {
      "id": "SCI-PROD-RATE",
      "name": "Science Production Rate",
      "type": "positive",
      "unit": "x_factor",
      "notes": "Advances science and thus unlocks new technologies."
    }
```

---

For more details, see the documentation folder.

