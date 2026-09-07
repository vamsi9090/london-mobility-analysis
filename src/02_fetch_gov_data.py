"""Fetch all TfL government datasets used in this analysis, live, from their
authoritative endpoints:

- Bus stops, bus routes, bus lanes, taxi ranks, cycle routes, London boroughs
  -- from TfL's GIS Open Data Hub (ArcGIS FeatureServer REST API).
- Cycle lane/track segments and cycle-restricted routes -- from the Cycling
  Infrastructure Database (CID), TfL's separate S3-hosted open data release
  (cycling.data.tfl.gov.uk), requested directly since it is not on the ArcGIS hub.

All ArcGIS layers are paginated (resultOffset/resultRecordCount) since several
exceed the service's 2000-record page limit. Everything is requested in WGS84
(outSR=4326) so no CRS reprojection is needed downstream -- unlike Dublin, where
one government source only had OS Irish Grid coordinates.
"""
import json
import time
import urllib.request

HEADERS = {"User-Agent": "london-mobility-analysis/1.0 (research)"}
PAGE_SIZE = 2000

ARCGIS_LAYERS = {
    "gov_bus_stops": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Stops/FeatureServer/0",
    "gov_bus_routes": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Routes/FeatureServer/0",
    "gov_taxi_ranks": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Taxi_Ranks/FeatureServer/37",
    "gov_bus_lanes": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Lanes/FeatureServer/0",
    "gov_cycle_routes": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Cycle_Routes/FeatureServer/11",
    "gov_london_boroughs": "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Boroughs_London/FeatureServer/10",
}

CID_FILES = {
    "gov_cid_cycle_lane_track": "https://cycling.data.tfl.gov.uk/CyclingInfrastructure/data/lines/cycle_lane_track.json",
    "gov_cid_restricted_route": "https://cycling.data.tfl.gov.uk/CyclingInfrastructure/data/lines/restricted_route.json",
}


def fetch_json(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_arcgis_layer(name: str, base_url: str) -> None:
    features = []
    offset = 0
    while True:
        q = (
            f"{base_url}/query?where=1%3D1&outFields=*&outSR=4326"
            f"&f=geojson&resultOffset={offset}&resultRecordCount={PAGE_SIZE}"
        )
        page = fetch_json(q)
        page_features = page.get("features", [])
        features.extend(page_features)
        print(f"  {name}: fetched {len(features)} so far (page had {len(page_features)})")
        if len(page_features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.3)

    out = {"type": "FeatureCollection", "features": features}
    path = f"../data/raw/{name}.geojson"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"Saved {name}: {len(features)} features -> {path}")


def fetch_cid_file(name: str, url: str) -> None:
    data = fetch_json(url, timeout=180)
    n = len(data.get("features", []))
    path = f"../data/raw/{name}.geojson"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"Saved {name}: {n} features -> {path}")


def main() -> None:
    for name, url in ARCGIS_LAYERS.items():
        print("Fetching", name)
        fetch_arcgis_layer(name, url)
    for name, url in CID_FILES.items():
        print("Fetching", name)
        fetch_cid_file(name, url)


if __name__ == "__main__":
    main()
