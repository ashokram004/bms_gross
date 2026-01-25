import json

# Define file names
input_file = 'districtCitiesInput.txt'
output_file = 'district_cities_config.json'

def convert_to_state_dictionary():
    try:
        # Load the raw text file (assuming it contains valid JSON as shown in snippets) 
        with open(input_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Initialize the target dictionary structure
        state_dict = {}

        # Iterate through the cities provided in the "cities" list 
        for city_item in raw_data.get("cities", []):
            state_name = city_item.get("state_name") # 
            city_name = city_item.get("city_name")   # [cite: 224, 226, 227]
            city_slug = city_item.get("city_key")    # [cite: 222, 226, 227]

            # If the state isn't in our dictionary yet, create a new list for it
            if state_name not in state_dict:
                state_dict[state_name] = []
            
            # Append the city info to the relevant state
            state_dict[state_name].append({
                "name": city_name,
                "slug": city_slug
            })

        # Sort the states and cities alphabetically for a cleaner file
        sorted_state_dict = {state: sorted(cities, key=lambda x: x['name']) 
                             for state, cities in sorted(state_dict.items())}

        # Write the final dictionary to a JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(sorted_state_dict, f, indent=4)

        print(f"✅ Successfully converted and saved to {output_file}")

    except Exception as e:
        print(f"❌ Error during conversion: {e}")

if __name__ == "__main__":
    convert_to_state_dictionary()