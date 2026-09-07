"""Match OSM bus stops against the government (TfL) bus stop register.

Primary match: exact NAPTAN ATCO code equality (naptan:AtcoCode on OSM,
NAPTAN_ATCO on the gov layer) -- both sides carry the same national stop
identifier, so this is a ground-truth match, not a spatial guess.

Fallback: for stops missing a code on either side, nearest-neighbor spatial
matching within a distance threshold, exactly as Dublin's stop_matching.py did
for its whole dataset. Reporting both numbers (code-match rate and the
distance distribution on the fallback set) is the cross-check -- if the two
methods disagreed wildly it would suggest a data problem, per the Dublin/Paris
lesson that headline percentages need a second, independently-derived check.
"""
import json

import numpy as np
from scipy.spatial import cKDTree

from geo_utils import load_geojson, feature_point, haversine_m, boundary_polygon

FALLBACK_THRESHOLD_M = 30.0


def main() -> None:
    gla = boundary_polygon("../data/raw/boundary_gla_gov.geojson")
    gov_all = load_geojson("../data/raw/gov_bus_stops.geojson")["features"]
    gov = [f for f in gov_all if gla.contains(feature_point(f))]
    print(f"Gov bus stops: {len(gov_all)} total, {len(gov)} inside GLA boundary "
          f"({len(gov_all) - len(gov)} excluded -- TfL-contracted routes crossing into neighbouring counties)")
    osm = load_geojson("../data/raw/osm_bus_stops.geojson")["features"]

    gov_by_code = {}
    for f in gov:
        code = f["properties"].get("NAPTAN_ATCO")
        if code:
            gov_by_code.setdefault(code, []).append(f)
    osm_by_code = {}
    for f in osm:
        code = f["properties"].get("naptan:AtcoCode")
        if code:
            osm_by_code.setdefault(code, []).append(f)

    matched_gov_ids, matched_osm_ids = set(), set()
    code_matches = []
    for code, gov_feats in gov_by_code.items():
        osm_feats = osm_by_code.get(code)
        if not osm_feats:
            continue
        gf, of = gov_feats[0], osm_feats[0]
        gp, op = feature_point(gf), feature_point(of)
        dist = haversine_m(gp.x, gp.y, op.x, op.y)
        code_matches.append(dist)
        matched_gov_ids.add(gf["properties"]["OBJECTID"])
        matched_osm_ids.add(of["properties"]["osm_id"])

    gov_remaining = [f for f in gov if f["properties"]["OBJECTID"] not in matched_gov_ids]
    osm_remaining = [f for f in osm if f["properties"]["osm_id"] not in matched_osm_ids]

    osm_pts = np.array([[feature_point(f).x, feature_point(f).y] for f in osm_remaining])
    fallback_matches = []
    if len(osm_remaining) and len(gov_remaining):
        tree = cKDTree(osm_pts)
        for gf in gov_remaining:
            gp = feature_point(gf)
            dist_deg, idx = tree.query([gp.x, gp.y], k=1)
            of = osm_remaining[idx]
            op = feature_point(of)
            dist_m = haversine_m(gp.x, gp.y, op.x, op.y)
            if dist_m <= FALLBACK_THRESHOLD_M:
                fallback_matches.append(dist_m)
                matched_gov_ids.add(gf["properties"]["OBJECTID"])
                matched_osm_ids.add(of["properties"]["osm_id"])

    all_dists = code_matches + fallback_matches
    summary = {
        "gov_total": len(gov),
        "osm_total": len(osm),
        "gov_with_atco_code": sum(1 for f in gov if f["properties"].get("NAPTAN_ATCO")),
        "osm_with_atco_code": sum(1 for f in osm if f["properties"].get("naptan:AtcoCode")),
        "code_matches": len(code_matches),
        "fallback_spatial_matches_within_30m": len(fallback_matches),
        "total_matched": len(all_dists),
        "gov_match_rate_pct": round(100 * len(matched_gov_ids) / len(gov), 1),
        "osm_match_rate_pct": round(100 * len(matched_osm_ids) / len(osm), 1),
        "median_distance_m_code_matches": round(float(np.median(code_matches)), 1) if code_matches else None,
        "median_distance_m_all_matches": round(float(np.median(all_dists)), 1) if all_dists else None,
        "gov_unmatched": len(gov) - len(matched_gov_ids),
        "osm_unmatched": len(osm) - len(matched_osm_ids),
    }
    print(json.dumps(summary, indent=2))

    with open("../data/processed/bus_stop_matching_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    for f in gov:
        f["properties"]["_matched"] = f["properties"]["OBJECTID"] in matched_gov_ids
    for f in osm:
        f["properties"]["_matched"] = f["properties"]["osm_id"] in matched_osm_ids

    with open("../data/processed/gov_bus_stops_classified.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": gov}, f)
    with open("../data/processed/osm_bus_stops_classified.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": osm}, f)
    print("Saved bus_stop_matching_summary.json + classified layers")


if __name__ == "__main__":
    main()
