"""Sentinel-2 L2A from the Earth Search STAC API (AWS, no key). Reads only a small window of each
Cloud-Optimized GeoTIFF, so memory and download stay small. Cloud/shadow pixels are masked with the SCL band."""
import time

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

STAC = "https://earth-search.aws.element84.com/v1/search"
BAD_SCL = [0, 1, 3, 8, 9, 10]      # no data, saturated, cloud shadow, cloud (medium/high), thin cirrus
CLOUD_SCL = [3, 8, 9, 10]
ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
           CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff", GDAL_HTTP_MULTIPLEX="YES",
           GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")


def search(lat, lon, half_km, start, end, max_cloud):
    dlat = half_km / 111.0
    dlon = half_km / (111.0 * float(np.cos(np.radians(lat))))
    bbox = [round(float(x), 5) for x in (lon - dlon, lat - dlat, lon + dlon, lat + dlat)]
    dt = f"{str(start)[:10]}T00:00:00Z/{str(end)[:10]}T23:59:59Z"   # STAC wants full RFC 3339 timestamps
    full = {"collections": ["sentinel-2-l2a"], "bbox": bbox, "datetime": dt, "limit": 100,
            "query": {"eo:cloud_cover": {"lt": float(max_cloud)}},
            "sortby": [{"field": "properties.datetime", "direction": "desc"}]}
    r = requests.post(STAC, json=full, timeout=30)
    if r.status_code == 400:   # retry with the simplest request, then filter and sort here
        simple = {"collections": ["sentinel-2-l2a"], "bbox": bbox, "datetime": dt, "limit": 100}
        r = requests.post(STAC, json=simple, timeout=30)
        if r.status_code >= 400:
            raise ValueError(f"{r.status_code} from Earth Search: {r.text[:300]}")
        feats = [f for f in r.json().get("features", [])
                 if f["properties"].get("eo:cloud_cover", 100) < max_cloud]
        feats.sort(key=lambda f: f["properties"]["datetime"], reverse=True)
        return bbox, feats
    if r.status_code >= 400:
        raise ValueError(f"{r.status_code} from Earth Search: {r.text[:300]}")
    return bbox, r.json().get("features", [])


def _geometry(href, bbox, max_px):
    with rasterio.Env(**ENV), rasterio.open(href) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *bbox)
        win = from_bounds(*b, transform=ds.transform)
        h, w = max(int(round(win.height)), 1), max(int(round(win.width)), 1)
        k = min(1.0, max_px / max(h, w))
        w0, s0, e0, n0 = transform_bounds(ds.crs, "EPSG:4326", *b)
        return (max(int(h * k), 1), max(int(w * k), 1)), [[s0, w0], [n0, e0]]


def _read(href, bbox, shape, bands=(1,), resampling=Resampling.bilinear):
    with rasterio.Env(**ENV), rasterio.open(href) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *bbox)
        win = from_bounds(*b, transform=ds.transform)
        return ds.read(list(bands), window=win, out_shape=(len(bands),) + tuple(shape), resampling=resampling,
                       boundless=True, fill_value=0)


def _scale_offset(f, key):
    rb = (f["assets"][key].get("raster:bands") or [{}])[0]
    try:
        off = -0.1 if float(f["properties"].get("s2:processing_baseline", "0")) >= 4.0 else 0.0
    except ValueError:
        off = 0.0
    return rb.get("scale", 0.0001), rb.get("offset", off)


def ndvi(f, bbox, max_px, shape=None):
    a = f["assets"]
    shape0, bounds = _geometry(a["red"]["href"], bbox, max_px)
    shape = tuple(shape) if shape else shape0
    red = _read(a["red"]["href"], bbox, shape)[0].astype("float32")
    nir = _read(a["nir"]["href"], bbox, shape)[0].astype("float32")
    scl = _read(a["scl"]["href"], bbox, shape, resampling=Resampling.nearest)[0]
    sr, orr = _scale_offset(f, "red")
    sn, on = _scale_offset(f, "nir")
    rr, nn = red * sr + orr, nir * sn + on
    valid = (red > 0) & (nir > 0)
    v = np.clip((nn - rr) / np.maximum(nn + rr, 1e-6), -1, 1)
    bad = np.isin(scl, BAD_SCL) | ~valid
    cloud_pct = 100 * np.isin(scl, CLOUD_SCL)[valid].sum() / max(valid.sum(), 1)
    return np.where(bad, np.nan, v), cloud_pct, bounds, shape


