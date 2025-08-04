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


def process_component(template, quantity, config, agents_config, template_id, instance_config, domain, subtype):
    comp_type = template.get("type", "").lower()
    base_cfg = template.get("config", {}) or {}
    cfg = {**base_cfg, **(instance_config or {})}

    if domain == "energy":
        if comp_type == "power_generator":
            agents_config.setdefault("generators", []).append({
                "template_id": template_id,
                "subtype": subtype,
                "config": cfg,
                "quantity": quantity
            })
        elif comp_type == "power_storage":
            agents_config.setdefault("storages", []).append({
                "template_id": template_id,
                "subtype": subtype,
                "config": cfg,
                "quantity": quantity
            })
    elif domain == "science":
        if comp_type == "rover":
            agents_config.setdefault("science_rovers", []).append({
                "template_id": template_id,
                "config": cfg,
                "quantity": quantity
            })


def configure_manufacturing_sector(ws_doc, proxima_db):
    """Configure manufacturing sector with ISRU agents from world system config."""
    agents_config = []
    
    # Get manufacturing components from world system active_components
    active_components = ws_doc.get("active_components", [])
    if not active_components:
        return {"agents": []}
    
    manufacturing_components = active_components[0].get("manufacturing", [])
    
    for component in manufacturing_components:
        template_id = component["template_id"]
        subtype = component["subtype"]
        config = component.get("config", {})
        quantity = component.get("quantity", 1)
        
        # Get template from database
        try:
            template = proxima_db.find_by_id("component_templates", template_id)
        except AttributeError:
            # Try alternative method names
            try:
                template = proxima_db.fetch_document("component_templates", template_id)
            except AttributeError:
                # Try collection query
                templates = proxima_db.db["component_templates"].find_one({"_id": template_id})
                template = templates
        
        if not template:
            print(f"Warning: Template {template_id} not found")
            continue
        
        # Merge template config with component config
        merged_config = {**template.get("config", {}), **config}
        
        # Store agent configuration for later instantiation
        agents_config.append({
            "template_id": template_id,
            "subtype": subtype,
            "config": merged_config,
            "quantity": quantity
        })
    
    print(f"Configured {len(agents_config)} manufacturing agent types")
    
    return {
        "agents_config": agents_config,
        "initial_stocks": {
            "H2_kg": 10.0,
            "O2_kg": 50.0,
            "H2O_kg": 600.0,  # Combined water: 100.0 + 500.0 (ice converted to water)
            "FeTiO3_kg": 11000.0,
            "Metal_kg": 0.0,
            "He3_kg": 0.0,
        }
    }


def build_world_system_config(world_system_id: str, experiment_id: str, db: ProximaDB) -> dict:
    """
    Build a generalized world system config from the new schema.
    """
    world_system = db.find_by_id("world_systems", world_system_id)
    experiment = db.find_by_id("experiments", experiment_id)
    environment = db.find_by_id("environments", world_system["environment_id"])
    component_templates = {c["_id"]: c for c in db.list_all("component_templates")}

    config = extract_environment_config(environment, experiment)
    agents_config = {}

    # Iterate over each domain in active_components
    for domain_dict in world_system.get("active_components", []):
        for domain, components in domain_dict.items():
            for comp in components:
                template_id = comp["template_id"]
                quantity = comp.get("quantity", 1)
                instance_config = comp.get("config", {})
                subtype = comp.get("subtype", None)
                template = component_templates.get(template_id)
                if not template:
                    continue
                # Generalized processing: pass domain, subtype, etc.
                process_component(
                    template=template,
                    quantity=quantity,
                    config=config,
                    agents_config=agents_config,
                    template_id=template_id,
                    instance_config=instance_config,
                    domain=domain,
                    subtype=subtype,
                )
    config["agents_config"] = agents_config
    config["agents_config"]["manufacturing"] = configure_manufacturing_sector(world_system, db)

    return config
