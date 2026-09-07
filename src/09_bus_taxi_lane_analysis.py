"""Two analyses on designated bus/taxi lanes:

1. Does London have taxi-only lanes, or is the Dublin pattern (every
   taxi-permitted lane is also a bus lane) also true here? Answered directly
   from the government VEHICLES field rather than assumed by convention.

2. Buffer-tolerant length-coverage gap analysis: what fraction of the
   government-documented bus lane network has a matching OSM-tagged designated
   lane nearby, and vice versa -- at several distance tolerances, per the
   Dublin lesson that a single-tolerance number can't distinguish a real
   tagging gap from independently-digitized lines that trace the same road.
"""
import json
from collections import Counter

from geo_utils import load_geojson, coverage_by_buffer_tolerance

THRESHOLDS = [5, 10, 15, 20, 30]


def vehicle_permission_analysis(gov_lanes: list) -> dict:
    vehicles = Counter(f["properties"].get("VEHICLES") for f in gov_lanes)
    taxi_permitted = sum(v for k, v in vehicles.items() if k and "taxi" in k.lower())
    bus_only_no_taxi = sum(v for k, v in vehicles.items() if k and "taxi" not in k.lower())
    total = len(gov_lanes)
    return {
        "total_gov_lane_segments": total,
        "distinct_vehicles_values": dict(vehicles.most_common()),
        "segments_permitting_taxi_pct": round(100 * taxi_permitted / total, 1),
        "segments_bus_lane_excluding_taxi_pct": round(100 * bus_only_no_taxi / total, 1),
        "finding": (
            f"{round(100 * taxi_permitted / total, 1)}% of government-documented bus lane "
            f"segments explicitly permit taxis; {round(100 * bus_only_no_taxi / total, 1)}% "
            f"are bus-only (or bus+cycle, excluding taxi) -- unlike Dublin, London does NOT "
            f"treat 'bus lane' and 'taxi-permitted lane' as fully interchangeable."
        ),
    }


def osm_taxi_tag_analysis(osm_lanes: list) -> dict:
    taxi_tagged = [f for f in osm_lanes if any(k.startswith("taxi") for k in f["properties"])]
    return {
        "total_osm_lane_ways": len(osm_lanes),
        "ways_with_any_taxi_tag": len(taxi_tagged),
        "pct_with_taxi_tag": round(100 * len(taxi_tagged) / len(osm_lanes), 1) if osm_lanes else None,
    }


def main() -> None:
    gov_lanes = load_geojson("../data/raw/gov_bus_lanes.geojson")["features"]
    osm_lanes = load_geojson("../data/raw/osm_bus_taxi_lanes.geojson")["features"]

    vpa = vehicle_permission_analysis(gov_lanes)
    ota = osm_taxi_tag_analysis(osm_lanes)

    print("=== Vehicle permission (government VEHICLES field) ===")
    print(json.dumps(vpa, indent=2))
    print("\n=== OSM taxi-tag coverage ===")
    print(json.dumps(ota, indent=2))

    print("\nComputing OSM-covers-gov coverage (gov lane length within N metres of an OSM lane)...")
    gov_covered_by_osm = coverage_by_buffer_tolerance(gov_lanes, osm_lanes, THRESHOLDS)
    print(json.dumps(gov_covered_by_osm, indent=2))

    print("\nComputing gov-covers-osm coverage (osm lane length within N metres of a gov lane)...")
    osm_covered_by_gov = coverage_by_buffer_tolerance(osm_lanes, gov_lanes, THRESHOLDS)
    print(json.dumps(osm_covered_by_gov, indent=2))

    out = {
        "vehicle_permission_analysis": vpa,
        "osm_taxi_tag_analysis": ota,
        "gov_length_covered_by_osm_at_threshold": gov_covered_by_osm,
        "osm_length_covered_by_gov_at_threshold": osm_covered_by_gov,
        "headline_gap_pct_gov_not_in_osm_at_15m": round(
            100 - gov_covered_by_osm["coverage_pct_by_threshold"]["15m"], 1
        ),
    }
    with open("../data/processed/bus_taxi_lane_analysis.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("\nSaved bus_taxi_lane_analysis.json")


if __name__ == "__main__":
    main()
