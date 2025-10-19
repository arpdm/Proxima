"""
world_system_builder.py

Builds a world system configuration for the Proxima simulation engine.
"""

from data_engine.proxima_db_engine import ProximaDB


def build_world_system_config(world_system_id: str, experiment_id: str, db: ProximaDB) -> dict:
    """Build a world system config from database documents."""
    # Load documents
    world_system = db.find_by_id("world_systems", world_system_id)
    experiment = db.find_by_id("experiments", experiment_id)
    environment = db.find_by_id("environments", world_system["environment_id"])
    component_templates = {c["_id"]: c for c in db.list_all("component_templates")}

    # Build base config
    config = {
        "sim_time": experiment.get("simulation_time_steps", experiment.get("simulation_time_stapes")),
        "delta_t": experiment.get("time_step_duration_hours"),
        "p_need": 2.0,
        "agents_config": {},
        "metrics": environment.get("metrics", []),
        "resources": environment.get("resources", []),
        "dust_decay_per_step": environment.get("dust_decay_per_step", 0.0),
    }

    # Process all components by sector
    active_components = world_system.get("active_components", [])
    if active_components:
        components_dict = active_components[0]  # Assuming single component dict

        # GUIDE: Add per sector
        config["agents_config"]["energy"] = _configure_energy_sector(
            components_dict.get("energy", []), component_templates
        )

        config["agents_config"]["science"] = _configure_science_sector(
            components_dict.get("science", []), component_templates
        )

        config["agents_config"]["manufacturing"] = _configure_manufacturing_sector(
            components_dict.get("manufacturing", []), component_templates, world_system
        )

        config["agents_config"]["equipment_manufacturing"] = _configure_equipment_manufacturing_sector(
            components_dict.get("equipmentManufacturing", []), component_templates
        )

    # Load active goals configuration
    config["goals"] = _configure_goals_system(world_system, db)
    return config


def _configure_energy_sector(energy_components, templates):
    """Configure energy sector components."""
    config = {"generators": [], "storages": []}

    for comp in energy_components:
        template = templates.get(comp["template_id"])
        if not template:
            print(f"Warning: Template {comp['template_id']} not found")
            continue

        component_data = {
            "template_id": comp["template_id"],
            "subtype": comp.get("subtype"),
            "config": {**template.get("config", {}), **comp.get("config", {})},
            "quantity": comp.get("quantity", 1),
        }

        comp_type = template.get("type", "").lower()
        if comp_type == "power_generator":
            config["generators"].append(component_data)
        elif comp_type == "power_storage":
            config["storages"].append(component_data)

    print(f"Configured energy sector: {len(config['generators'])} generators, {len(config['storages'])} storages")
    return config


def _configure_science_sector(science_components, templates):
    """Configure science sector components."""
    config = {"science_rovers": []}
    for comp in science_components:
        template = templates.get(comp["template_id"])
        if not template:
            continue
        quantity = int(comp.get("quantity", 1))
        rover_cfg = {
            "template_id": comp["template_id"],
            "subtype": comp.get("subtype", template.get("subtype")),
            "config": comp.get("config", template.get("default_config", {})),
            "quantity": quantity,
        }
        # Pass-through metric contribution if provided
        if "metric_contribution" in comp:
            mc = comp["metric_contribution"]
            rover_cfg["metric_contribution"] = {
                "metric_id": mc.get("metric_id"),
                "value": float(mc.get("contribution_value", mc.get("value", 0.0))),
            }
        config["science_rovers"].append(rover_cfg)
    return config


def _configure_manufacturing_sector(manufacturing_components, templates, world_system):
    """Configure manufacturing sector components."""
    config = {"isru_extractors": [], "isru_generators": [], "initial_stocks": world_system.get("initial_stocks", {})}
    for comp in manufacturing_components:
        template = templates.get(comp["template_id"])
        if not template:
            continue
        base_cfg = {
            "template_id": comp["template_id"],
            "subtype": comp.get("subtype", template.get("subtype")),
            "config": comp.get("config", template.get("default_config", {})),
            "quantity": int(comp.get("quantity", 1)),
        }
        if "metric_contribution" in comp:
            mc = comp["metric_contribution"]
            base_cfg["metric_contribution"] = {
                "metric_id": mc.get("metric_id"),
                "value": float(mc.get("contribution_value", mc.get("value", 0.0))),
            }
        subtype = base_cfg.get("subtype", "").lower()
        if subtype == "extractor":
            config["isru_extractors"].append(base_cfg)
        elif subtype == "generator":
            config["isru_generators"].append(base_cfg)
    return config

def _configure_equipment_manufacturing_sector(equipment_components, templates):
    """Configure the equipment manufacturing sector."""

    config = {"initial_stocks": {}}

    if not equipment_components:
        return config

    for comp in equipment_components:
        # Check for the special "equipment_stock" key
        if "equipment_stock" in comp:
            config["initial_stocks"].update(comp["equipment_stock"])

    return config


def _configure_goals_system(world_system, db):
    """Configure goals system from active goal IDs."""

    goals_config = {"performance_goals": []}
    active_goal_refs = world_system.get("active_goal_ids", []) or []

    if not active_goal_refs:
        print("No active goals found in world system")
        return goals_config

    for goal_ref in active_goal_refs:
        if isinstance(goal_ref, str):
            goal_id = goal_ref
        else:
            goal_id = goal_ref.get("goal_id")

        if not goal_id:
            print(f"Warning: Invalid goal reference: {goal_ref}")
            continue

        goal_doc = db.find_by_id("goals", goal_id)
        if not goal_doc:
            print(f"Warning: Goal {goal_id} not found in database")
            continue

        if goal_doc.get("type", "functional_goal") != "performance_goal":
            # Silently ignore functional goals in this simplified system
            continue

        goals_config["performance_goals"].append({
            "goal_id": goal_id,
            "name": goal_doc.get("name", "Unknown Performance Goal"),
            "metric_id": goal_doc.get("metric_id"),
            "target_value": float(goal_doc.get("target_value", 0)),
            "direction": goal_doc.get("direction", "minimize"),
            "weight": float(goal_doc.get("weight", 1.0)),
        })

    return goals_config