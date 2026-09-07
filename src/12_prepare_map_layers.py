"""Simplify geometry, and derive clean human-readable popup fields, for every
layer that will be embedded in the final HTML map.

Three things happen here that didn't in earlier passes of this map:
1. Geometry simplification + property whitelist (mirrors Dublin's
   08_simplify_layers.py -- ~6-7m tolerance is invisible at web-map zoom).
2. Every property key is a plain identifier (stop_name, matched, cycle_type,
   ...) -- a space in a key broke folium's style-function codegen and killed
   the whole page (see 13_build_map.py's docstring). Human-readable labels
   live in GeoJsonPopup's `aliases` instead.
3. Every feature gets an identity block: its own ID (OSM node/way ID, or the
   government OBJECTID/FEATURE_ID), a real "view source record" link (OSM ->
   openstreetmap.org; TfL ArcGIS layers -> a live query-by-ID link against the
   same FeatureServer this data was fetched from; CID cycling assets -> TfL's
   own street-level photo of that exact segment, which beats a synthesized
   Street View link since it's the government's own evidence), and a Google
   Street View deep link at the feature's location as a fallback everywhere
   else. Folium's popup template sets `div.innerHTML` directly (unescaped),
   so an <a href> inside a property value renders as a real clickable link.
"""
import json
import os

from shapely.geometry import shape, mapping

TOLERANCE_DEG = 0.00006
ROUND_DP = 5
OUT_DIR = "../data/processed/map_layers"
os.makedirs(OUT_DIR, exist_ok=True)

CYCLE_LABELS = {
    "dedicated_track": "Dedicated track (segregated)",
    "on_road_lane": "On-road painted lane",
    "shared_path": "Shared path (with pedestrians)",
    "unclassified": "Unclassified",
}

ARCGIS_BASE = {
    "bus_stops": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Stops/FeatureServer/0",
    "bus_routes": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Routes/FeatureServer/0",
    "taxi_ranks": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Taxi_Ranks/FeatureServer/37",
    "bus_lanes": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Lanes/FeatureServer/0",
}


def yn(v) -> str:
    return "Yes" if v in (True, "TRUE", "true", "Yes", "yes", 1) else "No"


def osm_id_and_link(p) -> dict:
    """Store only the bare type+id (~15 bytes). The full <a href=...> markup
    (~110 bytes) is built once by a shared JS function at popup-open time
    instead of being duplicated into every one of the ~150k OSM features that
    carry one -- baking the full link into the data pushed this map's largest
    layers (bus routes, cycling) past GitHub's 100MB per-file push limit for
    no reason, since the URL is 100% derivable from type+id.
    """
    otype, oid = p.get("osm_type"), p.get("osm_id")
    if not otype or not oid:
        return {"source_id": "", "src_kind": "", "src_ref": ""}
    return {"source_id": f"OSM {otype} {oid}", "src_kind": "osm", "src_ref": f"{otype}/{oid}"}


def gov_id_and_link(p, layer_key) -> dict:
    oid = p.get("OBJECTID")
    if not oid:
        return {"source_id": "", "src_kind": "", "src_ref": ""}
    return {"source_id": f"TfL OBJECTID {oid}", "src_kind": "gov", "src_ref": f"{layer_key}:{oid}"}


def round_coords(obj):
    if isinstance(obj, float):
        return round(obj, ROUND_DP)
    if isinstance(obj, list):
        return [round_coords(x) for x in obj]
    return obj


def centroid_lonlat(geom):
    c = geom.centroid
    return (c.x, c.y)