def colorize(v):
    stops = [-0.1, 0.0, 0.2, 0.4, 0.6, 0.8]
    cols = np.array([[40, 110, 200], [140, 109, 63], [230, 217, 107], [156, 207, 90], [46, 158, 79], [11, 93, 42]])
    x = np.nan_to_num(v, nan=-1)
    out = np.zeros(v.shape + (4,), np.uint8)
    for i in range(3):
        out[..., i] = np.interp(x, stops, cols[:, i]).astype(np.uint8)
    out[..., 3] = np.where(np.isnan(v), 0, 255)
    return out


def true_colour(f, bbox, shape):
    arr = _read(f["assets"]["visual"]["href"], bbox, shape, bands=(1, 2, 3))
    rgb = np.moveaxis(arr, 0, -1).astype(np.uint8)
    return np.dstack([rgb, np.where(arr.sum(0) > 0, 255, 0).astype(np.uint8)])


def _summary(f, v, cloud_pct, secs, shape):
    ok = ~np.isnan(v)
    return {"id": f["id"], "date": f["properties"]["datetime"][:10], "scene_cloud": f["properties"].get("eo:cloud_cover"),
            "cloud_pct": round(float(cloud_pct), 1), "usable_pct": round(100 * float(ok.mean()), 1),
            "mean_ndvi": round(float(np.nanmean(v)), 3) if ok.any() else None,
            "veg_pct": round(100 * float((v[ok] > 0.3).mean()), 1) if ok.any() else None,
            "pixels": int(v.size), "seconds": round(secs, 1), "shape": shape}


def stats(f, bbox, max_px=200):
    t = time.perf_counter()
    v, c, _, shape = ndvi(f, bbox, max_px)
    return _summary(f, v, c, time.perf_counter() - t, shape)


def load_scene(f, bbox, max_px):
    t = time.perf_counter()
    v, c, bounds, shape = ndvi(f, bbox, max_px)
    rgb = true_colour(f, bbox, shape)
    out = _summary(f, v, c, time.perf_counter() - t, shape)
    out.update(ndvi=v, ndvi_rgba=colorize(v), rgb=rgb, bounds=bounds)
    return out


def field_ndvi(f, geom, max_px=600):
    """Mean NDVI inside a polygon (GeoJSON geometry, lon/lat) for one scene."""
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds as tfb
    from rasterio.warp import transform_geom
    ring = geom["coordinates"][0]
    xs, ys = [c[0] for c in ring], [c[1] for c in ring]
    pad = 0.0005
    bbox = [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]
    with rasterio.Env(**ENV), rasterio.open(f["assets"]["red"]["href"]) as ds:
        crs = ds.crs
        b = transform_bounds("EPSG:4326", crs, *bbox)
    v, cloud_pct, _, _ = ndvi(f, bbox, max_px)
    inside = geometry_mask([transform_geom("EPSG:4326", crs, geom)], out_shape=v.shape,
                           transform=tfb(*b, v.shape[1], v.shape[0]), invert=True, all_touched=True)
    vals = v[inside & ~np.isnan(v)]
    total = int(inside.sum())
    return {"id": f["id"], "date": f["properties"]["datetime"][:10], "scene_cloud": f["properties"].get("eo:cloud_cover"),
            "mean_ndvi": round(float(vals.mean()), 3) if len(vals) else None,
            "p10": round(float(np.percentile(vals, 10)), 3) if len(vals) else None,
            "p90": round(float(np.percentile(vals, 90)), 3) if len(vals) else None,
            "valid_pct": round(100 * len(vals) / max(total, 1), 1), "field_pixels": total,
            "cloud_pct": round(float(cloud_pct), 1)}


def colorize_diff(d):
    stops = [-0.4, -0.1, 0.0, 0.1, 0.4]
    cols = np.array([[200, 55, 45], [240, 170, 120], [245, 245, 245], [150, 210, 130], [31, 138, 91]])
    x = np.nan_to_num(d, nan=0.0)
    out = np.zeros(d.shape + (4,), np.uint8)
    for i in range(3):
        out[..., i] = np.interp(x, stops, cols[:, i]).astype(np.uint8)
    out[..., 3] = np.where(np.isnan(d), 0, 235)
    return out


