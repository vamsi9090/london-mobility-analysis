"""Fetch live OSM data for Greater London (area 3600175342, relation 175342)
via the public Overpass API, one category per query, with retry/backoff since
overpass-api.de rate-limits (HTTP 429) rapid sequential requests from one IP --
learned the hard way while probing query sizes for this exact script.

Tag coverage deliberately goes beyond the single obvious tag per category --
the Dublin analysis found that querying only whole-way bus lane tags missed
per-direction lane-array tags (bus:lanes:forward etc.) and silently undercounted
by more than half. The same exhaustive-tag-list approach is applied here for
bus/taxi lanes and for cycling infrastructure (dedicated track / on-road lane /
shared path all use different tag families).
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "london-mobility-analysis/1.0 (research)"}
AREA = "area(3600175342)->.a;"


def run_query(query: str, retries: int = 5) -> dict:
    body = ("data=" + urllib.parse.quote(query)).encode()
    for attempt in range(retries):
        req = urllib.request.Request(OVERPASS_URL, data=body, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            wait = 20 * (attempt + 1)
            print(f"  HTTP {e.code}, retrying in {wait}s (attempt {attempt + 1}/{retries})")
            time.sleep(wait)
    raise RuntimeError(f"Overpass query failed after {retries} retries")


def elements_to_geojson(elements: list) -> dict:
    features = []
    for el in elements:
        tags = el.get("tags", {})
        if el["type"] == "node":
            geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
        elif el["type"] == "way" and "geometry" in el:
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            geom = {"type": "LineString", "coordinates": coords}
        else:
            continue
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {**tags, "osm_type": el["type"], "osm_id": el["id"]},
        })
    return {"type": "FeatureCollection", "features": features}


def save(name: str, elements: list) -> None:
    gj = elements_to_geojson(elements)
    path = f"../data/raw/{name}.geojson"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gj, f)
    print(f"Saved {name}: {len(gj['features'])} features -> {path}")


QUERIES = {
    "osm_bus_stops": f"""
        [out:json][timeout:180];
        {AREA}
        (
          node(area.a)[highway=bus_stop];
          node(area.a)[public_transport=platform][bus=yes];
        );
        out body;
    """,
    "osm_taxi_ranks": f"""
        [out:json][timeout:180];
        {AREA}
        (
          node(area.a)[amenity=taxi];
          way(area.a)[amenity=taxi];
        );
        out center;
    """,
    "osm_bus_route_relations": f"""
        [out:json][timeout:180];
        {AREA}
        relation(area.a)[route=bus];
        out tags;
    """,
    "osm_bus_route_ways": f"""
        [out:json][timeout:300];
        {AREA}
        relation(area.a)[route=bus];
        way(r);
        out geom;
    """,
    "osm_bus_taxi_lanes": f"""
        [out:json][timeout:300];
        {AREA}
        (
          way(area.a)[busway];
          way(area.a)["busway:left"];
          way(area.a)["busway:right"];
          way(area.a)["busway:both"];
          way(area.a)[bus=designated];
          way(area.a)[psv=designated];
          way(area.a)[taxi=yes];
          way(area.a)[taxi=designated];
          way(area.a)["bus:lanes"];
          way(area.a)["bus:lanes:forward"];
          way(area.a)["bus:lanes:backward"];
          way(area.a)["psv:lanes"];
          way(area.a)["psv:lanes:forward"];
          way(area.a)["psv:lanes:backward"];
          way(area.a)["taxi:lanes"];
          way(area.a)["taxi:lanes:forward"];
          way(area.a)["taxi:lanes:backward"];
          way(area.a)["lanes:bus"];
          way(area.a)["lanes:bus:forward"];
          way(area.a)["lanes:bus:backward"];
          way(area.a)["lanes:psv"];
          way(area.a)["lanes:psv:forward"];
          way(area.a)["lanes:psv:backward"];
        );
        out geom;
    """,
    "osm_cycling": f"""
        [out:json][timeout:300];
        {AREA}
        (
          way(area.a)[highway=cycleway];
          way(area.a)["cycleway"];
          way(area.a)["cycleway:left"];
          way(area.a)["cycleway:right"];
          way(area.a)["cycleway:both"];
          way(area.a)[highway=path][bicycle=designated];
          way(area.a)[highway=footway][bicycle=designated];
          way(area.a)[highway=track][bicycle=designated];
        );
        out geom;
    """,
    "osm_walking_count_only": f"""
        [out:json][timeout:180];
        {AREA}
        way(area.a)[highway~"^(footway|path|pedestrian|steps|living_street)$"];
        out count;
    """,
}


def main() -> None:
    for i, (name, q) in enumerate(QUERIES.items()):
        print(f"\nQuerying {name} ...")
        t0 = time.time()
        result = run_query(q)
        elapsed = time.time() - t0
        elements = result.get("elements", [])
        if name == "osm_walking_count_only":
            print("Walking network element count result:", elements)
            with open("../data/raw/osm_walking_count.json", "w", encoding="utf-8") as f:
                json.dump(elements, f)
        else:
            save(name, elements)
        print(f"  ({elapsed:.1f}s)")
        if i < len(QUERIES) - 1:
            time.sleep(12)


if __name__ == "__main__":
    main()
