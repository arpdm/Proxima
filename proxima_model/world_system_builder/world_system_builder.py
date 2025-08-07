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
        "sim_time": experiment["simulation_time_stapes"],
        "delta_t": experiment["time_step_duration_hours"],
        "day_hours": environment["day_hours"],
        "night_hours": environment["night_hours"],
        "p_need": 2.0,
        "agents_config": {},
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
            print(f"Warning: Template {comp['template_id']} not found")
            continue

        component_data = {
            "template_id": comp["template_id"],
            "subtype": comp.get("subtype"),
            "config": {**template.get("config", {}), **comp.get("config", {})},
            "quantity": comp.get("quantity", 1),
        }

        comp_type = template.get("type", "").lower()
        if comp_type == "rover":
            config["science_rovers"].append(component_data)

    print(f"Configured science sector: {len(config['science_rovers'])} rovers")
    return config


def _configure_manufacturing_sector(manufacturing_components, templates, world_system):
    """Configure manufacturing sector components."""
    agents_config = []

    for comp in manufacturing_components:
        template = templates.get(comp["template_id"])
        if not template:
            print(f"Warning: Template {comp['template_id']} not found")
            continue

        agents_config.append(
            {
                "template_id": comp["template_id"],
                "subtype": comp["subtype"],
                "config": {**template.get("config", {}), **comp.get("config", {})},
                "quantity": comp.get("quantity", 1),
            }
        )

    print(f"Configured manufacturing sector: {len(agents_config)} agent types")

    return {"agents_config": agents_config, "initial_stocks": world_system.get("initial_stocks", {})}


def _configure_goals_system(world_system, db):
    """Configure goals system from active goal IDs."""
    goals_config = {"active_goals": [], "sector_priorities": {}}

    active_goal_refs = world_system.get("active_goal_ids", [])

    if not active_goal_refs:
        print("No active goals found in world system")
        return goals_config

    print(f"Loading {len(active_goal_refs)} active goals...")

    for goal_ref in active_goal_refs:
        # Handle both old format (string) and new format (object with goal_id and priority)
        if isinstance(goal_ref, str):
            goal_id = goal_ref
            priority_weight = 1.0
        else:
            goal_id = goal_ref.get("goal_id")
            priority_weight = goal_ref.get("priority", 1.0)

        if not goal_id:
            print(f"Warning: Invalid goal reference: {goal_ref}")
            continue

        # Load goal document from database
        goal_doc = db.find_by_id("goals", goal_id)
        if not goal_doc:
            print(f"Warning: Goal {goal_id} not found in database")
            continue

        goal_data = {
            "goal_id": goal_id,
            "name": goal_doc.get("name", "Unknown Goal"),
            "priority_weight": priority_weight,
            "sector_weights": goal_doc.get("sector_weights", {}),
        }

        goals_config["active_goals"].append(goal_data)
        print(f"Loaded goal: {goal_data['name']} (ID: {goal_id}, Priority: {priority_weight})")

    # Calculate combined sector priorities from all active goals
    goals_config["sector_priorities"] = _calculate_combined_sector_priorities(goals_config["active_goals"])

    print(f"Combined sector priorities: {goals_config['sector_priorities']}")
    return goals_config


def _calculate_combined_sector_priorities(active_goals):
    """Calculate combined sector priorities from multiple active goals."""
    combined_priorities = {}
    total_priority = sum(goal["priority_weight"] for goal in active_goals)

    if total_priority == 0:
        return combined_priorities

    for goal in active_goals:
        weight = goal["priority_weight"] / total_priority

        for sector, sector_weights in goal["sector_weights"].items():
            if sector not in combined_priorities:
                combined_priorities[sector] = {}

            for task, task_weight in sector_weights.items():
                current = combined_priorities[sector].get(task, 0.0)
                combined_priorities[sector][task] = current + (weight * task_weight)

    return combined_priorities
