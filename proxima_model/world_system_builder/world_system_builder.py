"""
world_system_builder.py

This module provides functionality to dynamically build a world system configuration for the Proxima simulation engine.
It fetches relevant documents from the database and constructs a configuration dictionary based on experiment, environment, and component templates.
"""

from data_engine.proxima_db_engine import ProximaDB


def build_world_system_config(world_system_id: str, experiment_id: str, db: ProximaDB):

    # Fetch documents from database
    world_system = db.find_by_id("world_systems", world_system_id)
    experiment = db.find_by_id("experiments", experiment_id)
    environment = db.find_by_id("environments", world_system["environment_id"])
    component_templates = {c["_id"]: c for c in db.list_all("component_templates")}

    # Begin dynamic config
    config = {}
    config["sim_time"] = experiment["simulation_time_stapes"]
    config["delta_t"] = experiment["time_step_duration_hours"]
    config["day_hours"] = environment["day_hours"]
    config["night_hours"] = environment["night_hours"]
    config["p_need"] = 2.0

    for component in world_system.get("active_components", []):
        template_id = component["template_id"]
        template = component_templates.get(template_id)
        if not template:
            continue

        if template.get("children"):
            for child in template["children"]:
                child_template = component_templates.get(child["template_id"])
                quantity = child.get("quantity", 1)

                if not child_template:
                    continue

                subtype = child_template.get("subtype", "").lower()
                config_block = child_template.get("config", {})
                cid = child_template["_id"]

                if "solar" in subtype or "vsat" in cid:
                    config["vsat_count"] = quantity
                    config["p_vsat_max"] = config_block.get(
                        "power_capacity_kwh",
                    )

                elif "power_gen_h2_o2" in subtype:
                    config["fuel_cell_count"] = quantity
                    config["p_fuel_max"] = config_block.get("power_capacity_kwh")

                elif "storage" in subtype or "bat" in cid:
                    config["battery_count"] = quantity
                    config["b_min"] = config_block.get("min_operational_cap_kwh")
                    config["b_max"] = config_block.get("max_operational_cap_kwh")
                    config["initial_battery"] = config_block.get("initial_charge_kwh")

    return config
