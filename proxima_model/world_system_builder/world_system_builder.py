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
    """
    Generalized component processor for any type/domain.
    Only add one entry per active component (not per instance) to agents_config["all_components"].
    """
    comp_type = template.get("type", "").lower()
    base_cfg = template.get("config", {}) or {}
    cfg = {**base_cfg, **(instance_config or {})}

    # Add only one entry per active component
    agents_config.setdefault("all_components", []).append({
        "template_id": template_id,
        "type": comp_type,
        "domain": domain,
        "subtype": subtype,
        "config": cfg,
        "quantity": quantity
    })

    if domain == "energy":
        if comp_type == "power_generator":
            config.setdefault("generators", []).extend([
                {"template_id": template_id, "subtype": subtype, "config": cfg}
                for _ in range(quantity)
            ])
        elif comp_type == "power_storage":
            config.setdefault("storages", []).extend([
                {"template_id": template_id, "subtype": subtype, "config": cfg}
                for _ in range(quantity)
            ])
    elif domain == "science":
        if comp_type == "science_rover":
            agents_config.setdefault("science_rovers", []).extend([
                {"template_id": template_id, "config": cfg}
                for _ in range(quantity)
            ])

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
                    subtype=subtype
                )
    config["agents_config"] = agents_config
    return config
