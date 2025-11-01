# Model Improvements

1. Create a globall definition file that includes master definitions such as sector names. []
2. Create a base sector class so all sectors follow the same patthern. []
3. Make sure the power consumption is valid and causes demand to energey sector for each sector []
4. Move power allocation code to the energy sector instead of having it in the world system []
5. Add documentation separately for each sector and link to the architecture []
6. Extract sector dynamic equations and map them to world system definitions []
7. Document equations for manufacturing, and fuel generation sectors []
8. Make the policy configurations parameteric in the database []
9. Add policy description for Industrial Dust Coverage []



# Code Refactored

- World System Runner [x]
- UI Engine
- Components
    - assembly_robot.py []
    - energy_microgrid.py []
    - fuel_generator.py []
    - isru.py []
    - printing_robot.py []
    - rocket.py []
    - science_rover.py []
- event engine
    - event_bus.py [x]
- policy engine
    - metrics.py [x]
    - policy_protoco.py [x]
    - policy_engine.py [x]
    - environment_policies.py [x]
    - sceince_policies.py []
- sphere engine
    - construction_sector.py []
    - energy_sector.py []
    - equipment_manufacturing_sector.py []
    - manufacturing_sector.py []
    - scince_sector.py []
    - transportation_sector.py []
- world system
    - world_system.py []
    - world_system_builder.py []
    - world_system_defs.py []
    - evaluation_engine.py []


# Components Documented

- World System Runner [x]
- UI Engine
- Components
    - assembly_robot.py []
    - energy_microgrid.py []
    - fuel_generator.py []
    - isru.py []
    - printing_robot.py []
    - rocket.py []
    - science_rover.py []
- event engine
    - event_bus.py [x]
- policy engine
    - metrics.py []
    - policy_protoco.py []
    - policy_engine.py []
    - environment_policies.py []
    - sceince_policies.py []
- sphere engine
    - construction_sector.py []
    - energy_sector.py []
    - equipment_manufacturing_sector.py []
    - manufacturing_sector.py []
    - scince_sector.py []
    - transportation_sector.py []
- world system
    - world_system.py []
    - world_system_builder.py []
    - world_system_defs.py []
    - evaluation_engine.py []
