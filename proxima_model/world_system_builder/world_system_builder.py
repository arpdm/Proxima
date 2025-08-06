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
        "agents_config": {}
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

    return config


def _configure_energy_sector(energy_components, templates):
    """Configure energy sector components."""
    config = {
        "generators": [],
        "storages": []
    }
    
    for comp in energy_components:
        template = templates.get(comp["template_id"])
        if not template:
            print(f"Warning: Template {comp['template_id']} not found")
            continue
            
        component_data = {
            "template_id": comp["template_id"],
            "subtype": comp.get("subtype"),
            "config": {**template.get("config", {}), **comp.get("config", {})},
            "quantity": comp.get("quantity", 1)
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
    config = {
        "science_rovers": []
    }
    
    for comp in science_components:
        template = templates.get(comp["template_id"])
        if not template:
            print(f"Warning: Template {comp['template_id']} not found")
            continue
            
        component_data = {
            "template_id": comp["template_id"],
            "subtype": comp.get("subtype"),
            "config": {**template.get("config", {}), **comp.get("config", {})},
            "quantity": comp.get("quantity", 1)
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

        agents_config.append({
            "template_id": comp["template_id"],
            "subtype": comp["subtype"],
            "config": {**template.get("config", {}), **comp.get("config", {})},
            "quantity": comp.get("quantity", 1)
        })

    print(f"Configured manufacturing sector: {len(agents_config)} agent types")
    
    return {
        "agents_config": agents_config,
        "initial_stocks": world_system.get("initial_stocks", {})
    }
