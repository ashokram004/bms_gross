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
MAX_DISTANCE_KM    = 1.5
MIN_COMBINED_SCORE = 0.25
LAT_PREFILTER      = 0.015   # ~1.6km, skip haversine for obvious non-matches
LON_PREFILTER      = 0.02    # ~1.6km at Indian latitudes

# Manual overrides for venues with broken GPS (>1.5km apart) but confirmed same
# Format: {bms_venue_code: district_cinema_id}
MANUAL_OVERRIDES = {
    'IPCM': '1039499',    # IP Cinemas: IP Vijaya Mall, Varanasi (1710m GPS offset)
    'PBOX': '51932',      # FUN Cinemas Playbox Cinema: Dimapur (1877m GPS offset)
    'MPDX': '1016291',    # MPT DDX Drive in Cinema: Bhopal (1937m GPS offset)
    'KAWS': '48675',      # Kalpana Cine World: Sonari (1698m GPS offset)
    'GDMT': '876',        # Gold Cinema: Mathura (111m, noise-word identity)
    'CPEB': '128',        # Cinepolis: Binnypet Mall (423m, name split mismatch)
    'TCPK': '9530',       # Thrilok Cinemas: Pandalam (1517m GPS offset)
    'CSQS': '58318',      # Cine Square Cinemas: Shirpur (1543m GPS offset)
    'PLTT': '1992',       # Palace Theatre: Tiruchirappalli/Kulittalai (71m, noise-word identity)
}

# Pairs confirmed as FALSE POSITIVES during manual review — block these specific matches
# Format: {bms_venue_code: district_cinema_id}
EXCLUDED_PAIRS = {
    ('MTLM', '22684'),    # "Mani Talkies" ≠ "K K Cinemas" (Minjur, 152m)
    ('SLRT', '1102120'),  # "Laxmi 70MM" ≠ "Mythri Theatres Ganesh 70MM" (Shamshabad, 617m)
    ('NLTC', '1037496'),  # "National Theatre" ≠ "Vidya Theatre" (Tambaram, 478m)
    ('GKGM', '1020826'),  # "Gayathiri Cinemas" ≠ "Alankar Theatre" (Maduranthakam, 574m)
    ('ANAC', '4184'),     # "Anna Cinemas" ≠ "Devi Cineplex" (Chennai, 124m — 'Anna' is street name)
    ('APCY', '24929'),    # "Asian Paradise Cinemas" ≠ "Prathima Multiplex" (Karimnagar, 935m)
    ('PAAD', '4881'),     # "Parameswara 70MM" ≠ "SVC Rama Krishna 70MM" (Shadnagar, 683m)
    ('SRTW', '1039878'),  # "Sri Rama 70mm" ≠ "Mythri Theatres Srinivasa 70MM" (Wanaparthy, 764m)
    ('ASHN', '14166'),    # "Asian Cinemart" ≠ "Sangeetha Theatre" (RC Puram, 1186m)
    ('ATTK', '1082832'),  # "Annapurna Picture Palace" ≠ "Sri Raja Rajeshwari Picture Palace" (Narsapur, 188m)
    ('BDCG', '47385'),    # "Bhumika Digital: Gandhinagar" ≠ "Bhoomika Theatre: Bengaluru" (DIFFERENT CITIES)
    ('SISD', '9887'),     # "SSR Cinemas" ≠ "Durgapur Cinema" (Durgapur, 361m)
    ('AMZB', '1041690'),  # "Asian Sri Mohan" ≠ "Asian Mukta A2, Sri Venkateswara Cinemax" (Zaheerabad, 700m)
    ('AVMT', '3896'),     # "AVM Cinemas" ≠ "Sri Kumari Cinemas" (Uthukkottai, 31m)
    ('RTDM', '4903'),     # "Ravi A/C 4K Laser" ≠ "Sai Chitra Theatre" (Madanapalle, 46m)
    ('PTHK', '1102072'),  # "Prasanthi Theatre" ≠ "Sri Koteswara Theatre" (Kandukur, 24m)
    ('PKHC', '1102077'),  # "Prakash Cinema" ≠ "Kailash Cinemas" (Salem, 21m)
}

