"""Profile every field in every fetched dataset -- government and OSM -- before
any comparison logic is written. This step exists because the Dublin analysis
initially compared datasets on headline counts alone and missed columns that
turned out to matter (e.g. status/lifecycle fields that silently included
planned-but-not-yet-built infrastructure in a "current network" total).
"""
import json
from collections import Counter

DATASETS = [
    "gov_bus_stops", "gov_bus_routes", "gov_taxi_ranks", "gov_bus_lanes",
    "gov_cycle_routes", "gov_london_boroughs", "gov_cid_cycle_lane_track",
    "gov_cid_restricted_route",
    "osm_bus_stops", "osm_taxi_ranks", "osm_bus_route_relations",
    "osm_bus_route_ways", "osm_bus_taxi_lanes", "osm_cycling",
]


def profile(name: str) -> dict:
    with open(f"../data/raw/{name}.geojson", encoding="utf-8") as f:
        gj = json.load(f)
    features = gj["features"]
    field_stats = {}
    for feat in features:
        for k, v in feat["properties"].items():
            fs = field_stats.setdefault(k, {"non_null": 0, "distinct_sample": Counter()})
            if v is not None and v != "":
                fs["non_null"] += 1
                if len(fs["distinct_sample"]) < 25:
                    fs["distinct_sample"][str(v)] += 1
    out = {
        "n_features": len(features),
        "geometry_types": dict(Counter(f["geometry"]["type"] for f in features if f.get("geometry"))),
        "fields": {
            k: {
                "non_null": v["non_null"],
                "null_count": len(features) - v["non_null"],
                "sample_distinct_values": dict(v["distinct_sample"].most_common(15)),
            }
            for k, v in field_stats.items()
        },
    }
    return out


def main() -> None:
    profiles = {}
    for name in DATASETS:
        try:
            profiles[name] = profile(name)
            print(f"{name}: {profiles[name]['n_features']} features, {len(profiles[name]['fields'])} fields")
        except FileNotFoundError:
            print(f"SKIP {name}: not fetched yet")
    with open("../data/processed/column_profile.json", "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    print("\nSaved ../data/processed/column_profile.json")


if __name__ == "__main__":
    main()
