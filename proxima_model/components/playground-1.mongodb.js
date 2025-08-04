// MongoDB Playground
// Use Ctrl+Space inside a snippet or a string literal to trigger completions.

// The current database to use.
use('proxima_db');

// ISRU Extraction Agent Template
db.getCollection('component_templates').insertOne({
  "_id": "comp_isru_extractor",
  "name": "ISRU Extractor",
  "type": "isru",
  "subtype": "extractor",
  "sphere": "Technosphere",
  "config": {
    "max_power_usage_kWh": 15,  // Can handle both ice (5kWh) and regolith (10kWh) simultaneously
    "ice_extraction_power_kWh": 5,
    "ice_extraction_output_kg": 20,
    "regolith_extraction_power_kWh": 10,
    "regolith_extraction_output_kg": 100,
    "efficiency": 0.9
  }
});

// ISRU Generation Agent Template  
db.getCollection('component_templates').insertOne({
  "_id": "comp_isru_generator",
  "name": "ISRU Generator", 
  "type": "isru",
  "subtype": "generator",
  "sphere": "Technosphere",
  "config": {
    "max_power_usage_kWh": 65,  // Handles electrolysis (15kWh) + He3 extraction (50kWh)
    "electrolysis_power_kWh": 15,
    "electrolysis_water_input_kg": 2.7,
    "electrolysis_h2_output_kg": 0.3,
    "electrolysis_o2_output_kg": 2.4,
    "regolith_processing_input_kg": 100,
    "regolith_processing_o2_output_kg": 12,
    "regolith_processing_metal_output_kg": 10,
    "he3_extraction_regolith_input_kg": 500,
    "he3_extraction_power_kWh": 50,
    "he3_extraction_output_kg": 0.1,
    "efficiency": 0.85
  }
});
