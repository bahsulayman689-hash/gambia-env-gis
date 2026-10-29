"""Sentinel-2 L2A from the Earth Search STAC API (AWS, no key). Reads only a small window of each
Cloud-Optimized GeoTIFF, so memory and download stay small. Cloud/shadow pixels are masked with the SCL band."""
import time

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

# Ensure this exact gateway path is used to query the data engine properly
STAC = "https://earth-search.aws.element84.com/v1/search"
BAD_SCL = [0, 1, 3, 8, 9, 10]      # no data, saturated, cloud shadow, cloud (medium/high), thin cirrus
CLOUD_SCL = [3, 8, 9, 10]
ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
           CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff", GDAL_HTTP_MULTIPLEX="YES",
           GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")


def search(lat, lon, half_km, start, end, max_cloud):
    dlat = half_km / 111.0
    dlon = half_km / (111.0 * np.cos(np.radians(lat)))
    bbox = [lon - dlon, lat - dlat, lon + dlon, lat + dlat]
    
    # Enforces current catalog mapping with standardized timestamp ranges
    body = {
        "collections": ["sentinel-2-c1-l2a"], 
        "bbox": bbox, 
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", 
        "limit": 100,
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}]
    }
    
    r = requests.post(STAC, json=body, timeout=30)
    r.raise_for_status()
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


def ndvi(f, bbox, max_px):
    a = f["assets"]
    shape, bounds = _geometry(a["red"]["href"], bbox, max_px)
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
