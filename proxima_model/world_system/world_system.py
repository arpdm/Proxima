"""
world_system.py

PROXIMA LUNAR SIMULATION - WORLD SYSTEM ORCHESTRATOR
"""

from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from mesa import Model
from proxima_model.sphere_engine.sector_factory import SectorFactory
from proxima_model.policy_engine.policy_engine import PolicyEngine
from proxima_model.world_system.evaluation_engine import EvaluationEngine
from proxima_model.event_engine.event_bus import EventBus

logger = logging.getLogger(__name__)


class WorldSystem(Model):
    """Central orchestrator for the Proxima lunar base simulation."""

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
        # TODO: Create a class for environment dynamis as they will grow
        self.dust_decay_per_step = float(self.config.get("dust_decay_per_step", 0.0))

        # Initialize policy engine (uses evaluation engine internally)
        self.policy = PolicyEngine(self)

    def _initialize_sectors(self) -> None:
        """Initialize all sectors dynamically using the factory."""
        agents_config = self.config.get("agents_config", {})

        for sector_name, sector_config in agents_config.items():
            try:
                # Use the factory to create the sector
                sector = SectorFactory.create_sector(sector_name, self, sector_config, self.event_bus)
                self.sectors[sector_name] = sector
                logger.info(f"✅ Initialized {sector_name} sector via factory")
            except Exception as e:
                logger.error(f"⚠️  Failed to initialize {sector_name} sector: {e}")

    def _get_power_consumers(self) -> Dict[str, Any]:
        """Get sectors that can consume power."""
        return {
            name: sector
            for name, sector in self.sectors.items()
            if name != "energy" and hasattr(sector, "get_power_demand")
        }

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

        # Collect power demands
        sector_demands = {name: max(0.0, float(sector.get_power_demand())) for name, sector in power_consumers.items()}

        # Allocate power via energy sector
        energy_sector = self.sectors.get("energy")
        sector_allocations = energy_sector.allocate_power(sector_demands) if energy_sector else {}

        # Step each sector with its allocation
        for name, sector in power_consumers.items():
            alloc = sector_allocations.get(name, 0.0)
            if hasattr(sector, "step"):
                sector.step(alloc)

        # Collect metrics from all sectors
        sector_metrics = self._collect_sector_metrics()

        # Store sector metrics
        self.model_metrics = {"environment": {"step": self.steps}, **sector_metrics}

        # 1. Evaluate metrics using evaluation engine
        evaluation_result = self.evaluation_engine.evaluate(
            sector_metrics=sector_metrics, dust_decay_per_step=self.dust_decay_per_step
        )

        # Add performance data to model metrics
        self.model_metrics["performance"] = {
            "metrics": evaluation_result.performance_metrics,
            "scores": evaluation_result.scores,
        }

        # 2. Apply policies using the complete evaluation result
        self.policy.apply_policies(evaluation_result)
