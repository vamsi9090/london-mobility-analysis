"""Build the final interactive map.

Design pass applied per the dataviz skill's method:
- Colors are assigned by the job they do, from the skill's validated
  reference palette (references/palette.md): "matched/unmatched" is a STATE,
  so it gets the reserved status colors (good green / critical red)
  everywhere it appears. The three cycling types are an IDENTITY split shown
  simultaneously, so they get the three categorical slots the palette's own
  validation confirms are safe together (1/2/3 -- the all-pairs-safe set).
- Every feature is click-to-inspect (a real Leaflet popup with labelled
  fields), not hover-only.
- A custom sidebar (grouped by OSM / Government / Gaps, with a color swatch
  and a live feature count per row) replaces the default flat layer control.

Real bug fixed in this version: property keys with spaces ("Stop name",
"Matched to OSM (15m)", ...) broke folium's style-function code generation --
for a style_function whose output doesn't vary by feature, folium emits a
`switch(feature.properties.<first-key>) { default: ... }` scaffold using
*dot* notation, not bracket notation. Any key containing a space produced
invalid JavaScript there, and because the whole map lives in one <script>
block, that one syntax error broke the entire page -- nothing rendered, no
console-visible cause unless you opened devtools. Every property key is now a
plain identifier (stop_name, matched, cycle_type, ...); the human-readable
text moves to GeoJsonPopup's `aliases` parameter instead, which does the
label/value split correctly regardless of spacing. Verified this time with
`node --check` against the actual generated script before calling it done,
not just by eyeballing the Python.
"""
import json

import folium
from folium import GeoJsonPopup

LAYER_DIR = "../data/processed/map_layers"
OUT_PATH = "../maps/london_osm_vs_gov_map.html"

# --- Palette (dataviz skill reference palette, references/palette.md) ---
STATUS_GOOD = "#0ca30c"       # matched
STATUS_CRITICAL = "#d03b3b"   # unmatched / gap
CAT_BLUE = "#2a78d6"          # slot 1 -- OSM lines / cycling: dedicated track
CAT_ORANGE = "#eb6834"        # slot 2 -- cycling: on-road lane
CAT_AQUA = "#1baf7a"          # slot 3 -- cycling: shared path
CAT_VIOLET = "#4a3aa7"        # government lines / taxi-permitted lanes
INK_PRIMARY = "#0b0b0b"
INK_MUTED = "#898781"

CYCLE_COLORS = {
    "Dedicated track (segregated)": CAT_BLUE,
    "On-road painted lane": CAT_ORANGE,
    "Shared path (with pedestrians)": CAT_AQUA,
}

registry = []  # populated as layers are built; drives the custom sidebar


def load(name):
    with open(f"{LAYER_DIR}/{name}", encoding="utf-8") as f:
        return json.load(f)


def register(section, label, color, fg, count, default_on=False):
    registry.append({
        "section": section, "label": label, "color": color,
        "js_var": fg.get_name(), "count": count, "default_on": default_on,
    })


def popup_for(fields_aliases):
    fields = [f for f, _ in fields_aliases]
    aliases = [a for _, a in fields_aliases]
    return GeoJsonPopup(fields=fields, aliases=aliases, labels=True, localize=False,
                         style="font-size:13px; font-family:system-ui,sans-serif;")


def status_style_fn(status_field):
    def _style(feat):
        color = STATUS_GOOD if feat["properties"].get(status_field) == "Yes" else STATUS_CRITICAL
        return {"color": color, "fillColor": color, "weight": 1}
    return _style


def point_group(fc, status_field, fields_aliases, name, section, radius=3.5):
    fg = folium.FeatureGroup(name=name, show=False, control=False)
    marker_template = folium.CircleMarker(location=[0, 0], radius=radius, weight=1, fill=True, fill_opacity=0.85)
    folium.GeoJson(fc, marker=marker_template, style_function=status_style_fn(status_field),
                    popup=popup_for(fields_aliases)).add_to(fg)
    n_matched = sum(1 for f in fc["features"] if f["properties"].get(status_field) == "Yes")
    n_total = len(fc["features"])
    register(section, f"{name.split(': ', 1)[-1]} — {n_matched:,} matched / {n_total - n_matched:,} unmatched",
              STATUS_GOOD, fg, n_total)
    return fg


