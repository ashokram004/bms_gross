import json

with open('utils/venue_mapping.json') as f:
    m = json.load(f)
with open('duplicate removal tools/bms_all_venues.json') as f:
    bms = json.load(f)
with open('duplicate removal tools/district_all_venues.json') as f:
    dist = json.load(f)

print('='*60)
print('  VENUE MAPPING AUDIT')
print('='*60)

bms_total = bms['stats']['total_unique_venues']
dist_total = dist['stats']['total_unique_venues']
print(f"BMS total unique venues:       {bms_total}")
print(f"District total unique venues:  {dist_total}")

# Venues with/without coordinates
bms_with, bms_no = 0, 0
bms_all = {}
for sd in bms['states'].values():
    for cd in sd['cities'].values():
        for v in cd['venues']:
            code = v.get('VenueCode', '')
            if not code or code in bms_all: continue
            lat = float(v.get('VenueLatitude') or 0)
            lon = float(v.get('VenueLongitude') or 0)
            bms_all[code] = v
            if lat == 0 or lon == 0:
                bms_no += 1
            else:
                bms_with += 1

dist_with, dist_no = 0, 0
dist_all = {}
for sd in dist['states'].values():
    for cd in sd['cities'].values():
        for v in cd['venues']:
            cid = str(v.get('cinema_id', ''))
            if not cid or cid in dist_all: continue
            lat = float(v.get('lat') or 0)
            lon = float(v.get('lon') or 0)
            dist_all[cid] = v
            if lat == 0 or lon == 0:
                dist_no += 1
            else:
                dist_with += 1

print(f"\nBMS with lat/lon:              {bms_with}")
print(f"BMS WITHOUT lat/lon:           {bms_no}  (cannot be mapped)")
print(f"District with lat/lon:         {dist_with}")
print(f"District WITHOUT lat/lon:      {dist_no}  (cannot be mapped)")

# Mapping stats
matched = m['stats']['matched']
print(f"\nMatched pairs:                 {matched}")
print(f"Unmatched BMS (with coords):   {bms_with - matched}")
print(f"Unmatched District:            {dist_with - len(m['district_to_bms'])}")
print(f"Match rate (BMS w/ coords):    {matched/bms_with*100:.1f}%")
print(f"Match rate (District w/ crds): {len(m['district_to_bms'])/dist_with*100:.1f}%")

# Quality breakdown
details = m['match_details']
perfect = [d for d in details if d['combined'] >= 0.9]
high    = [d for d in details if 0.7 <= d['combined'] < 0.9]
medium  = [d for d in details if 0.4 <= d['combined'] < 0.7]
low     = [d for d in details if d['combined'] < 0.4]
print(f"\nMatch confidence breakdown:")
print(f"  Perfect (>= 0.9):   {len(perfect):>5}  ({len(perfect)/matched*100:.1f}%)")
print(f"  High    (0.7-0.9):  {len(high):>5}  ({len(high)/matched*100:.1f}%)")
print(f"  Medium  (0.4-0.7):  {len(medium):>5}  ({len(medium)/matched*100:.1f}%)")
print(f"  Low     (< 0.4):    {len(low):>5}  ({len(low)/matched*100:.1f}%)")

# Distance stats
avg_km = sum(d['distance_km'] for d in details) / len(details)
max_km = max(d['distance_km'] for d in details)
within_100m = sum(1 for d in details if d['distance_km'] <= 0.1)
within_50m  = sum(1 for d in details if d['distance_km'] <= 0.05)
print(f"\nDistance stats:")
print(f"  Avg distance:       {avg_km*1000:.0f}m")
print(f"  Max distance:       {max_km*1000:.0f}m")
print(f"  Within 50m:         {within_50m}  ({within_50m/matched*100:.1f}%)")
print(f"  Within 100m:        {within_100m}  ({within_100m/matched*100:.1f}%)")

# Spot-check: find potential missed matches by looking for BMS venues
# without mapping that share a city with unmapped District venues
import math, difflib

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

bms_mapped = set(m['bms_to_district'].keys())
dist_mapped = set(m['district_to_bms'].keys())

print(f"\n{'='*60}")
print("  POTENTIAL MISSED MATCHES (within 1.5km, name > 0.5)")
print(f"{'='*60}")

missed = []
for bms_code, bv in bms_all.items():
    if bms_code in bms_mapped: continue
    blat = float(bv.get('VenueLatitude') or 0)
    blon = float(bv.get('VenueLongitude') or 0)
    if blat == 0: continue
    for dist_id, dv in dist_all.items():
        if dist_id in dist_mapped: continue
        dlat = float(dv.get('lat') or 0)
        dlon = float(dv.get('lon') or 0)
        if dlat == 0: continue
        if abs(blat - dlat) > 0.015: continue
        if abs(blon - dlon) > 0.02: continue
        km = haversine_km(blat, blon, dlat, dlon)
        if km > 1.5: continue
        ratio = difflib.SequenceMatcher(None, bv['VenueName'].lower(), dv['cinema_name'].lower()).ratio()
        if ratio > 0.5:
            missed.append((ratio, km, bv['VenueName'], dv['cinema_name'], bms_code, dist_id))

missed.sort(key=lambda x: -x[0])
print(f"Found {len(missed)} potential missed pairs:")
for ratio, km, bn, dn, bc, dc in missed[:30]:
    print(f"  [{bc}] {bn[:40]:<40} <-> {dn[:40]:<40} (name={ratio:.2f}, dist={km*1000:.0f}m)")

# Venues only on one platform
print(f"\n{'='*60}")
print("  PLATFORM EXCLUSIVES (not on both)")
print(f"{'='*60}")
print(f"BMS-only venues (no mapping):  {len(bms_all) - matched}")
print(f"District-only (no mapping):    {len(dist_all) - len(m['district_to_bms'])}")
print("These are venues that exist on only one platform OR have")
print("no coordinate data - they are SKIPPED in mapping (expected).")
print("During merge, these will go through fuzzy fallback if needed.")
