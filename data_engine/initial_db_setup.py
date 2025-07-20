from data_engine.proxima_db_engine import ProximaDB


def setup_environment(db):
    db.environments.insert_one({"_id": "env_moon", "name": "Moon", "gravity": 1.62, "resources": ["helium3", "solar"]})

def main():
    print("Setting up Proxima Database Schema")

    proxima_db = ProximaDB()
    # proxima_db.create_component_template(
    #     comp_id="comp_bat",
    #     name="Battery",
    #     type="Energy",
    #     subtype="energy_storage",
    #     sphere="Technosphere",
    #     config={"min_operational_cap_kwh":30, "min_operational_cap_kwh":3, "initial_charge_kwh":20},
    # )

    # proxima_db.create_component_template(
    #     comp_id="comp_microgrid",
    #     name="Lunar Microgrid",
    #     type="Energy",
    #     subtype="Microgrid",
    #     sphere="technosphere",
    #     config=None,
    #     children=[
    #         {"template_id": "comp_vsat", "quantity": 3},
    #         {"template_id": "comp_fuelcell", "quantity": 5},
    #         {"template_id": "comp_bat", "quantity": 3}
    #     ]
    # )

    # # # Instantiate World System

    # active_components = [{
    #     "template_id": "comp_microgrid",
    #     "instance_id": "microgrid_001",
    #     "state": {
    #         "output_kW": 88,
    #         "efficiency": 0.92
    #     }
    # }]

    # proxima_db.create_world_system("ws_beta_1", "World System Beta 1", "env_moon", active_components, {"infospher":{"produced_knowledge":0}}) 
    # proxima_db.create_experiment("exp_001", sim_time_steps=10, time_step_duration_hours=1.0,world_system_id="ws_beta_1",experiment_type="base run")
    # print(proxima_db.list_all("experiments"))


    proxima_db.export_all_collections_to_json("log_files")

if __name__ == "__main__":
    main()