"""Classify cycling infrastructure into three real-world types on both sides
-- OSM (from tags) and government (from the CID's own boolean flags, which
already encode exactly this distinction) -- then measure length and
buffer-tolerant coverage gap per type. Doing the 3-way split matters because a
naive single "cycling infrastructure" total conflates a physically-segregated
track with a painted on-road lane with a shared footway, three very different
things for a cyclist -- Dublin found that skipping this split alone can
overstate or understate a "gap" by several times over.

OSM classification (priority order, first match wins):
  A. dedicated_track  -- highway=cycleway with an explicit non-shared signal
                          (segregated=yes, or no foot=designated/yes), or any
                          cycleway(:left/right/both)=track/separate value.
  B. on_road_lane     -- a lane/shared_lane/share_busway cycleway value on a
                          normal road (not a physically separate way).
  C. shared_path      -- highway=cycleway with foot=designated/yes or
                          segregated=no, or cycleway=shared/sidewalk.
  A way can carry both a highway=cycleway classification and an on-road
  sub-tag; the priority order above resolves that in favour of the strongest
  physical-separation signal actually present.

Government (CID) classification, from cycle_lane_track.json's own flags:
  A. dedicated_track  -- CLT_SEGREG=TRUE or CLT_PARSEG=TRUE or CLT_STEPP=TRUE
  B. on_road_lane     -- CLT_CARR=TRUE and not (A) and not CLT_SHARED=TRUE
  C. shared_path      -- CLT_SHARED=TRUE and not (A)
"""
import json

from geo_utils import load_geojson, line_length_m, coverage_by_buffer_tolerance

THRESHOLDS = [5, 10, 15, 20, 30]

TRACK_VALUES = {"track", "separate"}
LANE_VALUES = {"lane", "shared_lane", "share_busway"}
SHARED_VALUES = {"shared", "sidewalk"}
# Values that mean "no cycling infrastructure here" or are junction furniture,
# not a lane/track segment. The initial Overpass query matched on tag *key*
# presence (any cycleway* key), which pulled in ~22k ways whose value was one
# of these -- explicitly the absence of infrastructure, or a crossing marker,
# not a real segment. Caught by inspecting the "unclassified" bucket rather
# than reporting it as-is: exactly the over-broad-query pitfall the Dublin
# lane-tag lesson warned about, just on the value side instead of the key side.
NON_INFRA_VALUES = {"no", "none", "crossing", "traffic_island", "link", "right", "opposite"}


def classify_osm(props: dict) -> str:
    cw_values = {props.get(k) for k in ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both") if props.get(k)}
    is_cycleway_highway = props.get("highway") == "cycleway"
    foot = props.get("foot")
    segregated = props.get("segregated")

    if cw_values & TRACK_VALUES:
        return "dedicated_track"
    if is_cycleway_highway:
        if foot in ("designated", "yes") or segregated == "no" or cw_values & SHARED_VALUES:
            return "shared_path"
        return "dedicated_track"
    if cw_values & SHARED_VALUES:
        return "shared_path"
    if cw_values & LANE_VALUES:
        return "on_road_lane"
    if cw_values and cw_values <= NON_INFRA_VALUES:
        return "not_infrastructure"
    return "unclassified"


def classify_cid(props: dict) -> str:
    def flag(name):
        return props.get(name) == "TRUE"

    if flag("CLT_SEGREG") or flag("CLT_PARSEG") or flag("CLT_STEPP"):
        return "dedicated_track"
    if flag("CLT_SHARED"):
        return "shared_path"
    if flag("CLT_CARR"):
        return "on_road_lane"
    return "unclassified"


def summarize(features: list, classify_fn) -> dict:
    by_type = {}
    for f in features:
        cls = classify_fn(f["properties"])
        geom = f["geometry"]
        length = line_length_m(geom["coordinates"]) if geom["type"] == "LineString" else 0
        d = by_type.setdefault(cls, {"count": 0, "length_km": 0.0})
        d["count"] += 1
        d["length_km"] += length / 1000
    for d in by_type.values():
        d["length_km"] = round(d["length_km"], 2)
    return by_type


def main() -> None:
    osm_raw = load_geojson("../data/raw/osm_cycling.geojson")["features"]
    cid = load_geojson("../data/raw/gov_cid_cycle_lane_track.geojson")["features"]

    for f in osm_raw:
        f["_class"] = classify_osm(f["properties"])
    not_infra_count = sum(1 for f in osm_raw if f["_class"] == "not_infrastructure")
    print(f"Excluding {not_infra_count} OSM ways tagged cycleway=no/crossing/etc. "
          f"(explicit absence of infrastructure or junction furniture, not a lane/track segment)")
    osm = [f for f in osm_raw if f["_class"] != "not_infrastructure"]
    for f in cid:
        f["_class"] = classify_cid(f["properties"])

    osm_summary = summarize(osm, lambda p: classify_osm(p))
    cid_summary = summarize(cid, lambda p: classify_cid(p))

    print("=== OSM cycling infra by type ===")
    print(json.dumps(osm_summary, indent=2))
    print("\n=== Government (CID) cycling infra by type ===")
    print(json.dumps(cid_summary, indent=2))

    gap_by_type = {}
    for cls in ("dedicated_track", "on_road_lane", "shared_path"):
        osm_feats = [f for f in osm if f["_class"] == cls]
        cid_feats = [f for f in cid if f["_class"] == cls]
        print(f"\nComputing buffer coverage for type={cls} "
              f"(gov n={len(cid_feats)}, osm n={len(osm_feats)}) ...")
        if cid_feats and osm_feats:
            gov_covered = coverage_by_buffer_tolerance(cid_feats, osm_feats, THRESHOLDS)
            osm_covered = coverage_by_buffer_tolerance(osm_feats, cid_feats, THRESHOLDS)
        else:
            gov_covered, osm_covered = None, None
        gap_by_type[cls] = {
            "gov_length_covered_by_osm": gov_covered,
            "osm_length_covered_by_gov": osm_covered,
        }
        print(json.dumps(gap_by_type[cls], indent=2))

    out = {
        "osm_summary_by_type": osm_summary,
        "gov_cid_summary_by_type": cid_summary,
        "gap_by_type": gap_by_type,
    }
    with open("../data/processed/cycling_classification_gap.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("\nSaved cycling_classification_gap.json")


if __name__ == "__main__":
    main()
