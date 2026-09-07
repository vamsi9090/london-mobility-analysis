"""Match OSM taxi ranks (amenity=taxi) against the TfL taxi rank register.

No shared ID scheme exists between the two (unlike bus stops' NAPTAN code), so
this is nearest-neighbor spatial matching only -- exactly Dublin's approach for
taxi infrastructure. Reported for two OSM subsets separately, because OSM's
amenity=taxi tag is used both for physical taxi ranks (a curbside waiting area)
and for minicab/taxi-firm offices (a business with a phone number, not
necessarily a marked rank) -- conflating them would overstate or understate the
match rate depending on which way the confusion cuts. Real ambiguity in the
source tagging, documented rather than silently resolved.
"""
import json

import numpy as np
from scipy.spatial import cKDTree

from geo_utils import load_geojson, feature_point, haversine_m, boundary_polygon

THRESHOLD_M = 50.0


def match(gov_feats, osm_feats, threshold_m):
    if not osm_feats or not gov_feats:
        return [], set(), set()
    osm_pts = np.array([[feature_point(f).x, feature_point(f).y] for f in osm_feats])
    tree = cKDTree(osm_pts)
    dists, matched_gov, matched_osm = [], set(), set()
    for i, gf in enumerate(gov_feats):
        gp = feature_point(gf)
        _, idx = tree.query([gp.x, gp.y], k=1)
        of = osm_feats[idx]
        op = feature_point(of)
        d = haversine_m(gp.x, gp.y, op.x, op.y)
        if d <= threshold_m:
            dists.append(d)
            matched_gov.add(i)
            matched_osm.add(idx)
    return dists, matched_gov, matched_osm


def main() -> None:
    gla = boundary_polygon("../data/raw/boundary_gla_gov.geojson")
    gov_all = load_geojson("../data/raw/gov_taxi_ranks.geojson")["features"]
    gov_active = [f for f in gov_all if f["properties"].get("TAXI_STATUS") == "A" and gla.contains(feature_point(f))]
    print(f"Gov taxi ranks: {len(gov_all)} total, {len(gov_active)} active + inside GLA "
          f"({len(gov_all) - len(gov_active)} excluded: suspended status or outside boundary)")

    osm_all = load_geojson("../data/raw/osm_taxi_ranks.geojson")["features"]
    is_business_like = lambda f: bool(f["properties"].get("phone") or f["properties"].get("website")
                                       or f["properties"].get("opening_hours"))
    osm_rank_like = [f for f in osm_all if not is_business_like(f)]
    print(f"OSM amenity=taxi nodes: {len(osm_all)} total, {len(osm_rank_like)} without business-identifying "
          f"tags (phone/website/opening_hours) -- treated as the physical-rank-like subset")

    results = {}
    matched_gov_final, matched_osm_final = set(), set()
    for label, osm_feats in (("all_amenity_taxi_nodes", osm_all), ("rank_like_subset_only", osm_rank_like)):
        dists, matched_gov, matched_osm = match(gov_active, osm_feats, THRESHOLD_M)
        results[label] = {
            "osm_candidate_count": len(osm_feats),
            "matched": len(dists),
            "gov_match_rate_pct": round(100 * len(matched_gov) / len(gov_active), 1),
            "osm_match_rate_pct": round(100 * len(matched_osm) / len(osm_feats), 1) if osm_feats else None,
            "median_distance_m": round(float(np.median(dists)), 1) if dists else None,
        }
        if label == "rank_like_subset_only":
            matched_gov_final = matched_gov
            matched_osm_final = {osm_feats[i]["properties"]["osm_id"] for i in matched_osm}
    print(json.dumps(results, indent=2))

    with open("../data/processed/taxi_rank_matching_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    for i, gf in enumerate(gov_active):
        gf["properties"]["_matched"] = i in matched_gov_final
    for f in osm_rank_like:
        f["properties"]["_matched"] = f["properties"]["osm_id"] in matched_osm_final

    with open("../data/processed/gov_taxi_ranks_classified.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": gov_active}, f)
    with open("../data/processed/osm_taxi_ranks_classified.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": osm_rank_like}, f)
    print("Saved taxi_rank_matching_summary.json + classified layers for the map")


if __name__ == "__main__":
    main()
