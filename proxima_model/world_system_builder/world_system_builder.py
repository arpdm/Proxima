"""
world_system_builder.py

PROXIMA LUNAR SIMULATION - WORLD SYSTEM BUILDER

PURPOSE:
========
Builds world system configurations from database documents for the Proxima simulation engine.
Processes component templates, metrics, resources, and goals into a unified configuration.

ARCHITECTURE:
=============
- Sector Builders: Specialized builders for each simulation sector
- Template Resolution: Merges component instances with templates
- Goal Configuration: Processes performance and functional goals
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Any, Optional
from data_engine.proxima_db_engine import ProximaDB

import logging

logger = logging.getLogger(__name__)


class ComponentType(Enum):
    """Available component types."""

    POWER_GENERATOR = "power_generator"
    POWER_STORAGE = "power_storage"
    ORBITAL_ROCKET = "orbital_rocket"
    FUEL_GEN = "fuel_gen"
    SCIENCE_ROVER = "science_rover"
    ISRU_ROBOT = "isru_robot"


class GoalType(Enum):
    """Available goal types."""

    PERFORMANCE_GOAL = "performance_goal"
    FUNCTIONAL_GOAL = "functional_goal"


class GoalDirection(Enum):
    """Goal optimization direction."""

    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@dataclass
class ComponentConfig:
    """Configuration for a component instance."""

    template_id: str
    subtype: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    quantity: int = 1
    metric_contribution: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate component configuration."""
        if self.quantity < 0:
            raise ValueError("Quantity must be non-negative")


@dataclass
class PerformanceGoal:
    """Configuration for a performance goal."""

    goal_id: str
    name: str
    metric_id: str
    target_value: float
    direction: str = "minimize"
    weight: float = 1.0

    def __post_init__(self):
        """Validate goal configuration."""
        if self.weight < 0:
            raise ValueError("Weight must be non-negative")
        if self.direction not in [GoalDirection.MINIMIZE.value, GoalDirection.MAXIMIZE.value]:
            raise ValueError(f"Invalid direction: {self.direction}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "goal_id": self.goal_id,
            "name": self.name,
            "metric_id": self.metric_id,
            "target_value": self.target_value,
            "direction": self.direction,
            "weight": self.weight,
        }


@dataclass
class WorldSystemConfig:
    """Complete world system configuration."""

    sim_time: int
    delta_t: float
    p_need: float = 2.0
    agents_config: Dict[str, Any] = field(default_factory=dict)
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    resources: List[Dict[str, Any]] = field(default_factory=list)
    dust_decay_per_step: float = 0.0
    goals: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def __post_init__(self):
        """Validate world system configuration."""
        if self.sim_time <= 0:
            raise ValueError("sim_time must be positive")
        if self.delta_t <= 0:
            raise ValueError("delta_t must be positive")


class ComponentBuilder:
    """Base class for component configuration builders."""

    def __init__(self, templates: Dict[str, Dict[str, Any]]):
        """
        Initialize component builder with templates.

        Args:
            templates: Dictionary of component templates keyed by template_id
        """
        self._templates = templates

    def _get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Get template by ID with error handling.

        Args:
            template_id: Template identifier

        Returns:
            Template dictionary or None if not found
        """
        template = self._templates.get(template_id)
        if not template:
            logger.warning(f"⚠️  Warning: Template {template_id} not found")
        return template

    def _merge_config(self, component: Dict[str, Any], template: Dict[str, Any]) -> ComponentConfig:
        """
        Merge component instance with template.

        Args:
            component: Component instance from world system
            template: Component template definition

        Returns:
            Merged ComponentConfig
        """
        merged_config = {
            **template.get("config", {}),
            **template.get("default_config", {}),
            **component.get("config", {}),
        }

        config = ComponentConfig(
            template_id=component["template_id"],
            subtype=component.get("subtype", template.get("subtype")),
            config=merged_config,
            quantity=int(component.get("quantity", 1)),
        )

        # Add metric contribution if present
        if "metric_contribution" in component:
            mc = component["metric_contribution"]
            config.metric_contribution = {
                "metric_id": mc.get("metric_id"),
                "value": float(mc.get("contribution_value", mc.get("value", 0.0))),
            }

        return config


class EnergySectorBuilder(ComponentBuilder):
    """Builds energy sector configuration."""

    def build(self, components: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build energy sector configuration.

        Args:
            components: List of energy component instances

        Returns:
            Dictionary with 'generators' and 'storages' lists
        """
        config = {"sector_name": "energy", "generators": [], "storages": []}

        for comp in components:
            template = self._get_template(comp["template_id"])
            if not template:
                continue

            merged = self._merge_config(comp, template)
            component_data = {
                "template_id": merged.template_id,
                "subtype": merged.subtype,
                "config": merged.config,
                "quantity": merged.quantity,
            }

            comp_type = template.get("type", "").lower()
            if comp_type == ComponentType.POWER_GENERATOR.value:
                config["generators"].append(component_data)
            elif comp_type == ComponentType.POWER_STORAGE.value:
                config["storages"].append(component_data)

        logger.info(
            f"✅ Configured energy sector: {len(config['generators'])} generators, {len(config['storages'])} storages"
        )
        return config


