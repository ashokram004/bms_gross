import json
import os

def generate_bms_config(input_file, output_file):
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"❌ Error: Input file '{input_file}' not found.")
        return

    print(f"📂 Reading raw text data from {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        try:
            # Read the entire text content from the .txt file
            text_content = f.read()
            # Convert the text string into a JSON object
            raw_data = json.loads(text_content)
        except json.JSONDecodeError as e:
            print(f"❌ Error: The content of the .txt file is not valid JSON. {e}")
            return

    # Initialize structure
    state_map = {}
    
    # BMS data is split into TopCities and OtherCities
    bms_root = raw_data.get("BookMyShow", {})
    city_lists = [bms_root.get("TopCities", []), bms_root.get("OtherCities", [])]
    
    total_cities = 0
    print("⚙️ Processing cities and grouping by State...")

    for city_list in city_lists:
        for entry in city_list:
            state_name = entry.get("StateName")
            city_name = entry.get("RegionName")
            city_slug = entry.get("RegionSlug")
            
            if not state_name or not city_name or not city_slug:
                continue
                
            state_name = state_name.strip().title()
            
            if state_name not in state_map:
                state_map[state_name] = []
            
            city_obj = {
                "name": city_name,
                "slug": city_slug
            }
            
            # Avoid duplicate slugs per state
            existing_slugs = {c['slug'] for c in state_map[state_name]}
            if city_slug not in existing_slugs:
                state_map[state_name].append(city_obj)
                total_cities += 1

    # Sorting
    for state in state_map:
        state_map[state].sort(key=lambda x: x['name'])
    
    sorted_map = dict(sorted(state_map.items()))

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)

    # Save as clean JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sorted_map, f, indent=4, ensure_ascii=False)

    print(f"✅ Success! Processed {total_cities} cities across {len(sorted_map)} states.")
    print(f"📄 Clean config saved to: {output_file}")

# --- EXECUTION ---
if __name__ == "__main__":
    # Change these paths if your filenames are different
    INPUT_FILENAME = "bmsCitiesInput.txt" 
    OUTPUT_FILENAME = "bms_cities_config.json"
    
    generate_bms_config(INPUT_FILENAME, OUTPUT_FILENAME)