# proxima_mongo_api.py

from pymongo import MongoClient
from datetime import datetime, timezone
from pathlib import Path
import json
import argparse

class ProximaDB:
    def __init__(self, uri="mongodb://localhost:27017", db_name="proxima_db"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]

    # General Helpers
    def list_all(self, collection):
        return list(self.db[collection].find({}))

    def find_by_id(self, collection, _id):
        return self.db[collection].find_one({"_id": _id})

    def update_field(self, collection, _id, field, value):
        return self.db[collection].update_one({"_id": _id}, {"$set": {field: value}})

    def add_field_to_all(self, collection, field, value):
        return self.db[collection].update_many({}, {"$set": {field: value}})

    def remove_field_from_all(self, collection, field):
        return self.db[collection].update_many({}, {"$unset": {field: ""}})

    # Environment Methods
    def create_environment(self, env_id, name, gravity, resources=None):
        doc = {"_id": env_id, "name": name, "gravity": gravity, "resources": resources or []}
        return self.db.environments.insert_one(doc)

    # Component Templates
    def create_component_template(self, comp_id, name, type, subtype, sphere, config, children=None):
        doc = {
            "_id": comp_id,
            "name": name,
            "type": type,
            "subtype": subtype,
            "sphere": sphere,
            "config": config,
            "children": children or [],
        }
        return self.db.component_templates.insert_one(doc)

    # World Systems
    def create_world_system(self, ws_id, name, environment_id, components, live_state, active_plicies=None, linked_events = None):
        doc = {
            "_id": ws_id,
            "name": name,
            "environment_id": environment_id,
            "live_state": live_state,
            "active_components": components,
            "active_policy_ids": [],
            "active_event_ids": []
        }
        return self.db.world_systems.insert_one(doc)

    def add_component_instance(self, ws_id, component):
        return self.db.world_systems.update_one({"_id": ws_id}, {"$push": {"active_components": component}})

    def update_component_config(self, ws_id, instance_id, config_updates):
        return self.db.world_systems.update_one(
            {"_id": ws_id, "active_components.instance_id": instance_id},
            {"$set": {f"active_components.$.config": config_updates}},
        )

    def generate_component_instance(self, template_id, instance_id, state=None, config_override=None):
        template = self.find_by_id("component_templates", template_id)
        if not template:
            raise ValueError(f"Component template '{template_id}' not found.")

        component = {
            "template_id": template_id,
            "instance_id": instance_id,
            "state": state or {},
            "config": config_override if config_override is not None else template.get("config", {}),
        }
        return component

    # Policies
    def create_policy(self, policy_id, name, trigger_condition, response_action):
        doc = {
            "_id": policy_id,
            "name": name,
            "trigger_condition": trigger_condition,
            "response_action": response_action,
        }
        return self.db.policies.insert_one(doc)

    # Goals
    def create_goal(self, goal_id, name, metrics, scope):
        doc = {"_id": goal_id, "name": name, "target_metrics": metrics, "world_system_scope": scope}
        return self.db.goals.insert_one(doc)

    # Events
    def create_event(self, event_id, name, timestamp, target_system_id, effect):
        doc = {
            "_id": event_id,
            "name": name,
            "timestamp": timestamp,
            "target_system_id": target_system_id,
            "effect": effect,
        }
        return self.db.events.insert_one(doc)
    
    # Experiments
    def create_experiment(self, experiment_id, world_system_id, sim_time_steps, time_step_duration_hours, experiment_type):
        doc = {
            "_id": experiment_id,
            "world_system_id": world_system_id,
            "simulation_time_stapes": sim_time_steps,
            "time_step_duration_hours": time_step_duration_hours,
            "experiment_type": experiment_type
        }
        return self.db.experiments.insert_one(doc)
    
    # Export Database
    def export_all_collections_to_json(self, output_dir="mongo_exports"):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        for name in self.db.list_collection_names():
            data = list(self.db[name].find())
            for doc in data:
                doc["_id"] = str(doc["_id"])  # Convert ObjectId to string
            file_path = output_path / f"{name}.json"
            with file_path.open("w") as f:
                json.dump(data, f, indent=2)
        return f"Exported collections to {output_path}/"

    # Import Database
    def import_all_collections_from_json(self, input_dir="mongo_exports"):
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Directory '{input_dir}' does not exist.")

        for json_file in input_path.glob("*.json"):
            collection_name = json_file.stem
            with json_file.open("r") as f:
                data = json.load(f)
                for doc in data:
                    if "_id" in doc:
                        del doc["_id"]  # Let MongoDB assign a new ObjectId
                if data:
                    self.db[collection_name].insert_many(data)
        return f"Imported collections from {input_path}/"

# CLI Interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Proxima MongoDB CLI Interface")
    parser.add_argument("action", choices=["export", "import"], help="Choose to export or import the database")
    parser.add_argument("--dir", default="mongo_exports", help="Directory for export or import")

    args = parser.parse_args()
    db = ProximaDB()

    if args.action == "export":
        print(db.export_all_collections_to_json(args.dir))
    elif args.action == "import":
        print(db.import_all_collections_from_json(args.dir))