class ScienceSectorBuilder(ComponentBuilder):
    """Builds science sector configuration."""

    def build(self, components: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build science sector configuration.

        Args:
            components: List of science component instances

        Returns:
            Dictionary with 'science_rovers' list
        """
        config = {"sector_name": "science", "science_rovers": []}

        for comp in components:
            template = self._get_template(comp["template_id"])
            if not template:
                continue

            merged = self._merge_config(comp, template)
            rover_cfg = {
                "template_id": merged.template_id,
                "subtype": merged.subtype,
                "config": merged.config,
                "quantity": merged.quantity,
            }

            if merged.metric_contribution:
                rover_cfg["metric_contribution"] = merged.metric_contribution

            config["science_rovers"].append(rover_cfg)

        logger.info(f"✅ Configured science sector: {len(config['science_rovers'])} rovers")
        return config


class ManufacturingSectorBuilder(ComponentBuilder):
    """Builds manufacturing sector configuration."""

    def build(self, components: List[Dict[str, Any]], initial_stocks: Dict[str, float]) -> Dict[str, Any]:
        """
        Build manufacturing sector configuration.

        Args:
            components: List of manufacturing component instances
            initial_stocks: Initial resource stocks from world system

        Returns:
            Dictionary with 'isru_robots' and 'initial_stocks'
        """
        config = {
            "sector_name": "manufacturing",
            "isru_robots": [],
            "initial_stocks": initial_stocks,
        }

        for comp in components:
            template = self._get_template(comp["template_id"])
            if not template:
                continue

            merged = self._merge_config(comp, template)
            robot_cfg = {
                "template_id": merged.template_id,
                "subtype": merged.subtype,
                "config": merged.config,
                "quantity": merged.quantity,
            }

            if merged.metric_contribution:
                robot_cfg["metric_contribution"] = merged.metric_contribution

            # All ISRU components are now robots
            config["isru_robots"].append(robot_cfg)

        logger.info(f"✅ Configured manufacturing sector: {len(config['isru_robots'])} ISRU robots")
        return config


class TransportationSectorBuilder(ComponentBuilder):
    """Builds transportation sector configuration."""

    def build(self, components: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build transportation sector configuration.

        Args:
            components: List of transportation component instances and configuration

        Returns:
            Dictionary with sector config, rockets, and fuel_generators
        """
        # Import the config class to get default values
        from proxima_model.sphere_engine.transportation_sector import TransportationConfig

        # Start with defaults from the dataclass
        default_config = TransportationConfig()

        config = {
            "sector_name": "transportation",
            "rockets": [],
            "fuel_generators": [],
        }

        # Add all fields from TransportationConfig with their default values
        for field_name in default_config.__dataclass_fields__.keys():
            config[field_name] = getattr(default_config, field_name)

        for comp in components:
            # Check if this is a sector configuration (no template_id)
            if "template_id" not in comp:
                # Dynamically update any field that exists in the config
                for key, value in comp.items():
                    if key in config:  # Only update if key exists in our config
                        config[key] = value
                        logger.info(f"✅ Updated transportation config: {key} = {value}")
                continue

            # This is a component instance - existing logic unchanged
            template = self._get_template(comp["template_id"])
            if not template:
                continue

            merged = self._merge_config(comp, template)
            base_cfg = {
                "template_id": merged.template_id,
                "subtype": merged.subtype,
                "config": merged.config,
                "quantity": merged.quantity,
            }

            comp_type = template.get("type", "").lower()
            if comp_type == ComponentType.ORBITAL_ROCKET.value:
                config["rockets"].append(base_cfg)
            elif comp_type == ComponentType.FUEL_GEN.value:
                config["fuel_generators"].append(base_cfg)

        logger.info(
            f"✅ Configured transportation sector: {len(config['rockets'])} rockets, {len(config['fuel_generators'])} fuel generators"
        )
        return config


class EquipmentManufacturingSectorBuilder(ComponentBuilder):
    """Builds equipment manufacturing sector configuration."""

    def build(self, components: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """
        Build equipment manufacturing sector configuration.

        Args:
            components: List of equipment component instances

        Returns:
            Dictionary with 'initial_stocks'
        """
        config = {"sector_name": "equipment_manufacturing", "initial_stocks": {}}

        for comp in components:
            # Check for special "equipment_stock" key
            if "equipment_stock" in comp:
                config["initial_stocks"].update(comp["equipment_stock"])

        logger.info(f"✅ Configured equipment manufacturing sector: {len(config['initial_stocks'])} equipment types")
        return config


class GoalsSystemBuilder:
    """Builds goals system configuration."""

    def __init__(self, db: ProximaDB):
        """
        Initialize goals system builder.

        Args:
            db: ProximaDB database instance
        """
        self._db = db

    def build(self, active_goal_ids: List[Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build goals system configuration from active goal IDs.

        Args:
            active_goal_ids: List of active goal references

        Returns:
            Dictionary with 'performance_goals' list
        """
        config = {"performance_goals": []}

        if not active_goal_ids:
            logger.info("ℹ️  No active goals found in world system")
            return config

        for goal_ref in active_goal_ids:
            # Extract goal ID from reference
            if isinstance(goal_ref, str):
                goal_id = goal_ref
            else:
                goal_id = goal_ref.get("goal_id")

            if not goal_id:
                logger.warning(f"⚠️  Warning: Invalid goal reference: {goal_ref}")
                continue

            # Load goal document
            goal_doc = self._db.find_by_id("goals", goal_id)
            if not goal_doc:
                logger.warning(f"⚠️  Warning: Goal {goal_id} not found in database")
                continue

            # Only process performance goals
            if goal_doc.get("type", GoalType.FUNCTIONAL_GOAL.value) != GoalType.PERFORMANCE_GOAL.value:
                continue

            # Create performance goal
            try:
                goal = PerformanceGoal(
                    goal_id=goal_id,
                    name=goal_doc.get("name", "Unknown Performance Goal"),
                    metric_id=goal_doc.get("metric_id"),
                    target_value=float(goal_doc.get("target_value", 0)),
                    direction=goal_doc.get("direction", GoalDirection.MINIMIZE.value),
                    weight=float(goal_doc.get("weight", 1.0)),
                )
                config["performance_goals"].append(goal.to_dict())
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️  Warning: Invalid goal configuration for {goal_id}: {e}")

        logger.info(f"✅ Configured goals system: {len(config['performance_goals'])} performance goals")
        return config


def build_world_system_config(world_system_id: str, experiment_id: str, db: ProximaDB) -> dict:
    """
    Build a world system configuration from database documents.

    Args:
        world_system_id: World system document ID
        experiment_id: Experiment document ID
        db: ProximaDB database instance

    Returns:
        Complete world system configuration dictionary
    """
    # Load documents
    world_system = db.find_by_id("world_systems", world_system_id)
    experiment = db.find_by_id("experiments", experiment_id)
    environment = db.find_by_id("environments", world_system["environment_id"])
    component_templates = {c["_id"]: c for c in db.list_all("component_templates")}

    # Build base configuration
    config = {
        "sim_time": experiment.get("simulation_time_steps", experiment.get("simulation_time_stapes")),
        "delta_t": experiment.get("time_step_duration_hours"),
        "p_need": 2.0,
        "agents_config": {},
        "metrics": environment.get("metrics", []),
        "resources": environment.get("resources", []),
        "dust_decay_per_step": environment.get("dust_decay_per_step", 0.0),
    }

    # Extract component groups
    active_components = world_system.get("active_components", [])
    if not active_components:
        logger.info("ℹ️  No active components found in world system")
        return config

    components_dict = active_components[0]  # Assuming single component dict

    # Build sector configurations
    energy_builder = EnergySectorBuilder(component_templates)
    config["agents_config"]["energy"] = energy_builder.build(components_dict.get("energy", []))

    science_builder = ScienceSectorBuilder(component_templates)
    config["agents_config"]["science"] = science_builder.build(components_dict.get("science", []))

    manufacturing_builder = ManufacturingSectorBuilder(component_templates)
    config["agents_config"]["manufacturing"] = manufacturing_builder.build(
        components_dict.get("manufacturing", []), world_system.get("initial_stocks", {})
    )

    equipment_builder = EquipmentManufacturingSectorBuilder(component_templates)
    config["agents_config"]["equipment_manufacturing"] = equipment_builder.build(
        components_dict.get("equipmentManufacturing", [])
    )

    transportation_builder = TransportationSectorBuilder(component_templates)
    config["agents_config"]["transportation"] = transportation_builder.build(components_dict.get("transportation", []))

    # Build goals configuration
    goals_builder = GoalsSystemBuilder(db)
    config["goals"] = goals_builder.build(world_system.get("active_goal_ids", []))

    return config