def change(f1, f2, bbox, max_px):
    """NDVI change between two scenes (after minus before) over the same window."""
    t = time.perf_counter()
    v1, c1, bounds, shape = ndvi(f1, bbox, max_px)
    v2, c2, _, _ = ndvi(f2, bbox, max_px, shape=shape)
    d = v2 - v1
    ok = ~np.isnan(d)
    return {"before_date": f1["properties"]["datetime"][:10], "after_date": f2["properties"]["datetime"][:10],
            "before_cloud": f1["properties"].get("eo:cloud_cover"), "after_cloud": f2["properties"].get("eo:cloud_cover"),
            "mean_before": round(float(np.nanmean(v1)), 3) if (~np.isnan(v1)).any() else None,
            "mean_after": round(float(np.nanmean(v2)), 3) if (~np.isnan(v2)).any() else None,
            "mean_change": round(float(d[ok].mean()), 3) if ok.any() else None,
            "gain_pct": round(100 * float((d[ok] > 0.1).mean()), 1) if ok.any() else None,
            "loss_pct": round(100 * float((d[ok] < -0.1).mean()), 1) if ok.any() else None,
            "usable_pct": round(100 * float(ok.mean()), 1), "diff": d, "bounds": bounds,
            "diff_rgba": colorize_diff(d), "before_rgba": colorize(v1), "after_rgba": colorize(v2),
            "seconds": round(time.perf_counter() - t, 1), "pixels": int(d.size)}


def _field_v(f, geom, max_px, shape=None):
    """NDVI window around a polygon, with pixels outside the polygon set to NaN."""
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds as tfb
    from rasterio.warp import transform_geom
    ring = geom["coordinates"][0]
    xs, ys = [c[0] for c in ring], [c[1] for c in ring]
    pad = 0.0005
    bbox = [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]
    with rasterio.Env(**ENV), rasterio.open(f["assets"]["red"]["href"]) as ds:
        crs = ds.crs
        b = transform_bounds("EPSG:4326", crs, *bbox)
    v, cloud, bounds, shp = ndvi(f, bbox, max_px, shape=shape)
    inside = geometry_mask([transform_geom("EPSG:4326", crs, geom)], out_shape=v.shape,
                           transform=tfb(*b, v.shape[1], v.shape[0]), invert=True, all_touched=True)
    return np.where(inside, v, np.nan), inside, bounds, shp, cloud


def field_map(f, geom, max_px=600, ha=1.0):
    """Within-field zones: clearly weaker (more than 0.10 NDVI below the field median), typical, clearly stronger."""
    v, inside, bounds, shp, cloud = _field_v(f, geom, max_px)
    ok = ~np.isnan(v)
    base = {"id": f["id"], "date": f["properties"]["datetime"][:10], "cloud_pct": round(float(cloud), 1),
            "usable_pct": round(100 * float(ok.sum()) / max(int(inside.sum()), 1), 1), "bounds": bounds}
    if ok.sum() < 4:
        return {**base, "ok": False}
    p10, p25, p50, p75, p90 = np.percentile(v[ok], [10, 25, 50, 75, 90])
    cls = np.full(v.shape, np.nan)
    cls[ok & (v < p50 - 0.10)] = 0                       # clearly below the field's typical greenness
    cls[ok & (v >= p50 - 0.10) & (v <= p50 + 0.10)] = 1  # typical
    cls[ok & (v > p50 + 0.10)] = 2                       # clearly above
    cols = np.array([[200, 55, 45], [245, 215, 90], [31, 138, 91]], np.uint8)
    zr = np.zeros(v.shape + (4,), np.uint8)
    idx = np.nan_to_num(cls, nan=0).astype(int)
    zr[..., :3] = cols[idx]
    zr[..., 3] = np.where(ok, 215, 0)
    ha_px = ha / max(int(inside.sum()), 1)
    return {**base, "ok": True, "mean": round(float(v[ok].mean()), 3), "median": round(float(p50), 3),
            "spread": round(float(p75 - p25), 3), "weak_ha": round(float((cls == 0).sum() * ha_px), 2),
            "zones_rgba": zr, "ndvi_rgba": colorize(v)}


def field_change(f1, f2, geom, max_px=600, ha=1.0):
    """NDVI change inside a field between two scenes (after minus before)."""
    v1, inside, bounds, shp, c1 = _field_v(f1, geom, max_px)
    v2, _, _, _, c2 = _field_v(f2, geom, max_px, shape=shp)
    d = v2 - v1
    ok = ~np.isnan(d)
    if ok.sum() < 4:
        return {"ok": False, "before_date": f1["properties"]["datetime"][:10], "after_date": f2["properties"]["datetime"][:10]}
    ha_px = ha / max(int(inside.sum()), 1)
    return {"ok": True, "before_date": f1["properties"]["datetime"][:10], "after_date": f2["properties"]["datetime"][:10],
            "mean_before": round(float(np.nanmean(v1)), 3), "mean_after": round(float(np.nanmean(v2)), 3),
            "mean_change": round(float(d[ok].mean()), 3), "gain_ha": round(float((d[ok] > 0.1).sum() * ha_px), 2),
            "loss_ha": round(float((d[ok] < -0.1).sum() * ha_px), 2), "diff_rgba": colorize_diff(d), "bounds": bounds,
            "usable_pct": round(100 * float(ok.sum()) / max(int(inside.sum()), 1), 1)}