def line_group(fc, name, color, fields_aliases, section, weight=1.6, opacity=0.75, count=None):
    fg = folium.FeatureGroup(name=name, show=False, control=False)
    style = lambda feat: {"color": color, "weight": weight, "opacity": opacity}
    popup = popup_for(fields_aliases) if fields_aliases else None
    folium.GeoJson(fc, style_function=style, popup=popup,
                    highlight_function=lambda f: {"weight": weight + 2.5}).add_to(fg)
    n = count if count is not None else len(fc["features"])
    register(section, f"{name.split(': ', 1)[-1]} — {n:,}", color, fg, n)
    return fg


def classified_line_group(fc, name, class_field, color_map, fields_aliases, section, weight=2.6, opacity=0.85):
    fg = folium.FeatureGroup(name=name, show=False, control=False)
    style = lambda feat: {
        "color": color_map.get(feat["properties"].get(class_field), INK_MUTED),
        "weight": weight, "opacity": opacity,
    }
    folium.GeoJson(fc, style_function=style, popup=popup_for(fields_aliases),
                    highlight_function=lambda f: {"weight": weight + 2.5}).add_to(fg)
    register(section, f"{name.split(': ', 1)[-1]} — {len(fc['features']):,}", None, fg, len(fc["features"]))
    return fg


def cycling_type_group(fc, cls_label, source_label, section, fields_aliases):
    feats = [f for f in fc["features"] if f["properties"].get("cycle_type") == cls_label]
    sub = {"type": "FeatureCollection", "features": feats}
    color = CYCLE_COLORS[cls_label]
    name = f"{source_label}: Cycling — {cls_label}"
    return line_group(sub, name, color, fields_aliases, section, weight=2.2, opacity=0.85, count=len(feats))


def gap_group(fc, class_field, cls_label, source_label, section, fields_aliases):
    feats = [f for f in fc["features"] if f["properties"].get("cycle_type") == cls_label] if class_field else fc["features"]
    fg = folium.FeatureGroup(name=f"Gap: {source_label} — {cls_label}", show=False, control=False)
    style = lambda feat: {
        "color": STATUS_CRITICAL if feat["properties"].get("covered") == "No" else "#d9d8d2",
        "weight": 2.4 if feat["properties"].get("covered") == "No" else 1,
        "opacity": 0.9 if feat["properties"].get("covered") == "No" else 0.15,
    }
    folium.GeoJson({"type": "FeatureCollection", "features": feats}, style_function=style,
                    popup=popup_for(fields_aliases)).add_to(fg)
    n_gap = sum(1 for f in feats if f["properties"].get("covered") == "No")
    label = f"{cls_label} — {n_gap:,} of {len(feats):,} not matched"
    register(section, label, STATUS_CRITICAL, fg, len(feats))
    return fg


