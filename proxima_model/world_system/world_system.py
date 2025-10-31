"""
world_system.py

PROXIMA LUNAR SIMULATION - WORLD SYSTEM ORCHESTRATOR
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, Any, Optional, Set, List
import logging

from mesa import Model
from proxima_model.sphere_engine.energy_sector import EnergySector
from proxima_model.sphere_engine.science_sector import ScienceSector
from proxima_model.sphere_engine.manufacturing_sector import ManufacturingSector
from proxima_model.sphere_engine.equipment_manufacturing_sector import EquipmentManSector
from proxima_model.sphere_engine.transportation_sector import TransportationSector
from proxima_model.sphere_engine.construction_sector import ConstructionSector
from proxima_model.policy_engine.policy_engine import PolicyEngine
from proxima_model.world_system.evaluation_engine import EvaluationEngine
from proxima_model.event_engine.event_bus import EventBus

logger = logging.getLogger(__name__)


class AllocationMode(Enum):
    """Power allocation strategies."""

    PROPORTIONAL = "proportional"
    EQUAL = "equal"


class WorldSystem(Model):
    """Central orchestrator for the Proxima lunar base simulation."""

    # Sector registry for dynamic initialization
    SECTOR_REGISTRY = {
        "energy": EnergySector,
        "science": ScienceSector,
        "manufacturing": ManufacturingSector,
        "equipment_manufacturing": EquipmentManSector,
        "transportation": TransportationSector,
        "construction": ConstructionSector,
    }

    def __init__(self, config: Dict[str, Any], seed: Optional[int] = None):
        """
        Initialize world system with configuration.

        Args:
            config: World system configuration dictionary
            seed: Random seed for Mesa model
        """
        super().__init__(seed=seed)

        self.config = config
        self.running = True

        # Power allocation mode (TODO: Move to policy)
        allocation_mode_str = (self.config.get("allocation_mode") or "proportional").lower()
        self.allocation_mode = AllocationMode(allocation_mode_str)

        # Initialize event bus and sectors
        self.event_bus = EventBus()
        self.sectors: Dict[str, Any] = {}
        self._initialize_sectors()

        # Initialize evaluation engine
        goals_cfg = self.config.get("goals", {}) or {}
        performance_goals_data = goals_cfg.get("performance_goals", []) or []
        metric_defs_data = self.config.get("metrics", [])
        
        self.evaluation_engine = EvaluationEngine(
            metric_definitions=metric_defs_data,
            performance_goals=performance_goals_data,
        )

        # Model-wide metrics collection
        self.model_metrics: Dict[str, Any] = {"environment": {"step": 0}}

        # Environment dynamics
        self.dust_decay_per_step = float(self.config.get("dust_decay_per_step", 0.0))

        # Initialize policy engine (uses evaluation engine internally)
        self.policy = PolicyEngine(self)

    @property
    def metric_definitions(self) -> list:
        """Get metric definitions as list (backwards compatibility)."""
        return self.evaluation_engine.metric_definitions

    @property
    def performance_goals(self) -> List:
        """Get performance goals (backwards compatibility)."""
        return self.evaluation_engine.performance_goals

    @property
    def performance_metrics(self) -> Dict[str, float]:
        """Get current performance metrics (backwards compatibility)."""
        return self.evaluation_engine.performance_metrics

    def get_performance_metric(self, metric_id: str) -> float:
        """Get the current value of a performance metric."""
        return self.evaluation_engine.get_performance_metric(metric_id)

    def set_performance_metric(self, metric_id: str, value: float) -> None:
        """Set the value of a performance metric."""
        self.evaluation_engine.set_performance_metric(metric_id, value)

    def _initialize_sectors(self) -> None:
        """Initialize all sectors dynamically based on configuration."""
        agents_config = self.config.get("agents_config", {})

        for name, sector_class in self.SECTOR_REGISTRY.items():
            if name in agents_config:
                try:
                    self.sectors[name] = sector_class(self, agents_config[name], self.event_bus)
                    logger.info(f"✅ Initialized {name} sector")
                except Exception as e:
                    logger.error(f"⚠️  Failed to initialize {name} sector: {e}")

    def _get_power_consumers(self) -> Dict[str, Any]:
        """Get sectors that can consume power."""
        return {
            name: sector
            for name, sector in self.sectors.items()
            if name != "energy" and hasattr(sector, "get_power_demand")
        }

    def _allocate_power_fairly(self, available_power: float, operational_sectors: Dict[str, Any]) -> Dict[str, float]:
        """
        Compute fair power allocations for all non-energy sectors.

        Args:
            available_power: Total power available for allocation
            operational_sectors: Dictionary of sectors to allocate power to

        Returns:
            Dictionary of sector names to allocated power amounts
        """
        if not operational_sectors or available_power <= 0:
            return {name: 0.0 for name in operational_sectors}

        # Snapshot demands
        demands: Dict[str, float] = {
            name: max(0.0, float(sector.get_power_demand())) for name, sector in operational_sectors.items()
        }

        total_demand = sum(demands.values())

        if total_demand <= 0.0:
            return {name: 0.0 for name in operational_sectors}

        # Case 1: Sufficient power → satisfy all demands
        if total_demand <= available_power:
            return demands

        # Case 2: Scarcity → fair split based on allocation mode
        if self.allocation_mode == AllocationMode.EQUAL:
            num_sectors = len(operational_sectors)
            per_sector = available_power / num_sectors
            return {name: min(per_sector, demands[name]) for name in operational_sectors}
        else:
            # Proportional by demand (default)
            ratio = available_power / total_demand
            return {name: ratio * demands[name] for name in operational_sectors}

    def _collect_sector_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Collect metrics from all sectors."""
        sector_metrics = {}
        
        for sector_name, sector in self.sectors.items():
            if hasattr(sector, "get_metrics"):
                sector_metrics[sector_name] = sector.get_metrics()
        
        return sector_metrics

    def step(self) -> None:
        """Execute a single simulation step with dynamic sector handling."""

        # Get power-consuming sectors
        power_consumers = self._get_power_consumers()

        # Calculate total power demand
        total_power_demand = sum(float(s.get_power_demand()) for s in power_consumers.values())

        # Generate available power from energy sector
        energy_sector = self.sectors.get("energy")
        available_power = energy_sector.step(total_power_demand) if energy_sector else 0.0

        # Allocate power fairly among non-energy sectors
        sector_allocations = self._allocate_power_fairly(available_power, power_consumers)

        # Step each sector with its allocation
        for name, sector in power_consumers.items():
            alloc = sector_allocations.get(name, 0.0)
            if hasattr(sector, "step"):
                sector.step(alloc)

        # Collect metrics from all sectors
        sector_metrics = self._collect_sector_metrics()
        
        # Store sector metrics
        self.model_metrics = {
            "environment": {"step": self.steps},
            **sector_metrics
        }
        
        # Evaluate metrics using evaluation engine
        evaluation_result = self.evaluation_engine.evaluate(
            sector_metrics=sector_metrics,
            dust_decay_per_step=self.dust_decay_per_step
        )
        
        # Add performance data to model metrics
        self.model_metrics["performance"] = {
            "metrics": evaluation_result.performance_metrics,
            "scores": evaluation_result.scores,
        }
        
        # Update and apply policies
        self.policy.update_scores()
        self.policy.apply_policies()