def prep_layer(src_path: str, out_name: str, keep_props: list, is_line: bool = True,
               feature_filter=None, derive=None) -> None:
    with open(src_path, encoding="utf-8") as f:
        fc = json.load(f)
    feats = fc["features"]
    if feature_filter:
        feats = [f for f in feats if feature_filter(f)]

    out_feats = []
    for feat in feats:
        geom = shape(feat["geometry"])
        ll = centroid_lonlat(geom)
        if is_line:
            geom = geom.simplify(TOLERANCE_DEG, preserve_topology=(geom.geom_type != "LineString"))
        new_geom = mapping(geom)
        new_geom["coordinates"] = round_coords(new_geom["coordinates"])
        src_props = feat["properties"]
        derived = derive(src_props, ll) if derive else {}
        props = {k: (src_props.get(k, "") if src_props.get(k) is not None else "") for k in keep_props}
        props.update(derived)
        out_feats.append({"type": "Feature", "geometry": new_geom, "properties": props})

    out_path = f"{OUT_DIR}/{out_name}"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": out_feats}, f, separators=(",", ":"))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"{out_name}: {len(out_feats)} features, {size_kb:.0f} KB")


def prep_walking_merged(src_path: str, out_name: str) -> None:
    """The walking network (250,724 OSM ways) is two orders of magnitude larger
    than any other layer here. All simplified lines are merged into one
    MultiLineString feature so Leaflet draws it as a single canvas path --
    individual per-way click identification is traded away for a network this
    size, same call Dublin made for its own large regional-scope layers.
    """
    with open(src_path, encoding="utf-8") as f:
        fc = json.load(f)
    lines = []
    for feat in fc["features"]:
        geom = shape(feat["geometry"])
        if geom.geom_type != "LineString":
            continue
        geom = geom.simplify(TOLERANCE_DEG, preserve_topology=False)
        if geom.is_empty or len(geom.coords) < 2:
            continue
        lines.append(round_coords(list(geom.coords)))
    merged = {
        "type": "Feature",
        "geometry": {"type": "MultiLineString", "coordinates": lines},
        "properties": {"way_count": f"{len(lines):,}"},
    }
    out_path = f"{OUT_DIR}/{out_name}"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [merged]}, f, separators=(",", ":"))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"{out_name}: {len(lines)} merged line parts, {size_kb:.0f} KB")


def gov_bus_stop_derive(p, ll):
    d = {"stop_name": p.get("STOP_NAME") or "(unnamed)", "road": p.get("ROAD_NAME") or "",
         "stop_code": p.get("STOP_CODE") or "", "matched": yn(p.get("_matched")),
        }
    d.update(gov_id_and_link(p, "bus_stops"))
    return d


def osm_bus_stop_derive(p, ll):
    d = {"stop_name": p.get("name") or "(unnamed)", "local_ref": p.get("local_ref") or "",
         "matched": yn(p.get("_matched"))}
    d.update(osm_id_and_link(p))
    return d


def gov_taxi_rank_derive(p, ll):
    d = {"rank_name": p.get("RANK_NAME") or "(unnamed)", "spaces": p.get("NB_SPACES") or "",
         "rank_type": p.get("FEATURE_TYPE_NAME") or "", "matched": yn(p.get("_matched")),
        }
    d.update(gov_id_and_link(p, "taxi_ranks"))
    return d


def osm_taxi_rank_derive(p, ll):
    d = {"rank_name": p.get("name") or "(unnamed)", "capacity": p.get("capacity") or "",
         "matched": yn(p.get("_matched"))}
    d.update(osm_id_and_link(p))
    return d


def gov_bus_route_derive(p, ll):
    d = {"route": p.get("ROUTE") or "", "direction": p.get("DIRECTION") or "",
         "route_status": p.get("STATUS") or ""}
    d.update(gov_id_and_link(p, "bus_routes"))
    return d


def osm_bus_route_derive(p, ll):
    d = {"road_name": p.get("name") or "(unnamed)", "route_ref": p.get("ref") or "",
        }
    d.update(osm_id_and_link(p))
    return d


def gov_bus_lane_derive(p, ll):
    d = {"road": p.get("ROAD_NAME") or "(unnamed)", "permitted_vehicles": p.get("VEHICLES") or "",
         "taxi_permitted": yn(p.get("_taxi_permitted")), "covered": yn(p.get("_covered")),
        }
    d.update(gov_id_and_link(p, "bus_lanes"))
    return d


