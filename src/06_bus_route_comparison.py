"""Compare OSM's TfL bus route relations against the government's registered
current bus route numbers.

Two real corrections applied before computing a headline number (both caught
by inspecting the mismatch lists, not assumed away):

1. The initial unrestricted OSM query (any relation with route=bus in Greater
   London) pulls in Surrey, Hertfordshire, Kent, National Express, Flixbus and
   other operators' routes that happen to pass through London -- these are not
   part of the TfL-contracted network the government dataset describes, so
   comparing against them would understate the real match rate. Restricted to
   OSM relations tagged network=London Buses.
2. The government dataset's STATUS field includes FIRM and PROVISIONAL
   (future, not-yet-operating) routes alongside CURRENT ones -- only CURRENT
   is a fair comparison set for "does OSM have this route today".
3. Leading-zero ref formatting ("035" vs "35") was checked as a possible false
   mismatch (as Dublin found with a stray "DB 104" ref tag) -- verified to make
   no difference here once (1) and (2) are applied, so left undocumented as a
   real gap rather than a formatting artefact.
"""
import json

from geo_utils import load_geojson


def main() -> None:
    rel = load_geojson("../data/raw/osm_bus_route_relations.geojson")["features"]
    gov = load_geojson("../data/raw/gov_bus_routes.geojson")["features"]

    gov_current = set(f["properties"]["ROUTE"] for f in gov if f["properties"].get("STATUS") == "CURRENT")

    tfl_relations = [f for f in rel if f["properties"].get("network") == "London Buses"]
    osm_refs = set(f["properties"].get("ref") for f in tfl_relations if f["properties"].get("ref"))

    matched = osm_refs & gov_current
    osm_only = sorted(osm_refs - gov_current)
    gov_only = sorted(gov_current - osm_refs)

    summary = {
        "osm_relations_total_any_operator": len(rel),
        "osm_relations_network_london_buses": len(tfl_relations),
        "osm_distinct_refs_london_buses": len(osm_refs),
        "gov_distinct_current_routes": len(gov_current),
        "matched_route_count": len(matched),
        "gov_match_rate_pct": round(100 * len(matched) / len(gov_current), 1),
        "osm_match_rate_pct": round(100 * len(matched) / len(osm_refs), 1),
        "osm_only_refs": osm_only,
        "gov_only_refs_sample": gov_only[:40],
        "gov_only_count": len(gov_only),
        "note_on_gov_only": (
            "Most gov-only route codes carry non-standard-numeric prefixes "
            "(UL, Y, DL, TR, SL) typical of school, night, or route-branch "
            "variants -- worth a targeted OSM mapping pass, not necessarily "
            "evidence the physical route itself is unmapped under its parent number."
        ),
    }
    print(json.dumps(summary, indent=2))

    with open("../data/processed/bus_route_comparison.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("\nSaved bus_route_comparison.json")


if __name__ == "__main__":
    main()
