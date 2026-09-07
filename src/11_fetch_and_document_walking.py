"""Walking/pedestrian infrastructure: fetch full OSM geometry, and document the
genuine-search result that no free, comprehensive, open government footway
dataset exists for London -- verified by checking specific candidates, not
assumed by analogy to Dublin:

- OS MasterMap Highways Network - Paths: the accurate, authoritative GB path
  network, but "Licence: Not set" on its data.gov.uk listing with no public
  download link -- it is Ordnance Survey's PSGA/premium product, not open data.
- OS Detailed Path Network: open (OGL) but explicitly scoped to off-road
  navigation in National Parks, not urban footways -- does not cover London's
  pedestrian network.
- OS Open Roads: free (OGL) with a direct bulk-download API, but explicitly
  covers vehicle roads only ("motorways to country lanes") -- footpaths are
  not a feature type in it.

So OSM is the only usable source for Dublin's pedestrian network, and the same
appears true for London -- this script documents that rather than silently
comparing OSM against nothing.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "london-mobility-analysis/1.0 (research)"}
AREA = "area(3600175342)->.a;"


def run_query(query: str, retries: int = 6) -> dict:
    body = ("data=" + urllib.parse.quote(query)).encode()
    for attempt in range(retries):
        req = urllib.request.Request(OVERPASS_URL, data=body, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            wait = 20 * (attempt + 1)
            print(f"  HTTP {e.code}, retrying in {wait}s (attempt {attempt + 1}/{retries})")
            time.sleep(wait)
    raise RuntimeError("Overpass query failed after retries")


def elements_to_geojson(elements: list) -> dict:
    features = []
    for el in elements:
        if el["type"] != "way" or "geometry" not in el:
            continue
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {**el.get("tags", {}), "osm_type": el["type"], "osm_id": el["id"]},
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    print("Counting walking network by highway subtype ...")
    counts = {}
    for i, hw in enumerate(["footway", "path", "pedestrian", "steps", "living_street"]):
        q = f'[out:json][timeout:120];{AREA}way(area.a)[highway={hw}];out count;'
        result = run_query(q)
        counts[hw] = int(result["elements"][0]["tags"]["total"])
        print(f"  highway={hw}: {counts[hw]}")
        if i < 4:
            time.sleep(15)

    print("\nFetching full geometry for the walking network (this is the largest query, may take a while) ...")
    q_geom = f"""
        [out:json][timeout:400][maxsize:1073741824];
        {AREA}
        way(area.a)[highway~"^(footway|path|pedestrian|steps|living_street)$"];
        out geom;
    """
    time.sleep(15)
    result = run_query(q_geom)
    gj = elements_to_geojson(result["elements"])
    with open("../data/raw/osm_walking.geojson", "w", encoding="utf-8") as f:
        json.dump(gj, f)
    print(f"Saved osm_walking.geojson: {len(gj['features'])} features")

    walking_summary = {
        "counts_by_highway_subtype": counts,
        "total_ways": sum(counts.values()),
        "government_dataset_search_result": {
            "conclusion": "No free, comprehensive, open government footway/pedestrian "
                           "network dataset exists for London.",
            "candidates_checked": [
                {
                    "dataset": "OS MasterMap Highways Network - Paths",
                    "finding": "Licence not set on data.gov.uk listing; no public download link; "
                                "OS's PSGA/premium product, requires a paid licence/account.",
                },
                {
                    "dataset": "OS Detailed Path Network",
                    "finding": "Open (OGL) but explicitly scoped to off-road navigation in "
                                "National Parks, not urban footways -- does not cover London.",
                },
                {
                    "dataset": "OS Open Roads",
                    "finding": "Free (OGL), direct bulk download available, but covers vehicle "
                                "roads only ('motorways to country lanes') -- footpaths are "
                                "explicitly not a feature type.",
                },
            ],
        },
    }
    with open("../data/processed/walking_analysis.json", "w", encoding="utf-8") as f:
        json.dump(walking_summary, f, indent=2)
    print("\nSaved walking_analysis.json")
    print(json.dumps(walking_summary, indent=2))


if __name__ == "__main__":
    main()
