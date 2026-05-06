"""Print all mapped pairs for manual verification."""
import json, os

MAP_PATH = os.path.join(os.path.dirname(__file__), '..', 'utils', 'venue_mapping.json')

with open(MAP_PATH, encoding='utf-8') as f:
    m = json.load(f)

details = m['match_details']
print(f"Total mappings: {len(details)}\n")

for i, d in enumerate(details):
    bms = d['bms_name'][:52]
    dist = d['dist_name'][:55]
    km = d['distance_km']
    ns = d['name_score']
    code = d['bms_code']
    did = d['dist_id']
    src = d.get('source', '')
    flag = ' MANUAL' if src == 'manual_override' else ''
    print(f"{i+1:4d} | {code:5s} | {did:>8s} | {km:7.3f}km | ns={ns:.3f} | {bms:<52s} <-> {dist}{flag}")
