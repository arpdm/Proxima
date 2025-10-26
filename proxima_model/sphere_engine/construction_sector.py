"""
Construction Sector Manager

Manages construction robots, shell production, and module assembly for lunar base expansion.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional, Any
from proxima_model.components.printing_robot import PrintingRobot, PrintingRobotMode
from proxima_model.components.assembly_robot import AssemblyRobot, AssemblyRobotMode

import logging

logger = logging.getLogger(__name__)


class ConstructionRequestStatus(Enum):
    """Status of construction requests."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class ConstructionRequest:
    """Represents a construction request."""

    requesting_sphere: str
    module_id: str
    shell_quantity_needed: int
    equipment_needed: Dict[str, int] = field(default_factory=dict)
    status: str = "queued"
    assigned_assembly_robot: Optional[AssemblyRobot] = None
    equipment_requested: bool = False

    def __post_init__(self):
        if self.shell_quantity_needed <= 0:
            raise ValueError("Shell quantity must be positive")


@dataclass
class ConstructionConfig:
    """Configuration for construction sector."""

    # TODO: These need to be added to policy engine and controlled by growth dynamically
    max_concurrent_projects: int = 3
    shell_storage_capacity: int = 10

    def __post_init__(self):
        if self.max_concurrent_projects < 0:
            raise ValueError("Max concurrent projects must be non-negative")


@dataclass
class ConstructionStocks:
    """Internal resource stocks for construction sector."""

    shells: int = 0


