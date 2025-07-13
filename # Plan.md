# Phase 1

**Objective:** Establish the foundation of World System Beta using Agent-Based Modeling (ABM) and Discrete Event Simulations (DES) to model dynamic interactions, emergent behaviors, and systemic dependencies. The infrastructure needs to be in place from get go for growth, expansion and adaptiveness

1. Create local database
    - World System Component
        - Configuration for each component (can be updated)
    - World System environment
        - World system and its environmental specs
    - World System State Space
        - Goals
        - Perfomance Metrics
        - Characteristics of world system
        - Latest world system state (the module can resume from last known good state)
    - Events
        - Pre-loaded even timeline
        - Intrudcoude events (random)
    - Availanle Policies 
        - The world system can update the policy while running and optimizing
2. Create Proxima runneer engine
    - Constructs world system by pulling in from the server
    - World system byilding shoyld be fully dynamic
    - After construction runs the world system model 
3. Logger
    - Loggs data to CSV
    - Updates the last known system state to the server
4. Visualizer Engine
    - Live dashboard that pulls in live information
    - Live dashboard should be detached enough that later can be pulling data from large onlie data server.
    - Static dashboard at the end of the run
5. Post Processor
6. Complexity Engine
    - Will have its own executor
    - Mostly post processing

# Phase 2
