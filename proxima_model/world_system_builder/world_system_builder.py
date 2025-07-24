"""
world_system_builder.py

Builds a world system configuration for the Proxima simulation engine.
Handles environment setup, experiment timing, and agent/component instantiation
based on active_components and component_templates from MongoDB.
"""

from data_engine.proxima_db_engine import ProximaDB


def extract_environment_config(environment: dict, experiment: dict) -> dict:
    return {
        "sim_time": experiment["simulation_time_stapes"],
        "delta_t": experiment["time_step_duration_hours"],
        "day_hours": environment["day_hours"],
        "night_hours": environment["night_hours"],
        "p_need": 2.0,  # baseline power need
    }


def process_component(template: dict, quantity: int, config: dict, agents_config: dict, template_id: str):
    subtype = template.get("subtype", "").lower()
    cfg = template.get("config", {})

    # MICROGRID
    if "microgrid" in subtype:
        config["microgrid"] = cfg

    # VSAT / SOLAR
    elif "solar" in subtype or "vsat" in template_id or "vsat" in subtype:
        config["vsat_count"] = quantity
        config["p_vsat_max"] = cfg.get("power_capacity_kwh", 0.0)

    # FUEL CELLS
    elif "fuel_cell" in subtype or "power_gen_h2_o2" in subtype:
        config["fuel_cell_count"] = quantity
        config["p_fuel_max"] = cfg.get("power_capacity_kwh", 0.0)

    # BATTERY STORAGE
    elif "storage" in subtype or "battery" in template_id:
        config["battery_count"] = quantity
        config["b_min"] = cfg.get("min_operational_cap_kwh", 0.0)
        config["b_max"] = cfg.get("max_operational_cap_kwh", 0.0)
        config["initial_battery"] = cfg.get("initial_charge_kwh", 0.0)

    # SCIENCE ROVERS
    elif "science_rover" in subtype:
        agents_config.setdefault("science_rovers", [])
        for i in range(quantity):
            agents_config["science_rovers"].append(
                {
                    "id": f"{template_id}_{i}",
                    "type": "science_rover",
                    "power_usage_kWh": cfg.get("power_usage_kWh", 0.2),
                    "science_generation": cfg.get("science_generation", 0.5),
                    "battery_capacity_kWh": cfg.get("battery_capacity_kWh", 20.0),
                    "current_battery_kWh": cfg.get("battery_capacity_kWh", 20.0),
                    "science_buffer": 0.0,
                    "status": "idle",
                    "location": (0, 0),
                }
            )


def build_world_system_config(world_system_id: str, experiment_id: str, db: ProximaDB) -> dict:
    world_system = db.find_by_id("world_systems", world_system_id)
    experiment = db.find_by_id("experiments", experiment_id)
    environment = db.find_by_id("environments", world_system["environment_id"])
    component_templates = {c["_id"]: c for c in db.list_all("component_templates")}

    config = extract_environment_config(environment, experiment)
    agents_config = {}

    for component in world_system.get("active_components", []):
        template_id = component["template_id"]
        quantity = component.get("quantity", 1)
        template = component_templates.get(template_id)

        if not template:
            continue

        process_component(template, quantity, config, agents_config, template_id)

        # Handle template-defined children (optional)
        for child in template.get("children", []):
            child_template = component_templates.get(child["template_id"])
            child_quantity = child.get("quantity", 1)

            if child_template:
                process_component(child_template, child_quantity, config, agents_config, child_template["_id"])

    config["agents_config"] = agents_config
    return config
