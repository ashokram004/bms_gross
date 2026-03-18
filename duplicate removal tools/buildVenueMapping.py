"""
Builds a venue mapping between BMS VenueCode and District cinema_id.

Matching strategy:
  1. For each BMS venue with lat/lon, find District venues within 0.5km (Haversine)
  2. Score candidates by name similarity (token Jaccard + SequenceMatcher hybrid)
  3. Distance-weighted combined score must exceed threshold
  4. Best match wins; conflicts resolved by score

Output: utils/venue_mapping.json
"""

import json, math, re, os, difflib

# ── Paths ─────────────────────────────────────────────────────────────────────
BMS_PATH    = os.path.join(os.path.dirname(__file__), '..', 'duplicate removal tools', 'bms_all_venues.json')
DIST_PATH   = os.path.join(os.path.dirname(__file__), '..', 'duplicate removal tools', 'district_all_venues.json')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'utils', 'venue_mapping.json')

# ── Matching parameters ───────────────────────────────────────────────────────
MAX_DISTANCE_KM    = 0.5
MIN_COMBINED_SCORE = 0.20
LAT_PREFILTER      = 0.005   # ~0.55km, skip haversine for obvious non-matches
LON_PREFILTER      = 0.007   # ~0.55km at Indian latitudes

# Noise words stripped before token comparison
NOISE_WORDS = frozenset({
    'a/c', 'ac', '2k', '4k', 'hdr', 'dolby', 'atmos', 'dts', 'digital',
    'laser', '7.1', 'ultrasound', '3d', 'imax', 'projection',
    'screen', 'screens', 'deluxe', 'premium', 'gold', 'platinum',
    'only', 'recliners', 'sofa', 'seating', 'and', 'the', 'of', 'in',
    'at', 'on', 'with', 'new', 'mini', 'cinemas', 'cinema', 'theatre',
    'theater', 'theaters', 'theatres', 'multiplex', 'mall', 'talkies',
    'complex', 'picture', 'palace', 'house',
})