class ConstructionSector:
    """Manages construction robots and lunar base expansion."""

    # Equipment mapping: template_id -> equipment_type
    EQUIPMENT_MAP = {
        "comp_science_rover": "Science_Rover_EQ",
        "comp_energy_generator": "Energy_Generator_EQ",
        "comp_habitation_module": "Habitation_Module_EQ",
        "comp_isru_robot": "ISRU_Robot_EQ",
        "comp_rocket": "Rocket_EQ",
        "comp_printing_robot": "Printing_Robot_EQ",
        "comp_assembly_robot": "Assembly_Robot_EQ",
    }

    def __init__(self, model, config: Dict[str, Any], event_bus):
        self.model = model
        self.event_bus = event_bus

        # Load configuration
        config_kwargs = {}
        for field_name in ConstructionConfig.__dataclass_fields__.keys():
            if field_name in config:
                config_kwargs[field_name] = config[field_name]
        self._config = ConstructionConfig(**config_kwargs)

        # Initialize stocks
        self._stocks = ConstructionStocks()
        self.equipment_stock: Dict[str, int] = {eq_type: 0 for eq_type in self.EQUIPMENT_MAP.values()}

        # Construction queue
        self.construction_queue: List[ConstructionRequest] = []
        self.regolith_used_kg: float = 0.0

        # Initialize printing robots
        self.printing_robots: List[PrintingRobot] = []
        printing_configs = config.get("printing_robots", [])

        for robot_config in printing_configs:
            quantity = robot_config.get("quantity", 1)
            for _ in range(quantity):
                self.printing_robots.append(PrintingRobot(self.model, robot_config))

        # Initialize assembly robots
        self.assembly_robots: List[AssemblyRobot] = []
        assembly_configs = config.get("assembly_robots", [])

        for robot_config in assembly_configs:
            quantity = robot_config.get("quantity", 1)
            for _ in range(quantity):
                self.assembly_robots.append(AssemblyRobot(self.model, robot_config))

        # Subscribe to events
        self.event_bus.subscribe("construction_request", self.handle_construction_request)
        self.event_bus.subscribe("equipment_allocated", self.handle_equipment_allocation)

        # Metrics
        self.modules_completed_this_step = 0
        self.shells_produced_this_step = 0

    def handle_construction_request(self, requesting_sphere: str, module_id: str, shell_quantity: int) -> None:
        """Handle incoming construction request."""

        logger.info(
            f"Construction Sector received request from {requesting_sphere} for {module_id} ({shell_quantity} shells)"
        )

        # Determine equipment needed based on module_id
        equipment_type = self.EQUIPMENT_MAP.get(module_id)
        equipment_needed = {equipment_type: 1} if equipment_type else {}

        try:
            request = ConstructionRequest(
                requesting_sphere=requesting_sphere,
                module_id=module_id,
                shell_quantity_needed=shell_quantity,
                equipment_needed=equipment_needed,
                status=ConstructionRequestStatus.QUEUED.value,
            )
            self.construction_queue.append(request)
        except ValueError as e:
            logger.error(f"Invalid construction request: {e}")

    def handle_equipment_allocation(self, recipient_sector: str, equipment_type: str, quantity: int) -> None:
        """Handle equipment allocation from equipment manufacturing."""

        if recipient_sector == "construction":
            if equipment_type in self.equipment_stock:
                self.equipment_stock[equipment_type] += quantity
                logger.info(
                    f"Construction sector received {quantity} {equipment_type}, total: {self.equipment_stock[equipment_type]}"
                )
            else:
                logger.warning(f"Unknown equipment type {equipment_type} allocated to construction")

    def _process_construction_queue(self) -> None:
        """Process queued construction requests."""
        active_projects = 0

        for request in self.construction_queue[:]:
            if active_projects >= self._config.max_concurrent_projects:
                break

            if request.status == ConstructionRequestStatus.QUEUED.value:
                if self._start_construction_project(request):
                    active_projects += 1
            elif request.status == ConstructionRequestStatus.IN_PROGRESS.value:
                if self._advance_construction_project(request):
                    active_projects += 1

        # Remove completed requests from queue
        self.construction_queue = [
            r for r in self.construction_queue if r.status != ConstructionRequestStatus.COMPLETED.value
        ]

    def _start_construction_project(self, request: ConstructionRequest) -> bool:
        """Start a construction project if resources available."""

        # Check equipment availability
        equipment_available = all(
            self.equipment_stock.get(eq, 0) >= qty for eq, qty in request.equipment_needed.items()
        )

        if not equipment_available:

            missing_equipment = {
                eq: qty - self.equipment_stock.get(eq, 0)
                for eq, qty in request.equipment_needed.items()
                if self.equipment_stock.get(eq, 0) < qty
            }

            logger.debug(f"Cannot start {request.module_id}: missing equipment {missing_equipment}")

            if not request.equipment_requested:
                # Request missing equipment from equipment manufacturing
                for eq, qty_needed in missing_equipment.items():
                    self.event_bus.publish(
                        "equipment_request", requesting_sector="construction", equipment_type=eq, quantity=qty_needed
                    )
                request.equipment_requested = True

            return False

        if self._stocks.shells < request.shell_quantity_needed:
            logger.debug(
                f"Cannot start {request.module_id}: not enough shells ({self._stocks.shells} < {request.shell_quantity_needed})"
            )

            return False

        # Find available assembly robot
        available_assembly = next((r for r in self.assembly_robots if r.mode == AssemblyRobotMode.IDLE), None)
        if not available_assembly:
            logger.debug(f"Cannot start {request.module_id}: no available assembly robots")
            return False

        # Reserve equipment and shells
        for eq, qty in request.equipment_needed.items():
            self.equipment_stock[eq] -= qty
        self._stocks.shells -= request.shell_quantity_needed

        # Assign assembly robot
        request.assigned_assembly_robot = available_assembly
        logger.debug(f"Assigned assembly robot {available_assembly.unique_id} to {request.module_id}")

        if available_assembly.start_assembly(request.module_id):
            request.status = ConstructionRequestStatus.IN_PROGRESS.value
            logger.debug(f"Assembly robot {available_assembly.unique_id} started assembling {request.module_id}")
            logger.info(
                f"Started construction of {request.module_id} (equipment consumed: {request.equipment_needed}, shells consumed: {request.shell_quantity_needed})"
            )
            return True
        else:
            # Return resources if assembly failed to start
            for eq, qty in request.equipment_needed.items():
                self.equipment_stock[eq] += qty
            self._stocks.shells += request.shell_quantity_needed
            logger.debug(
                f"Assembly robot {available_assembly.unique_id} failed to start assembling {request.module_id}"
            )
            return False

    def _advance_construction_project(self, request: ConstructionRequest) -> bool:
        """Advance an in-progress construction project."""

        request.assigned_assembly_robot.step()

        # Check if assembly is complete
        if request.assigned_assembly_robot.mode == AssemblyRobotMode.IDLE:

            # Assembly complete

            logger.debug(
                f"Assembly robot {request.assigned_assembly_robot.unique_id} completed assembling {request.module_id}"
            )

            request.status = ConstructionRequestStatus.COMPLETED.value
            self.modules_completed_this_step += 1

            # Free robot
            request.assigned_assembly_robot = None

            # Notify sphere
            self.event_bus.publish(
                "module_created",
                sphere=request.requesting_sphere,
                module_id=request.module_id,
                equipment_consumed=request.equipment_needed,
            )

            logger.info(f"Completed construction of {request.module_id} for {request.requesting_sphere}")
            return False
        return True

    def _manage_printing_operations(self) -> None:
        """Manage printing robot operations - produce shells into stock."""
        for robot in self.printing_robots:
            if robot.mode == PrintingRobotMode.IDLE and self._stocks.shells < self._config.shell_storage_capacity:
                robot.start_printing()
            result = robot.step()

            if result["shell_produced"]:
                self._stocks.shells += 1
                self.regolith_used_kg += result["regolith_consumed"]
                self.shells_produced_this_step += 1

    def get_power_demand(self) -> float:
        """Calculate total power demand."""
        printing_power = sum(r.get_power_demand() for r in self.printing_robots)
        assembly_power = sum(r.get_power_demand() for r in self.assembly_robots)
        return printing_power + assembly_power

    def step(self, allocated_power: float) -> None:
        """Execute single simulation step."""
        # Reset metrics
        self.modules_completed_this_step = 0
        self.shells_produced_this_step = 0
        self.available_power = allocated_power

        # Produce shells in advance
        self._manage_printing_operations()

        # Process construction queue
        self._process_construction_queue()

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return {
            "printing_robots": len(self.printing_robots),
            "assembly_robots": len(self.assembly_robots),
            "queued_requests": len(self.construction_queue),
            "shells_in_stock": self._stocks.shells,
            "regolith_used_kg": self.regolith_used_kg,
            "modules_completed_this_step": self.modules_completed_this_step,
            "shells_produced_this_step": self.shells_produced_this_step,
            **{f"equipment_{k}": v for k, v in self.equipment_stock.items()},
        }