# Noise words stripped before token comparison
NOISE_WORDS = frozenset({
    # Technical specs
    'a/c', 'ac', '2k', '4k', 'hdr', 'dolby', 'atmos', 'dts', 'digital',
    'laser', '7.1', 'ultrasound', '3d', 'imax', 'projection',
    'screen', 'screens', 'deluxe', 'premium', 'gold', 'platinum',
    'only', 'recliners', 'sofa', 'seating',
    # Common words
    'and', 'the', 'of', 'in', 'at', 'on', 'with', 'new', 'mini',
    # Venue type words
    'cinemas', 'cinema', 'theatre', 'theater', 'theaters', 'theatres',
    'multiplex', 'mall', 'talkies', 'complex', 'picture', 'palace', 'house',
    # Address words (District names often have these, BMS doesn't)
    'near', 'road', 'street', 'colony', 'nagar', 'market', 'marg',
    'highway', 'stand', 'bus', 'stop', 'old', 'opp', 'opposite',
    'chowk', 'tower', 'sector', 'main', 'alias', 'plaza',
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


def _split_alphanum(token):
    """Split mixed alpha+digit tokens: 'nh22' → ['nh','22'], 'pvr' → ['pvr']."""
    parts = re.findall(r'[a-z]+|\d+', token)
    return parts if len(parts) > 1 else [token]


def clean_tokens(raw_name, city=''):
    """Lowercase, strip punctuation/noise/city tokens → set of meaningful words.
    Falls back to keeping noise words if stripping them empties the set."""
    name       = re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', raw_name.lower())
    raw_tokens = name.split()
    # Split mixed alphanumeric tokens (nh22 → nh + 22)
    expanded = []
    for t in raw_tokens:
        expanded.extend(_split_alphanum(t))
    all_tokens = [t for t in expanded if len(t) > 1]
    tokens     = [t for t in all_tokens if t not in NOISE_WORDS]
    if not tokens:
        # Name is entirely noise words (e.g. "Gold Cinema") — keep them all
        tokens = all_tokens
        return set(tokens)          # skip city stripping to preserve identity
    if city:
        city_toks = set(re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', city.lower()).split())
        result    = [t for t in tokens if t not in city_toks]
        if result:
            tokens = result         # only strip city if tokens remain
    return set(tokens)


def name_similarity(bms_name, dist_name, bms_city='', dist_city=''):
    """Fuzzy token Dice coefficient — matches tokens even with slight spelling diffs.
    Falls back to raw SequenceMatcher (penalised) when token Dice gives 0."""
    bt = clean_tokens(bms_name, bms_city)
    dt = clean_tokens(dist_name, dist_city)
    if not bt or not dt:
        # Both empty after stripping — use raw name comparison
        cb = re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', bms_name.lower()).strip()
        cd = re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', dist_name.lower()).strip()
        return difflib.SequenceMatcher(None, cb, cd).ratio() * 0.4
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
    dice = (2 * matches) / (len(bt) + len(dt))
    if dice == 0:
        # No token overlap — try raw name comparison as fallback (penalised)
        cb = re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', bms_name.lower()).strip()
        cd = re.sub(r'[:\-,&()\[\]/.\'\"]', ' ', dist_name.lower()).strip()
        return difflib.SequenceMatcher(None, cb, cd).ratio() * 0.35
    return dice


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

            if (bms_code, dist_id) in EXCLUDED_PAIRS:
                continue

            ns       = name_similarity(bv['name'], dv['name'], bv['city'], dv['city'])

            # Require higher name similarity for distant venues to avoid false positives
            if km < 0.05:          # Within 50m — same building, allow lower name match
                min_ns = 0.15
            elif km < 0.2:         # Within 200m — nearby, moderate threshold
                min_ns = 0.25
            else:                  # Farther — require strong name evidence
                min_ns = 0.35
            if ns < min_ns:
                continue

            # Additive score: name is primary (85%), distance is tiebreaker (15%)
            combined = ns * 0.85 + (1 - km / MAX_DISTANCE_KM) * 0.15

            if combined >= MIN_COMBINED_SCORE:
                all_candidates.append((combined, ns, km, bms_code, dist_id))

    # Phase 2: Greedy 1:1 assignment — highest confidence first
    all_candidates.sort(key=lambda x: -x[0])
    used_bms      = set()
    used_dist     = set()
    mapping       = {}
    match_details = []

    # Apply manual overrides first (GPS-broken pairs)
    for bms_code, dist_id in MANUAL_OVERRIDES.items():
        if bms_code in bms_venues and dist_id in dist_venues:
            mapping[bms_code] = dist_id
            used_bms.add(bms_code)
            used_dist.add(dist_id)
            km = haversine_km(bms_venues[bms_code]['lat'], bms_venues[bms_code]['lon'],
                              dist_venues[dist_id]['lat'], dist_venues[dist_id]['lon'])
            match_details.append({
                'bms_code':     bms_code,
                'bms_name':     bms_venues[bms_code]['name'],
                'dist_id':      dist_id,
                'dist_name':    dist_venues[dist_id]['name'],
                'distance_km':  round(km, 4),
                'name_score':   1.0,
                'combined':     1.0,
                'source':       'manual_override',
            })

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