SIDEBAR_CSS = """
<style>
#lm-sidebar {
  position: fixed; top: 12px; left: 12px; z-index: 1000;
  width: 300px; max-height: calc(100vh - 24px); overflow-y: auto;
  background: #fcfcfbee; backdrop-filter: blur(6px);
  border: 1px solid rgba(11,11,11,0.10); border-radius: 10px;
  box-shadow: 0 4px 18px rgba(0,0,0,0.18);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  color: #0b0b0b;
}
#lm-sidebar h1 {
  font-size: 14px; font-weight: 700; margin: 0; padding: 12px 14px 8px;
  border-bottom: 1px solid #e1e0d9;
}
#lm-sidebar h1 span { display:block; font-weight:400; font-size:11px; color:#52514e; margin-top:2px; }
#lm-sidebar details { border-bottom: 1px solid #e1e0d9; }
#lm-sidebar summary {
  cursor: pointer; padding: 9px 14px; font-size: 12.5px; font-weight: 700;
  letter-spacing: 0.02em; text-transform: uppercase; color: #52514e;
  list-style: none; display: flex; justify-content: space-between; align-items: center;
}
#lm-sidebar summary::-webkit-details-marker { display: none; }
#lm-sidebar summary::after { content: "+"; font-size: 15px; color: #898781; }
#lm-sidebar details[open] summary::after { content: "\\2212"; }
#lm-sidebar .lm-row {
  display: flex; align-items: center; gap: 8px; padding: 5px 14px 5px 20px; font-size: 12.5px;
}
#lm-sidebar .lm-row:hover { background: #f0efec; }
#lm-sidebar .lm-swatch { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; border: 1px solid rgba(0,0,0,0.15); }
#lm-sidebar .lm-label { flex: 1; line-height: 1.3; }
#lm-sidebar input[type=checkbox] { accent-color: #2a78d6; width: 15px; height: 15px; flex-shrink: 0; }
#lm-sidebar .lm-footer { padding: 8px 14px; font-size: 10.5px; color: #898781; }
.leaflet-popup-content-wrapper { border-radius: 8px; }
.leaflet-popup-content table { font-size: 12.5px; }
.leaflet-popup-content table tr th { color: #52514e; padding-right: 6px; text-align:left; }
.leaflet-popup-content table tr td { color: #0b0b0b; font-weight: 600; }
</style>
"""


def build_sidebar_html(map_var: str) -> str:
    sections = {}
    for row in registry:
        sections.setdefault(row["section"], []).append(row)

    body = ['<div id="lm-sidebar"><h1>London: OSM vs. Government<span>Toggle layers &middot; click any feature for details</span></h1>']
    for section, rows in sections.items():
        body.append(f"<details><summary>{section} ({len(rows)})</summary>")
        for r in rows:
            checked = "checked" if r["default_on"] else ""
            swatch = f'<span class="lm-swatch" style="background:{r["color"] or "#999"}"></span>'
            body.append(
                f'<div class="lm-row">{swatch}'
                f'<span class="lm-label">{r["label"]}</span>'
                f'<input type="checkbox" {checked} data-layer="{r["js_var"]}"></div>'
            )
        body.append("</details>")
    body.append('<div class="lm-footer">Data: TfL GIS Open Data Hub + OSM Overpass, Sep 2026</div></div>')
    html = "".join(body)

    js_lines = ["document.addEventListener('DOMContentLoaded', function() {"]
    for r in registry:
        if r["default_on"]:
            js_lines.append(f"  try {{ {r['js_var']}.addTo({map_var}); }} catch(e) {{}}")
    js_lines.append("""
  document.querySelectorAll('#lm-sidebar input[type=checkbox]').forEach(function(cb) {
    cb.addEventListener('change', function() {
      var layer = window[cb.dataset.layer];
      if (!layer) return;
      if (cb.checked) { layer.addTo(%s); } else { %s.removeLayer(layer); }
    });
  });

  var LM_GOV_BASE = {
    bus_stops: 'https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Stops/FeatureServer/0',
    bus_routes: 'https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Routes/FeatureServer/0',
    taxi_ranks: 'https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Taxi_Ranks/FeatureServer/37',
    bus_lanes: 'https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Lanes/FeatureServer/0'
  };

  %s.on('popupopen', function(e) {
    var el = e.popup.getElement();
    var content = el ? el.querySelector('.leaflet-popup-content') : null;
    if (!content || content.querySelector('.lm-sv-link')) { return; }

    // Source-record link, built from the short src_kind/src_ref this feature
    // carries -- not a full URL string baked into every feature, which was
    // pushing the largest layers (bus routes, cycling) past GitHub's 100MB
    // per-file push limit for no reason, since the URL is fully derivable.
    try {
      var feat = e.popup._source && e.popup._source.feature;
      var props = feat && feat.properties;
      if (props && props.src_kind) {
        var linkA = document.createElement('a');
        linkA.target = '_blank'; linkA.rel = 'noopener'; linkA.className = 'lm-src-link';
        linkA.style.cssText = 'display:block;margin-top:4px;font-weight:600;';
        if (props.src_kind === 'osm') {
          linkA.href = 'https://www.openstreetmap.org/' + props.src_ref;
          linkA.textContent = 'View on OpenStreetMap \\u2197';
        } else if (props.src_kind === 'gov') {
          var parts = props.src_ref.split(':');
          var base = LM_GOV_BASE[parts[0]];
          if (base) {
            linkA.href = base + '/query?objectids=' + parts[1] + '&f=json';
            linkA.textContent = 'View TfL source record (JSON) \\u2197';
          }
        } else if (props.src_kind === 'cid') {
          linkA.href = 'https://cycleassetimages.data.tfl.gov.uk/' + props.src_ref + '_1.jpg';
          linkA.textContent = 'TfL street-level photo \\u2197';
        }
        if (linkA.href) { content.appendChild(linkA); }
      }
    } catch (err) {}

    var ll = e.popup.getLatLng();
    var url = 'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint='
      + ll.lat.toFixed(5) + ',' + ll.lng.toFixed(5);
    var a = document.createElement('a');
    a.href = url; a.target = '_blank'; a.rel = 'noopener'; a.className = 'lm-sv-link';
    a.textContent = 'Google Street View at this point \\u2197';
    a.style.cssText = 'display:block;margin-top:6px;font-weight:600;';
    content.appendChild(a);
  });
""" % (map_var, map_var, map_var))
    js_lines.append("});")
    script = "<script>" + "\n".join(js_lines) + "</script>"
    return html + script


