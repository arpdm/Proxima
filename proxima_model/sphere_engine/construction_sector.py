"""
Construction Sector Manager

Manages construction robots, shell production, and module assembly for lunar base expansion.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional, Any
from proxima_model.components.printing_robot import PrintingRobot, PrintingRobotMode
from proxima_model.components.assembly_robot import AssemblyRobot, AssemblyRobotMode
from proxima_model.world_system.world_system_defs import EventType

import logging

logger = logging.getLogger(__name__)


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
class ConstructureSectorState:
    """Configuration and Current State for construction sector."""

    # TODO: These need to be added to policy engine and controlled by growth dynamically
    max_concurrent_projects: int = 3
    shell_storage_capacity: int = 10
    shells: int = 0
    regolith_used_kg: float = 0.0
    equipment_stock: Dict[str, int] = field(default_factory=lambda: {eq_type: 0 for eq_type in EQUIPMENT_MAP.values()})
    construction_queue: List[ConstructionRequest] = field(default_factory=list)

    def __post_init__(self):
        if self.max_concurrent_projects < 0:
            raise ValueError("Max concurrent projects must be non-negative")


class ConstructionSector:
    """Manages construction robots and lunar base expansion."""

    def __init__(self, model, config: Dict[str, Any], event_bus):
        self.model = model
        self.event_bus = event_bus
        self.power_demand_step = 0

        # Load configuration
        config_kwargs = {}
        for field_name in ConstructureSectorState.__dataclass_fields__.keys():
            if field_name in config:
                config_kwargs[field_name] = config[field_name]
        self._state = ConstructureSectorState(**config_kwargs)

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
        self.event_bus.subscribe(EventType.CONSTRUCTION_REQUEST.value, self.handle_construction_request)
        self.event_bus.subscribe(EventType.EQUIPMENT_ALLOCATED.value, self.handle_equipment_allocation)

        # Metrics
        self.modules_completed_this_step = 0
        self.shells_produced_this_step = 0
        self._queued_requests_loaded: Optional[int] = None

        # Hydrate from latest_state if provided (similar to science sector)
        latest_state_construction = config.get("latest_state") if isinstance(config, dict) else None
        if latest_state_construction:
            self._apply_latest_state(latest_state_construction)

    def handle_construction_request(self, requesting_sphere: str, module_id: str, shell_quantity: int) -> None:
        """Handle incoming construction request."""

        logger.info(
            f"Construction Sector received request from {requesting_sphere} for {module_id} ({shell_quantity} shells)"
        )

        # Determine equipment needed based on module_id
        equipment_type = EQUIPMENT_MAP.get(module_id)
        equipment_needed = {equipment_type: 1} if equipment_type else {}

        try:
            request = ConstructionRequest(
                requesting_sphere=requesting_sphere,
                module_id=module_id,
                shell_quantity_needed=shell_quantity,
                equipment_needed=equipment_needed,
                status=ConstructionRequestStatus.QUEUED.value,
            )
            self._state.construction_queue.append(request)
        except ValueError as e:
            logger.error(f"Invalid construction request: {e}")

    def handle_equipment_allocation(self, recipient_sector: str, equipment_type: str, quantity: int) -> None:
        """Handle equipment allocation from equipment manufacturing."""

        if recipient_sector == "construction":
            if equipment_type in self._state.equipment_stock:
                self._state.equipment_stock[equipment_type] += quantity
                logger.info(
                    f"Construction sector received {quantity} {equipment_type}, total: {self._state.equipment_stock[equipment_type]}"
                )
            else:
                logger.warning(f"Unknown equipment type {equipment_type} allocated to construction")

    def _process_construction_queue(self) -> None:
        """Process queued construction requests using all available assembly robots."""

        # First, advance all in-progress projects
        for request in self._state.construction_queue[:]:
            if request.status == ConstructionRequestStatus.IN_PROGRESS.value:
                self._advance_construction_project(request)

        # Then, assign new projects to any idle assembly robots
        for request in self._state.construction_queue[:]:
            if request.status == ConstructionRequestStatus.QUEUED.value:
                # Check if there's an available assembly robot
                available_robot = next((r for r in self.assembly_robots if r.mode == AssemblyRobotMode.IDLE), None)
                if available_robot:
                    self._start_construction_project(request)
                else:
                    # No idle robots available, stop trying to start new projects
                    break

        # Remove completed requests from queue
        self._state.construction_queue = [
            r for r in self._state.construction_queue if r.status != ConstructionRequestStatus.COMPLETED.value
        ]

    def _start_construction_project(self, request: ConstructionRequest) -> bool:
        """Start a construction project if resources available."""

        # Check equipment availability
        equipment_available = all(
            self._state.equipment_stock.get(eq, 0) >= qty for eq, qty in request.equipment_needed.items()
        )

        if not equipment_available:

            missing_equipment = {
                eq: qty - self._state.equipment_stock.get(eq, 0)
                for eq, qty in request.equipment_needed.items()
                if self._state.equipment_stock.get(eq, 0) < qty
            }

            logger.debug(f"Cannot start {request.module_id}: missing equipment {missing_equipment}")

            if not request.equipment_requested:
                # Request missing equipment from equipment manufacturing
                # TODO: Make requesting sector dynamic
                for eq, qty_needed in missing_equipment.items():
                    self.event_bus.publish(
                        EventType.EQUIPMENT_REQUEST.value,
                        requesting_sector="construction",
                        equipment_type=eq,
                        quantity=qty_needed,
                    )
                request.equipment_requested = True

            return False

        if self._state.shells < request.shell_quantity_needed:
            logger.debug(
                f"Cannot start {request.module_id}: not enough shells ({self._state.shells} < {request.shell_quantity_needed})"
            )

            return False

        # Find available assembly robot
        available_assembly = next((r for r in self.assembly_robots if r.mode == AssemblyRobotMode.IDLE), None)
        if not available_assembly:
            logger.debug(f"Cannot start {request.module_id}: no available assembly robots")
            return False

        # Reserve equipment and shells
        for eq, qty in request.equipment_needed.items():
            self._state.equipment_stock[eq] -= qty
        self._state.shells -= request.shell_quantity_needed

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
                self._state.equipment_stock[eq] += qty
            self._state.shells += request.shell_quantity_needed
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
                EventType.MODULE_COMPLETED.value,
                requesting_sphere=request.requesting_sphere,
                module_id=request.module_id,
            )

            logger.info(f"Completed construction of {request.module_id} for {request.requesting_sphere}")
            return False
        return True

    def _manage_printing_operations(self) -> None:
        """Manage printing robot operations - produce shells into stock."""
        for robot in self.printing_robots:
            if robot.mode == PrintingRobotMode.IDLE and self._state.shells < self._state.shell_storage_capacity:
                robot.start_printing()
            result = robot.step()

            if result["shell_produced"]:
                self._state.shells += 1
                self._state.regolith_used_kg += result["regolith_consumed"]
                self.shells_produced_this_step += 1

    def get_power_demand(self) -> float:
        """Calculate total power demand."""
        printing_power = sum(r.get_power_demand() for r in self.printing_robots)
        assembly_power = sum(r.get_power_demand() for r in self.assembly_robots)
        self.power_demand_step = printing_power + assembly_power
        return self.power_demand_step

    def _apply_latest_state(self, construction_state: Dict[str, Any]) -> None:
        """Restore construction sector stocks/state from latest_state snapshot."""

        # Stocks and usage
        self._state.shells = int(construction_state.get("shells_in_stock", self._state.shells))
        self._state.regolith_used_kg = float(construction_state.get("regolith_used_kg", self._state.regolith_used_kg))

        # Queued requests count (informational only; cannot reconstruct queue without details)
        if "queued_requests" in construction_state:
            try:
                self._queued_requests_loaded = int(construction_state.get("queued_requests", 0))
            except (TypeError, ValueError):
                self._queued_requests_loaded = None

        # Rebuild construction queue if full request data is provided
        queue_entries = construction_state.get("construction_queue", [])
        if isinstance(queue_entries, list):
            rebuilt_queue: List[ConstructionRequest] = []
            for entry in queue_entries:
                try:
                    status = entry.get("status", ConstructionRequestStatus.QUEUED.value)
                    if status == ConstructionRequestStatus.IN_PROGRESS.value:
                        # Cannot resume mid-assembly without robot binding; requeue it
                        status = ConstructionRequestStatus.QUEUED.value

                    req = ConstructionRequest(
                        requesting_sphere=entry.get("requesting_sphere", ""),
                        module_id=entry.get("module_id", ""),
                        shell_quantity_needed=max(1, int(entry.get("shell_quantity_needed", 0))),
                        equipment_needed=dict(entry.get("equipment_needed", {})),
                        status=status,
                        equipment_requested=bool(entry.get("equipment_requested", False)),
                    )
                    rebuilt_queue.append(req)
                except Exception as exc:  # skip malformed entries
                    logger.warning(f"Skipping malformed construction_queue entry during hydrate: {exc}")
            if rebuilt_queue:
                self._state.construction_queue = rebuilt_queue

        # Equipment stock (keys like equipment_Science_Rover_EQ)
        for key, value in construction_state.items():
            if key.startswith("equipment_"):
                eq_type = key.replace("equipment_", "")
                self._state.equipment_stock[eq_type] = int(value)

        # Queued requests count is informational only; we can't reconstruct queue without details.
        # Per-step counters reset each run
        self.modules_completed_this_step = 0
        self.shells_produced_this_step = 0

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
        from proxima_model.components.assembly_robot import AssemblyRobotMode

        assembly_robots_working = sum(1 for r in self.assembly_robots if r.mode == AssemblyRobotMode.ASSEMBLING)

        # Use loaded queued_requests if provided and no live queue yet; otherwise live queue length
        queued_requests = (
            self._queued_requests_loaded
            if self._queued_requests_loaded is not None and len(self._state.construction_queue) == 0
            else len(self._state.construction_queue)
        )

        # Serialize queue for persistence / resume
        serialized_queue = [
            {
                "requesting_sphere": r.requesting_sphere,
                "module_id": r.module_id,
                "shell_quantity_needed": r.shell_quantity_needed,
                "equipment_needed": r.equipment_needed,
                "status": r.status,
                "equipment_requested": r.equipment_requested,
            }
            for r in self._state.construction_queue
        ]

        return {
            "printing_robots": len(self.printing_robots),
            "assembly_robots": len(self.assembly_robots),
            "assembly_robots_working": assembly_robots_working,
            "queued_requests": queued_requests,
            "construction_queue": serialized_queue,
            "shells_in_stock": self._state.shells,
            "regolith_used_kg": self._state.regolith_used_kg,
            "power_demand_kw_step": self.power_demand_step,
            "modules_completed_this_step": self.modules_completed_this_step,
            "shells_produced_this_step": self.shells_produced_this_step,
            **{f"equipment_{k}": v for k, v in self._state.equipment_stock.items()},
        }
