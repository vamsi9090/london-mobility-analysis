"""Fetch two independent London boundary polygons:

1. Government boundary: the official Greater London Authority (GLA) administrative
   boundary, published by TfL on its GIS Open Data Hub (ArcGIS FeatureServer).
2. OSM boundary: the OpenStreetMap "Greater London" administrative relation
   (osm_id 175342), fetched via Nominatim, used as the area filter for Overpass
   queries so OSM data is pulled for the matching extent.

Both are saved so later scripts can clip every dataset (government AND OSM) to
one common polygon -- the lesson from Dublin/Paris is that area-scope mismatches
between OSM query extent and government dataset extent silently masquerade as
data-completeness gaps if not normalized first.
"""
import json
import urllib.request

HEADERS = {"User-Agent": "london-mobility-analysis/1.0 (research)"}

GLA_URL = (
    "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/"
    "Greater_London_Authority__GLA_/FeatureServer/17/query"
    "?where=1%3D1&outFields=*&outSR=4326&f=geojson"
)
NOMINATIM_URL = (
    "https://nominatim.openstreetmap.org/lookup"
    "?osm_ids=R175342&format=geojson&polygon_geojson=1"
)

OUT_GOV = "../data/raw/boundary_gla_gov.geojson"
OUT_OSM = "../data/raw/boundary_greater_london_osm.geojson"


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    gov = fetch(GLA_URL)
    assert gov.get("features"), "GLA FeatureServer returned no features"
    print("GLA (gov) boundary features:", len(gov["features"]))
    print("GLA properties sample:", gov["features"][0]["properties"])
    with open(OUT_GOV, "w", encoding="utf-8") as f:
        json.dump(gov, f)
    print("Saved government boundary to", OUT_GOV)

    osm = fetch(NOMINATIM_URL)
    assert osm.get("features"), "Nominatim returned no features for relation 175342"
    feature = osm["features"][0]
    print("OSM boundary geometry type:", feature["geometry"]["type"])
    print("OSM properties:", {k: feature["properties"].get(k) for k in ("osm_id", "display_name", "type")})
    with open(OUT_OSM, "w", encoding="utf-8") as f:
        json.dump(feature, f)
    print("Saved OSM boundary to", OUT_OSM)


if __name__ == "__main__":
    main()
