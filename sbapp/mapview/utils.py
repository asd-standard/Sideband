# coding=utf-8

__all__ = [
    "clamp",
    "haversine",
    "get_zoom_for_radius",
    "to_quad_key",
    "tile_url",
    "tile_cache_fn",
]

import os
from math import asin, cos, pi, radians, sin, sqrt
from random import choice

from kivy.core.window import Window
from kivy.metrics import dp


def clamp(x, minimum, maximum):
    return max(minimum, min(x, maximum))


def to_quad_key(x, y, z):
    """Converts an XYZ tile coordinate to the quadkey used by VirtualEarth"""
    quad_key = []
    i = z
    while i > 0:
        digit = 0
        mask = 1 << (i - 1)
        if (x & mask) != 0:
            digit += 1
        if (y & mask) != 0:
            digit += 2
        quad_key.append(str(digit))
        i -= 1
    return "".join(quad_key)


def tile_url(map_source, x, y, z):
    """
    Returns the upstream URL for the given tile, taking subdomains and
    quadkey-based sources into account. ``y`` must be given in the same
    top-origin XYZ convention that ``map_source``'s URL templates expect.
    """
    if map_source.quad_key:
        return map_source.url.format(
            q=to_quad_key(x, y, z),
            s=choice(map_source.subdomains),
        )
    else:
        return map_source.url.format(
            z=z,
            x=x,
            y=y,
            s=choice(map_source.subdomains),
        )


def tile_cache_fn(map_source, x, y, z):
    """Returns the cache file path for the given tile"""
    fn = map_source.cache_fmt.format(
        image_ext=map_source.image_ext,
        cache_key=map_source.cache_key,
        zoom=z,
        tile_x=x,
        tile_y=y,
    )
    return os.path.join(map_source.cache_dir, fn)


def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)

    Taken from: http://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2

    c = 2 * asin(sqrt(a))
    km = 6367 * c
    return km


def get_zoom_for_radius(radius_km, lat=None, tile_size=256.0):
    """See: https://wiki.openstreetmap.org/wiki/Zoom_levels"""
    radius = radius_km * 1000.0
    if lat is None:
        lat = 0.0  # Do not compensate for the latitude

    # Calculate the equatorial circumference based on the WGS-84 radius
    earth_circumference = 2.0 * pi * 6378137.0 * cos(lat * pi / 180.0)

    # Check how many tiles that are currently in view
    nr_tiles_shown = min(Window.size) / dp(tile_size)

    # Keep zooming in until we find a zoom level where the circle can fit inside the screen
    zoom = 1
    while earth_circumference / (2 << (zoom - 1)) * nr_tiles_shown > 2 * radius:
        zoom += 1
    return zoom - 1  # Go one zoom level back
