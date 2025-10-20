"""
manufacturing_sector.py

PROXIMA LUNAR SIMULATION - MANUFACTURING SECTOR MANAGER

PURPOSE:
========
The ManufacturingSector manages all In-Situ Resource Utilization (ISRU) operations on the lunar base.
It orchestrates extraction and generation agents to produce essential resources (He3, metals, water, etc.)
based on dynamic priority systems and available power budgets.

CORE ALGORITHMS:
===============
1) Each managed stock has a target band [min, max] from config.
2) At each step, compute deficiency = max(0, min_target - current_stock).
3) Choose tasks whose primary output stocks have the largest deficiencies.
4) Assign agents to tasks based on priority and availability.
5) Execute operations and process stock flows atomically.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Tuple, Optional, Any
import threading

from proxima_model.components.isru import ISRUExtractor, ISRUGenerator


class TaskType(Enum):
    """Available manufacturing tasks."""

    HE3 = auto()
    WATER = auto()
    REGOLITH = auto()
    METAL = auto()
    ELECTROLYSIS = auto()


class SectorState(Enum):
    """Manufacturing sector operational states."""

    ACTIVE = auto()
    INACTIVE = auto()
    THROTTLED = auto()


@dataclass
class BufferTarget:
    """Resource buffer target configuration."""

    min: float = 0.0
    max: float = 100.0

    def __post_init__(self):
        if self.min < 0 or self.max < 0:
            raise ValueError("Buffer targets must be non-negative")
        if self.min > self.max:
            raise ValueError("Min target cannot exceed max target")


@dataclass
class TaskDefinition:
    """Definition of a manufacturing task."""

    task_type: TaskType
    generator_mode: Optional[str] = None
    extractor_mode: Optional[str] = None
    primary_output: str = ""

    def __post_init__(self):
        # Allow tasks without modes for placeholders/future expansion
        # Only validate if modes are provided
        if self.generator_mode and self.extractor_mode:
            raise ValueError("Task cannot specify both generator and extractor modes")


@dataclass
class StockFlow:
    """Represents a resource flow transaction."""

    source_component: str
    consumed: Dict[str, float] = field(default_factory=dict)
    generated: Dict[str, float] = field(default_factory=dict)


@dataclass
class ManufacturingMetrics:
    """Manufacturing sector metrics."""

    power_demand: float = 0.0
    power_consumed: float = 0.0
    active_operations: int = 0
    operational_extractors: int = 0
    operational_generators: int = 0
    sector_state: SectorState = SectorState.ACTIVE
    stocks: Dict[str, float] = field(default_factory=dict)
    metric_contributions: Dict[str, float] = field(default_factory=dict)


class ManufacturingSector:
    """Manages ISRU operations, resource stocks, and manufacturing processes."""

    # Default task definitions for easy expansion
    DEFAULT_TASKS = {
        TaskType.HE3: TaskDefinition(TaskType.HE3, "HE3", None, "He3_kg"),
        TaskType.WATER: TaskDefinition(TaskType.WATER, None, "ICE", "H2O_kg"),
        TaskType.REGOLITH: TaskDefinition(TaskType.REGOLITH, None, "REGOLITH", "FeTiO3_kg"),
    }

    # Default buffer targets
    DEFAULT_BUFFER_TARGETS = {
        "He3_kg": BufferTarget(min=20.0, max=300.0),
        "H2O_kg": BufferTarget(min=2.0, max=10.0),
        "FeTiO3_kg": BufferTarget(min=20.0, max=100.0),
    }

    def __init__(self, model, config, event_bus):
        """Initialize manufacturing sector with agents and resource stocks."""

        self.model = model
        self.config = config
        self.event_bus = event_bus

        # Thread safety for shared state
        self._lock = threading.Lock()

        # Agent collections
        self.isru_extractors: List[ISRUExtractor] = []
        self.isru_generators: List[ISRUGenerator] = []

        # Operation state
        self.sector_state = SectorState.ACTIVE
        self.extractor_throttle = 1.0
        self.pending_stock_flows: List[StockFlow] = []

        # Metrics tracking
        self._current_metrics = ManufacturingMetrics()
        self.total_power_consumed = 0.0

        # Metric contributions from config
        self.extractor_metric_contributions = config.get("extractor_metric_contributions", {"value": 1.0})

        # Initialize resource stocks
        self.stocks: Dict[str, float] = {
            "H2O_kg": 0.0,
            "FeTiO3_kg": 0.0,
            "He3_kg": 0.0,
            **config.get("initial_stocks", {}),
        }

        # Initialize buffer targets
        self.buffer_targets: Dict[str, BufferTarget] = self._initialize_buffer_targets(config)

        # Initialize task definitions (allow config overrides)
        self.task_definitions: Dict[TaskType, TaskDefinition] = {
            **self.DEFAULT_TASKS,
            **self._load_task_definitions(config),
        }

        self._initialize_agents(config)

        # Subscribe to events
        self.event_bus.subscribe("resource_request", self.fulfill_resource_request)

    def _initialize_buffer_targets(self, config: dict) -> Dict[str, BufferTarget]:
        """Initialize buffer targets from configuration."""
        targets = self.DEFAULT_BUFFER_TARGETS.copy()

        # Override with config values
        config_targets = config.get("buffer_targets", {})
        for resource, target_config in config_targets.items():
            if isinstance(target_config, dict):
                targets[resource] = BufferTarget(min=target_config.get("min", 0.0), max=target_config.get("max", 100.0))

        return targets

    def _load_task_definitions(self, config: dict) -> Dict[TaskType, TaskDefinition]:
        """Load custom task definitions from config."""
        custom_tasks = {}
        for task_config in config.get("custom_tasks", []):
            try:
                task_type = TaskType[task_config["name"].upper()]
                custom_tasks[task_type] = TaskDefinition(
                    task_type=task_type,
                    generator_mode=task_config.get("generator_mode"),
                    extractor_mode=task_config.get("extractor_mode"),
                    primary_output=task_config.get("primary_output", ""),
                )
            except (KeyError, ValueError):
                continue  # Skip invalid tasks
        return custom_tasks

    def _initialize_agents(self, config: dict):
        """Initialize ISRU agents from configuration."""
        # Initialize extractors
        for agent_cfg in config.get("isru_extractors", []):
            quantity = agent_cfg.get("quantity", 1)
            agent_config = agent_cfg.get("config", {})

            for _ in range(quantity):
                extractor = ISRUExtractor(self.model, agent_config)
                self.isru_extractors.append(extractor)

        # Initialize generators
        for agent_cfg in config.get("isru_generators", []):
            quantity = agent_cfg.get("quantity", 1)
            agent_config = agent_cfg.get("config", {})

            for _ in range(quantity):
                generator = ISRUGenerator(self.model, agent_config)
                self.isru_generators.append(generator)

    def fulfill_resource_request(self, requesting_sector: str, resource: str, amount: float):
        """Handle resource requests from other sectors."""
        with self._lock:
            available_amount = self.stocks.get(resource, 0.0)

            if available_amount >= amount:
                self.stocks[resource] = available_amount - amount
                print(f"Fulfilling request. Remaining {resource}: {self.stocks[resource]:.2f} kg.")

                self.event_bus.publish(
                    "resource_allocated",
                    recipient_sector=requesting_sector,
                    resource=resource,
                    amount=amount,
                )

    def add_stock_flow(
        self,
        source_component: str,
        consumed: Optional[Dict[str, float]] = None,
        generated: Optional[Dict[str, float]] = None,
    ) -> None:
        """Add a stock flow transaction to pending queue."""

        flow = StockFlow(source_component=source_component, consumed=consumed or {}, generated=generated or {})
        with self._lock:
            self.pending_stock_flows.append(flow)

    def process_all_stock_flows(self) -> Dict[str, Dict[str, float]]:
        """Process all pending stock flows atomically."""

        with self._lock:
            if not self.pending_stock_flows:
                return {"consumed": {}, "generated": {}}

            total_consumed = {}
            total_generated = {}

            # Process all flows atomically
            for flow in self.pending_stock_flows:
                # Apply consumption
                for resource, amount in flow.consumed.items():
                    if resource in self.stocks:
                        self.stocks[resource] = max(0.0, self.stocks[resource] - amount)
                        total_consumed[resource] = total_consumed.get(resource, 0.0) + amount

                # Apply generation
                for resource, amount in flow.generated.items():
                    self.stocks[resource] = self.stocks.get(resource, 0.0) + amount
                    total_generated[resource] = total_generated.get(resource, 0.0) + amount

            # Clear processed flows
            self.pending_stock_flows.clear()

            return {"consumed": total_consumed, "generated": total_generated}

    def _calculate_task_priorities(self) -> List[TaskType]:
        """Calculate task priorities based on resource deficiencies."""

        deficiencies = []

        for task_def in self.task_definitions.values():
            if not task_def.primary_output:
                continue

            target = self.buffer_targets.get(task_def.primary_output)
            if not target:
                continue

            current_stock = self.stocks.get(task_def.primary_output, 0.0)
            deficiency = max(0.0, target.min - current_stock)

            if deficiency > 0:
                deficiencies.append((task_def.task_type, deficiency))

        # Sort by deficiency (descending)
        return [task for task, _ in sorted(deficiencies, key=lambda x: -x[1])]

    def _assign_agents_to_tasks(self, priority_tasks: List[TaskType]):
        """Assign agents to tasks based on priority."""

        # Set all agents to inactive first
        for extractor in self.isru_extractors:
            extractor.set_operational_mode("INACTIVE")
        for generator in self.isru_generators:
            generator.set_operational_mode("INACTIVE")

        # Assign extractors to priority tasks
        extractor_index = 0
        for task_type in priority_tasks:
            task_def = self.task_definitions[task_type]
            if task_def.extractor_mode and extractor_index < len(self.isru_extractors):
                self.isru_extractors[extractor_index].set_operational_mode(task_def.extractor_mode)
                extractor_index += 1

        # Assign generators to priority tasks
        generator_index = 0
        for task_type in priority_tasks:
            task_def = self.task_definitions[task_type]
            if task_def.generator_mode and generator_index < len(self.isru_generators):
                self.isru_generators[generator_index].set_operational_mode(task_def.generator_mode)
                generator_index += 1

    def set_throttle_factor(self, factor: float):
        """Set throttle factor for extractor operations."""

        self.extractor_throttle = max(0.0, min(1.0, float(factor)))

    def get_power_demand(self) -> float:
        """Calculate total power demand from all ISRU operations."""

        if self.sector_state == SectorState.INACTIVE:
            return 0.0

        extractor_demand = sum(agent.get_power_demand() for agent in self.isru_extractors)
        generator_demand = sum(agent.get_power_demand() for agent in self.isru_generators)

        return extractor_demand + generator_demand

    def step(self, allocated_power: float) -> float:
        """Execute manufacturing operations for one simulation step."""

        # Reset metrics
        self._current_metrics = ManufacturingMetrics()

        if allocated_power <= 0 or self.sector_state == SectorState.INACTIVE:
            self._set_all_agents_inactive()
            return allocated_power

        # Determine task priorities and assign agents
        priority_tasks = self._calculate_task_priorities()
        self._assign_agents_to_tasks(priority_tasks)

        remaining_power = allocated_power

        # Execute generator operations first
        for generator in self.isru_generators:
            power_demand = generator.get_power_demand()
            if power_demand > 0 and remaining_power >= power_demand:
                generated, consumed, used_power = generator.generate_resources(power_demand, self.stocks)

                if generated or consumed:
                    self.add_stock_flow("ISRU_Generator", consumed, generated)

                remaining_power -= used_power
                self._current_metrics.power_consumed += used_power

                if used_power > 0:
                    self._current_metrics.operational_generators += 1

        # Execute extractor operations with throttling
        max_extractors = max(0, int(len(self.isru_extractors) * self.extractor_throttle))

        for i, extractor in enumerate(self.isru_extractors[:max_extractors]):
            power_demand = extractor.get_power_demand()
            if power_demand > 0 and remaining_power >= power_demand:
                extracted, used_power = extractor.extract_resources(power_demand)

                if extracted:
                    self.add_stock_flow("ISRU_Extractor", None, extracted)

                remaining_power -= used_power
                self._current_metrics.power_consumed += used_power

                if used_power > 0:
                    self._current_metrics.operational_extractors += 1

        # Process all stock flows atomically
        self.process_all_stock_flows()

        # Update total metrics
        self.total_power_consumed += self._current_metrics.power_consumed
        self._current_metrics.active_operations = (
            self._current_metrics.operational_extractors + self._current_metrics.operational_generators
        )

        return remaining_power

    def _set_all_agents_inactive(self):
        """Set all agents to inactive mode."""

        for generator in self.isru_generators:
            generator.set_operational_mode("INACTIVE")
        for extractor in self.isru_extractors:
            extractor.set_operational_mode("INACTIVE")

    def get_stocks(self) -> Dict[str, float]:
        """Return current resource stocks (read-only copy)."""

        with self._lock:
            return self.stocks.copy()

    def set_buffer_targets(self, targets: Dict[str, Dict[str, float]]):
        """Update buffer targets dynamically."""

        for resource, target_config in targets.items():
            if isinstance(target_config, dict):
                self.buffer_targets[resource] = BufferTarget(
                    min=target_config.get("min", 0.0), max=target_config.get("max", 100.0)
                )

    def _create_metric_map(self):
        """
        Create a map of metric IDs and their corresponding values.
        Only contributes metrics if agents actually operated in this step.

        Returns:
            dict: A dictionary where keys are metric IDs and values are their contributions.
        """

        metric_map = {}
        value = float(
            self.extractor_metric_contributions.get(
                "value", self.extractor_metric_contributions.get("contribution_value", 0.0)
            )
        )
        metric_map["IND-DUST-COV"] = self._current_metrics.operational_extractors * value
        return metric_map

    def get_metrics(self) -> Dict:
        """Return comprehensive manufacturing sector metrics."""

        with self._lock:
            return {
                "power_demand": self.get_power_demand(),
                "power_consumed": self._current_metrics.power_consumed,
                "active_operations": self._current_metrics.active_operations,
                "operational_extractors": self._current_metrics.operational_extractors,
                "operational_generators": self._current_metrics.operational_generators,
                "sector_state": self.sector_state.name,
                **{f"stock_{k}": v for k, v in self.stocks.items()},
                "metric_contributions": self._create_metric_map(),
            }