def osm_bus_lane_derive(p, ll):
    d = {"road_name": p.get("name") or "(unnamed)", "taxi_tagged": yn(p.get("_taxi_tagged")),
         "covered": yn(p.get("_covered"))}
    d.update(osm_id_and_link(p))
    return d


def gov_cycling_derive(p, ll):
    # TfL's photo URL is fully deterministic from FEATURE_ID
    # (https://cycleassetimages.data.tfl.gov.uk/{FEATURE_ID}_1.jpg), so only
    # the short ID is stored -- the JS popup handler builds the photo link.
    feature_id = p.get("FEATURE_ID") or ""
    return {
        "borough": p.get("BOROUGH") or "", "cycle_type": CYCLE_LABELS.get(p.get("_class"), "Unclassified"),
        "covered": yn(p.get("_covered")),
        "source_id": f"TfL CID {feature_id}" if feature_id else "",
        "src_kind": "cid" if feature_id else "", "src_ref": feature_id,
    }


def osm_cycling_derive(p, ll):
    d = {"way_name": p.get("name") or "(unnamed)", "cycle_type": CYCLE_LABELS.get(p.get("_class"), "Unclassified"),
         "covered": yn(p.get("_covered"))}
    d.update(osm_id_and_link(p))
    return d


LAYERS = [
    dict(src="../data/processed/gov_bus_stops_classified.geojson", out="gov_bus_stops.json",
         keep=[], is_line=False, derive=gov_bus_stop_derive),
    dict(src="../data/processed/osm_bus_stops_classified.geojson", out="osm_bus_stops.json",
         keep=[], is_line=False, derive=osm_bus_stop_derive),
    dict(src="../data/processed/gov_taxi_ranks_classified.geojson", out="gov_taxi_ranks.json",
         keep=[], is_line=False, derive=gov_taxi_rank_derive),
    dict(src="../data/processed/osm_taxi_ranks_classified.geojson", out="osm_taxi_ranks.json",
         keep=[], is_line=False, derive=osm_taxi_rank_derive),
    dict(src="../data/raw/gov_bus_routes.geojson", out="gov_bus_routes.json",
         keep=[], is_line=True, feature_filter=lambda f: f["properties"].get("STATUS") == "CURRENT",
         derive=gov_bus_route_derive),
    dict(src="../data/raw/osm_bus_route_ways_tfl.geojson", out="osm_bus_route_ways.json",
         keep=[], is_line=True, derive=osm_bus_route_derive),
    dict(src="../data/processed/gov_bus_lanes_classified.geojson", out="gov_bus_lanes.json",
         keep=[], is_line=True, derive=gov_bus_lane_derive),
    dict(src="../data/processed/osm_bus_taxi_lanes_classified.geojson", out="osm_bus_taxi_lanes.json",
         keep=[], is_line=True, derive=osm_bus_lane_derive),
    dict(src="../data/processed/gov_cid_cycling_classified.geojson", out="gov_cycling.json",
         keep=[], is_line=True, derive=gov_cycling_derive),
    dict(src="../data/processed/osm_cycling_classified.geojson", out="osm_cycling.json",
         keep=[], is_line=True, derive=osm_cycling_derive),
    dict(src="../data/raw/boundary_gla_gov.geojson", out="boundary_gla.json",
         keep=[], is_line=True, derive=lambda p, ll: {"boundary_name": "Greater London Authority (government)"}),
]


def main() -> None:
    for layer in LAYERS:
        prep_layer(layer["src"], layer["out"], layer["keep"], layer["is_line"],
                   layer.get("feature_filter"), layer.get("derive"))
    prep_walking_merged("../data/raw/osm_walking.geojson", "osm_walking.json")


if __name__ == "__main__":
    main()
