"""Shared geometry helpers for the London analysis scripts."""
import json
import math

import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import shape, Point
from shapely.ops import unary_union, transform as shapely_transform

_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform
_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True).transform


def to_bng(geom):
    return shapely_transform(_TO_BNG, geom)


def load_geojson(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def boundary_polygon(path: str):
    gj = load_geojson(path)
    geoms = [shape(f["geometry"]) for f in gj["features"]] if "features" in gj else [shape(gj["geometry"])]
    return unary_union(geoms)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def line_length_m(coords: list) -> float:
    total = 0.0
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[i + 1]
        total += haversine_m(lon1, lat1, lon2, lat2)
    return total


def sample_points_along(line_coords_bng: list, spacing_m: float = 10.0) -> list:
    """Sample points at a fixed spacing along a line, in projected (metre) coords."""
    pts = []
    for i in range(len(line_coords_bng) - 1):
        x1, y1 = line_coords_bng[i]
        x2, y2 = line_coords_bng[i + 1]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        if seg_len == 0:
            continue
        n_steps = max(1, int(seg_len // spacing_m))
        for s in range(n_steps):
            t = s / n_steps
            pts.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    if line_coords_bng:
        pts.append(tuple(line_coords_bng[-1]))
    return pts


def coverage_by_buffer_tolerance(line_features_a: list, line_features_b: list, thresholds_m: list) -> dict:
    """For line dataset A (sampled to points) and reference dataset B (as a point
    cloud for nearest-neighbor lookup), compute what fraction of A's total length
    lies within each buffer distance of some point in B, at several thresholds.

    This is a scalable point-sampling substitute for full buffer-and-union
    overlap detection (Dublin's original approach), used because these London
    datasets have tens of thousands of line features -- polygon-union at that
    scale is impractically slow, while nearest-neighbor lookup via a KD-tree
    over sampled points is fast and gives an equivalent answer. Reporting the
    result at multiple thresholds reproduces Dublin's diagnostic: a smooth
    climb from a low to a high coverage percentage as tolerance increases is
    the signature of "same real feature, different digitization," not a
    genuine gap that a single-threshold number could mistake for one.
    """
    b_points = []
    for feat in line_features_b:
        geom = feat["geometry"]
        if geom["type"] != "LineString":
            continue
        b_points.extend(sample_points_along([to_bng_coord(c) for c in geom["coordinates"]]))
    if not b_points:
        return {f"{t}m": 0.0 for t in thresholds_m}
    tree = cKDTree(np.array(b_points))

    total_len = 0.0
    covered_len_by_threshold = {t: 0.0 for t in thresholds_m}
    for feat in line_features_a:
        geom = feat["geometry"]
        if geom["type"] != "LineString":
            continue
        coords_bng = [to_bng_coord(c) for c in geom["coordinates"]]
        seg_length = line_length_m(geom["coordinates"])
        total_len += seg_length
        sample_pts = sample_points_along(coords_bng, spacing_m=10.0)
        if not sample_pts:
            continue
        dists, _ = tree.query(np.array(sample_pts), k=1)
        for t in thresholds_m:
            frac_within = float(np.mean(dists <= t))
            covered_len_by_threshold[t] += seg_length * frac_within

    return {
        "total_length_km": round(total_len / 1000, 2),
        "coverage_pct_by_threshold": {
            f"{t}m": round(100 * covered_len_by_threshold[t] / total_len, 1) if total_len else None
            for t in thresholds_m
        },
    }


def flag_coverage(features_a: list, reference_b: list, threshold_m: float) -> None:
    """Tag each feature in A with properties['_covered'] = True if the majority
    of its length lies within threshold_m of some feature in B, else False.
    Used to build gap-highlight map layers at the same 15m tolerance used for
    the headline coverage percentages.
    """
    b_points = []
    for feat in reference_b:
        geom = feat["geometry"]
        if geom["type"] != "LineString":
            continue
        b_points.extend(sample_points_along([to_bng_coord(c) for c in geom["coordinates"]]))
    if not b_points:
        for f in features_a:
            f["properties"]["_covered"] = False
        return
    tree = cKDTree(np.array(b_points))
    for f in features_a:
        geom = f["geometry"]
        if geom["type"] != "LineString":
            f["properties"]["_covered"] = False
            continue
        coords_bng = [to_bng_coord(c) for c in geom["coordinates"]]
        sample_pts = sample_points_along(coords_bng, spacing_m=10.0)
        if not sample_pts:
            f["properties"]["_covered"] = False
            continue
        dists, _ = tree.query(np.array(sample_pts), k=1)
        f["properties"]["_covered"] = bool(np.mean(dists <= threshold_m) >= 0.5)


def to_bng_coord(lonlat) -> tuple:
    x, y = _TO_BNG(lonlat[0], lonlat[1])
    return (x, y)


def feature_point(feat: dict):
    geom = feat["geometry"]
    if geom["type"] == "Point":
        return Point(geom["coordinates"])
    if geom["type"] == "LineString":
        coords = geom["coordinates"]
        mid = coords[len(coords) // 2]
        return Point(mid)
    if geom["type"] == "Polygon":
        return shape(geom).centroid
    raise ValueError(f"Unsupported geometry type {geom['type']}")
