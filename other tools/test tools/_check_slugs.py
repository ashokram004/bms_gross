import json
d = json.load(open('utils/bms_cities_config.json'))
cities = [c for s,cs in d.items() for c in cs]
print(f'Total cities: {len(cities)}')
blr = [c for c in cities if 'bang' in c.get('slug','').lower() or 'beng' in c.get('slug','').lower()]
for c in blr[:5]:
    print(c)
print('---First 5:')
for c in cities[:5]:
    print(f"  {c['name']}: slug={c.get('slug','?')}")
print('---Structure:', type(d), list(d.keys())[:3])
# Show a sample entry
for state, cs in d.items():
    if cs:
        print(f"State: {state}, first city: {cs[0]}")
        break
