"""Check both boundary polygons agree closely, and check how many points in
each point dataset (gov + OSM bus stops, taxi ranks) fall outside the
government GLA boundary.

This is the independent-baseline check the Dublin analysis was missing until
a boundary-clipping bug was caught by comparing against a known-good baseline.
Here the check is run up front, before any comparison logic exists, rather
than being discovered as a bug afterwards: OSM data was already queried against
the OSM Greater London relation, so if a meaningful fraction of OSM points
fall outside the *government* GLA polygon, that is a real signal the two
boundaries disagree and every downstream percentage needs the caveat.
"""
import json

from shapely.geometry import Point

from geo_utils import load_geojson, boundary_polygon, feature_point


def outside_rate(features: list, polygon) -> dict:
    outside = 0
    for f in features:
        p = feature_point(f)
        if not polygon.contains(p):
            outside += 1
    return {"total": len(features), "outside_gla": outside, "outside_pct": round(100 * outside / len(features), 2)}


def main() -> None:
    gla = boundary_polygon("../data/raw/boundary_gla_gov.geojson")
    osm_boundary = boundary_polygon("../data/raw/boundary_greater_london_osm.geojson")

    print("GLA (gov) boundary area (deg^2, rough):", gla.area)
    print("OSM Greater London boundary area (deg^2, rough):", osm_boundary.area)
    iou = gla.intersection(osm_boundary).area / gla.union(osm_boundary).area
    print(f"Boundary intersection-over-union: {iou:.4f} (1.0 = identical polygons)")

    results = {"boundary_iou": round(iou, 4)}
    for name in ("gov_bus_stops", "osm_bus_stops", "gov_taxi_ranks", "osm_taxi_ranks"):
        feats = load_geojson(f"../data/raw/{name}.geojson")["features"]
        r = outside_rate(feats, gla)
        results[name] = r
        print(name, r)

    with open("../data/processed/boundary_check_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nSaved boundary_check_summary.json")


if __name__ == "__main__":
    main()