def main() -> None:
    m = folium.Map(location=[51.5074, -0.1278], zoom_start=11, tiles=None, prefer_canvas=True,
                    zoom_control="bottomright")
    folium.TileLayer("OpenStreetMap", name="Street map", control=True).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satellite", control=True,
    ).add_to(m)

    boundary = load("boundary_gla.json")
    b_fg = folium.FeatureGroup(name="Greater London Authority boundary", show=True, control=False)
    folium.GeoJson(
        boundary, style_function=lambda f: {"color": INK_PRIMARY, "weight": 2, "fill": False, "dashArray": "5,5"},
        popup=popup_for([("boundary_name", "Boundary")]),
    ).add_to(b_fg)
    b_fg.add_to(m)
    register("Boundary", "Greater London Authority (government)", INK_PRIMARY, b_fg, 1, default_on=True)

    # --- OSM panel ---
    fg = point_group(load("osm_bus_stops.json"), "matched",
                      [("stop_name", "Stop name"), ("local_ref", "Local ref"), ("matched", "Matched to Government"),
                       ("source_id", "ID")],
                      "OSM: Bus stops", "OpenStreetMap")
    fg.add_to(m)
    fg = line_group(load("osm_bus_route_ways.json"), "OSM: Bus routes (London Buses network)", CAT_BLUE,
                     [("road_name", "Road name"), ("route_ref", "Route ref(s)"), ("source_id", "ID")],
                     "OpenStreetMap", weight=3, opacity=0.95)
    fg.add_to(m)
    fg = point_group(load("osm_taxi_ranks.json"), "matched",
                      [("rank_name", "Name"), ("capacity", "Capacity"), ("matched", "Matched to Government"),
                       ("source_id", "ID")],
                      "OSM: Taxi ranks", "OpenStreetMap", radius=5)
    fg.add_to(m)
    fg = classified_line_group(load("osm_bus_taxi_lanes.json"), "OSM: Designated bus/taxi lanes", "taxi_tagged",
                                {"Yes": CAT_VIOLET, "No": CAT_BLUE},
                                [("road_name", "Road name"), ("taxi_tagged", "Taxi tag present"),
                                 ("covered", "Matched to Government (15m)"), ("source_id", "ID")], "OpenStreetMap")
    fg.add_to(m)
    osm_cyc = load("osm_cycling.json")
    for cls in CYCLE_COLORS:
        fg = cycling_type_group(osm_cyc, cls, "OSM", "OpenStreetMap",
                                 [("way_name", "Name"), ("cycle_type", "Type"), ("covered", "Matched to Government (15m)"),
                                  ("source_id", "ID")])
        fg.add_to(m)
    fg = line_group(load("osm_walking.json"), "OSM: Walking network (footway/path/pedestrian/steps)",
                     INK_MUTED, [("way_count", "Ways in this layer")], "OpenStreetMap",
                     weight=0.6, opacity=0.5, count=250724)
    fg.add_to(m)

    # --- Government panel ---
    fg = point_group(load("gov_bus_stops.json"), "matched",
                      [("stop_name", "Stop name"), ("road", "Road"), ("stop_code", "Stop code"),
                       ("matched", "Matched to OSM"), ("source_id", "ID")],
                      "Government: Bus stops", "Government")
    fg.add_to(m)
    fg = line_group(load("gov_bus_routes.json"), "Government: Bus routes (current)", CAT_ORANGE,
                     [("route", "Route"), ("direction", "Direction"), ("route_status", "Status"),
                      ("source_id", "ID")],
                     "Government", weight=3, opacity=0.95)
    fg.add_to(m)
    fg = point_group(load("gov_taxi_ranks.json"), "matched",
                      [("rank_name", "Rank name"), ("spaces", "Spaces"), ("rank_type", "Type"),
                       ("matched", "Matched to OSM"), ("source_id", "ID")],
                      "Government: Taxi ranks", "Government", radius=5)
    fg.add_to(m)
    fg = classified_line_group(load("gov_bus_lanes.json"), "Government: Bus lanes (taxi-permitted vs bus-only)",
                                "taxi_permitted", {"Yes": CAT_VIOLET, "No": CAT_BLUE},
                                [("road", "Road"), ("permitted_vehicles", "Permitted vehicles"),
                                 ("taxi_permitted", "Taxi permitted"), ("covered", "Matched to OSM (15m)"),
                                 ("source_id", "ID")],
                                "Government")
    fg.add_to(m)
    gov_cyc = load("gov_cycling.json")
    for cls in CYCLE_COLORS:
        fg = cycling_type_group(gov_cyc, cls, "Government", "Government",
                                 [("borough", "Borough"), ("cycle_type", "Type"), ("covered", "Matched to OSM (15m)"),
                                  ("source_id", "ID")])
        fg.add_to(m)

    # --- Gap layers ---
    fg = gap_group(load("gov_bus_lanes.json"), None, "Bus lanes", "Government", "Gaps (15m tolerance)",
                    [("road", "Road"), ("permitted_vehicles", "Permitted vehicles"), ("covered", "Matched to OSM (15m)"),
                     ("source_id", "ID")])
    fg.add_to(m)
    for cls in CYCLE_COLORS:
        fg = gap_group(gov_cyc, "cycle_type", cls, "Government cycling", "Gaps (15m tolerance)",
                        [("borough", "Borough"), ("cycle_type", "Type"), ("covered", "Matched to OSM (15m)"),
                         ("source_id", "ID")])
        fg.add_to(m)

    m.get_root().header.add_child(folium.Element(SIDEBAR_CSS))
    m.get_root().html.add_child(folium.Element(build_sidebar_html(m.get_name())))
    folium.LayerControl(collapsed=True, position="topright").add_to(m)

    m.save(OUT_PATH)
    print("Saved", OUT_PATH)
    print(f"Sidebar registry: {len(registry)} layers across {len(set(r['section'] for r in registry))} sections")


if __name__ == "__main__":
    main()