# ── Utilities ─────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R    = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = (math.sin(dlat / 2) ** 2 +
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
            math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def clean_tokens(raw_name, city=''):
    """Lowercase, strip punctuation/noise/city tokens → set of meaningful words."""
    name   = re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', raw_name.lower())
    tokens = [t for t in name.split() if t not in NOISE_WORDS and len(t) > 1]
    if city:
        city_toks = set(re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', city.lower()).split())
        tokens = [t for t in tokens if t not in city_toks]
    return set(tokens)


def name_similarity(bms_name, dist_name, bms_city='', dist_city=''):
    """Fuzzy token Dice coefficient — matches tokens even with slight spelling diffs."""
    bt = clean_tokens(bms_name, bms_city)
    dt = clean_tokens(dist_name, dist_city)
    if not bt or not dt:
        return 0.0
    # For each BMS token, find a fuzzy match in District tokens (SequenceMatcher > 0.8)
    matches = 0
    used    = set()
    for a in bt:
        for b in dt:
            if b in used:
                continue
            if a == b or (len(a) > 2 and len(b) > 2 and
                          difflib.SequenceMatcher(None, a, b).ratio() > 0.8):
                matches += 1
                used.add(b)
                break
    return (2 * matches) / (len(bt) + len(dt))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    with open(BMS_PATH, encoding='utf-8') as f:
        bms_data = json.load(f)
    with open(DIST_PATH, encoding='utf-8') as f:
        dist_data = json.load(f)

    # Extract unique venues (deduplicate by code/id)
    bms_venues = {}
    for state_data in bms_data['states'].values():
        for city_data in state_data['cities'].values():
            for v in city_data['venues']:
                code = v.get('VenueCode', '')
                if not code or code in bms_venues:
                    continue
                lat = float(v.get('VenueLatitude') or 0)
                lon = float(v.get('VenueLongitude') or 0)
                if lat == 0 or lon == 0:
                    continue
                bms_venues[code] = {
                    'name': v['VenueName'], 'lat': lat, 'lon': lon,
                    'city': v.get('City', ''), 'pincode': v.get('PostalCode', ''),
                }

    dist_venues = {}
    for state_data in dist_data['states'].values():
        for city_data in state_data['cities'].values():
            for v in city_data['venues']:
                cid = str(v.get('cinema_id', ''))
                if not cid or cid in dist_venues:
                    continue
                lat = float(v.get('lat') or 0)
                lon = float(v.get('lon') or 0)
                if lat == 0 or lon == 0:
                    continue
                dist_venues[cid] = {
                    'name': v['cinema_name'], 'lat': lat, 'lon': lon,
                    'city': v.get('city_label', ''), 'pincode': v.get('pincode', ''),
                }

    print(f"BMS venues with coordinates:      {len(bms_venues)}")
    print(f"District venues with coordinates:  {len(dist_venues)}")

    # ── Build mapping (greedy 1:1 assignment) ─────────────────────────────────
    dist_list      = list(dist_venues.items())
    all_candidates = []

    # Phase 1: Find ALL potential matches above threshold
    for bms_code, bv in bms_venues.items():
        for dist_id, dv in dist_list:
            if abs(bv['lat'] - dv['lat']) > LAT_PREFILTER:
                continue
            if abs(bv['lon'] - dv['lon']) > LON_PREFILTER:
                continue

            km = haversine_km(bv['lat'], bv['lon'], dv['lat'], dv['lon'])
            if km > MAX_DISTANCE_KM:
                continue

            ns       = name_similarity(bv['name'], dv['name'], bv['city'], dv['city'])
            combined = ns * (1 - km / MAX_DISTANCE_KM)

            if combined >= MIN_COMBINED_SCORE:
                all_candidates.append((combined, ns, km, bms_code, dist_id))

    # Phase 2: Greedy 1:1 assignment — highest confidence first
    all_candidates.sort(key=lambda x: -x[0])
    used_bms      = set()
    used_dist     = set()
    mapping       = {}
    match_details = []

    for combined, ns, km, bms_code, dist_id in all_candidates:
        if bms_code in used_bms or dist_id in used_dist:
            continue
        mapping[bms_code] = dist_id
        used_bms.add(bms_code)
        used_dist.add(dist_id)
        match_details.append({
            'bms_code':     bms_code,
            'bms_name':     bms_venues[bms_code]['name'],
            'dist_id':      dist_id,
            'dist_name':    dist_venues[dist_id]['name'],
            'distance_km':  round(km, 4),
            'name_score':   round(ns, 3),
            'combined':     round(combined, 3),
        })

    # Reverse mapping
    reverse = {}
    for bms_code, dist_id in mapping.items():
        if dist_id not in reverse:
            reverse[dist_id] = bms_code

    # ── Stats ─────────────────────────────────────────────────────────────────
    matched_count    = len(mapping)
    unmatched_bms    = len(bms_venues) - matched_count
    unmatched_dist   = len(dist_venues) - len(reverse)

    print(f"\n{'='*60}")
    print(f"  Matched:            {matched_count}")
    print(f"  Unmatched BMS:      {unmatched_bms}")
    print(f"  Unmatched District: {unmatched_dist}")
    print(f"{'='*60}")

    # ── Save ──────────────────────────────────────────────────────────────────
    output = {
        'bms_to_district': mapping,
        'district_to_bms': reverse,
        'stats': {
            'bms_venues_total':           len(bms_venues),
            'district_venues_total':      len(dist_venues),
            'matched':                    matched_count,
            'unmatched_bms':              unmatched_bms,
            'unmatched_district':         unmatched_dist,
            'match_rate_bms':             f"{matched_count/len(bms_venues)*100:.1f}%",
            'match_rate_district':        f"{len(reverse)/len(dist_venues)*100:.1f}%",
        },
        'match_details': match_details,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {OUTPUT_PATH}")

    # ── Sample output ─────────────────────────────────────────────────────────
    print(f"\n=== Sample Matches (first 25) ===")
    for m in match_details[:25]:
        print(f"  {m['bms_name'][:40]:<40} <-> {m['dist_name'][:40]:<40} "
              f"({m['distance_km']}km, name={m['name_score']}, comb={m['combined']})")

    # Show some unmatched BMS venues
    unmatched = [c for c in bms_venues if c not in mapping]
    if unmatched:
        print(f"\n=== Sample Unmatched BMS (first 15) ===")
        for code in unmatched[:15]:
            v = bms_venues[code]
            print(f"  [{code}] {v['name']:<45} ({v['city']})")


if __name__ == '__main__':
    main()
