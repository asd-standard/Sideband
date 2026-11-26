# coding=utf-8
"""
Region prefetching and MBTiles export for MapView
=================================================

Utilities for downloading every tile covering a geographic region, so it
can be used offline, either directly from the map cache, or as a portable
raster MBTiles file that can be distributed and opened with
:class:`mapview.mbtsource.MBTilesMapSource`.

Only raster tiles from sources that explicitly permit bulk downloading
should be prefetched. Sideband only ever uses this for OpenStreetMap, via
:func:`get_osm_download_source`.
"""

__all__ = [
    "OSM_DOWNLOAD_URL",
    "MAX_PREFETCH_TILES",
    "get_osm_download_source",
    "xyz_range_for_bbox",
    "count_tiles",
    "estimate_bytes",
    "tile_url",
    "tile_cache_fn",
    "tms_y",
    "create_mbtiles",
    "TilePrefetcher",
]

import os
import sqlite3
import threading
import time
from math import cos, floor, log, pi, tan
from os.path import exists

import requests
from kivy.clock import Clock

from mapview.source import MapSource
from mapview.constants import MAX_LATITUDE, MIN_LATITUDE
from mapview.utils import clamp, tile_cache_fn, tile_url

# OpenStreetMap tile server, over HTTPS. The map display itself uses the
# plain HTTP endpoint for compatibility, but bulk downloads always use
# HTTPS, and are governed by the OSM tile usage policy at
# https://operations.osmfoundation.org/policies/tiles/
OSM_DOWNLOAD_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"

# Hard upper bound on the number of tiles in a single download, to keep
# downloads a reasonable size, protect the device, and be polite to the
# upstream tile server.
MAX_PREFETCH_TILES = 15000

# Approximate size of one cached 256x256 OSM tile, used for estimates.
ESTIMATED_TILE_BYTES = 15000

USER_AGENT = "Sideband"

REQUEST_TIMEOUT    = 10
REQUEST_ATTEMPTS   = 2
REQUEST_RETRY_WAIT = 1.0
DEFAULT_WORKERS    = 3


def get_osm_download_source(cache_dir):
    """
    Returns the :class:`MapSource` used for prefetching. It shares the
    ``osm`` cache key with the normal online OSM layer, so prefetched
    tiles are immediately usable offline and show up in the map cache.
    """
    return MapSource(
        url=OSM_DOWNLOAD_URL,
        cache_key="osm",
        min_zoom=0,
        max_zoom=19,
        image_ext="png",
        attribution=MapSource.attribution_osm,
        subdomains="abc",
        quad_key=False,
        cache_dir=cache_dir,
    )


def _lon_to_tile_x(lon, z):
    lon = clamp(lon, -180.0, 180.0)
    return int(floor((lon + 180.0) / 360.0 * (2 ** z)))


def _lat_to_tile_y(lat, z):
    """Converts a latitude to an XYZ (top-origin) tile row"""
    lat = clamp(lat, MIN_LATITUDE, MAX_LATITUDE)
    lat = lat * pi / 180.0
    return int(floor((1.0 - log(tan(lat) + 1.0 / cos(lat)) / pi) / 2.0 * (2 ** z)))


def xyz_range_for_bbox(source, bbox, zoom):
    """
    Returns the inclusive tile range ``(x_first, y_first, x_last, y_last)``
    covering the geographic bounding box ``(lat_first, lon_first, lat_last,
    lon_last)`` at the given zoom level. As in :meth:`MapView.get_bbox`,
    the first coordinate pair is the bottom/left corner and the second is
    the top/right corner, but the order does not actually matter here.
    """
    if zoom < 0:
        raise ValueError("Zoom level cannot be negative")

    lat1, lon1, lat2, lon2 = bbox
    n = 2 ** zoom
    west  = min(lon1, lon2)
    east  = max(lon1, lon2)
    south = min(lat1, lat2)
    north = max(lat1, lat2)

    x_first = _lon_to_tile_x(west, zoom)
    x_last  = _lon_to_tile_x(east, zoom)
    y_first = _lat_to_tile_y(north, zoom)
    y_last  = _lat_to_tile_y(south, zoom)

    x_first = int(clamp(x_first, 0, n - 1))
    x_last  = int(clamp(x_last,  0, n - 1))
    y_first = int(clamp(y_first, 0, n - 1))
    y_last  = int(clamp(y_last,  0, n - 1))

    return x_first, y_first, x_last, y_last


def count_tiles(source, bbox, min_zoom, max_zoom):
    """
    Returns the total number of tiles needed to cover the bounding box for
    every zoom level from ``min_zoom`` to ``max_zoom``, inclusive.
    """
    total = 0
    for z in range(int(min_zoom), int(max_zoom) + 1):
        x_first, y_first, x_last, y_last = xyz_range_for_bbox(source, bbox, z)
        total += (x_last - x_first + 1) * (y_last - y_first + 1)
    return total


def estimate_bytes(tile_count):
    """Returns a rough download size estimate, in bytes."""
    return int(tile_count) * ESTIMATED_TILE_BYTES


def tms_y(z, y):
    """Converts an XYZ (top-origin) tile row to an MBTiles TMS row."""
    return (2 ** z) - 1 - int(y)


def create_mbtiles(path, source, bbox, min_zoom, max_zoom, name=None):
    """
    Creates an empty raster MBTiles file at ``path``, with metadata
    describing the source and the covered region, and returns an open
    connection to it. Metadata is written before any tiles are inserted,
    so a partially completed (or cancelled) download is still a valid
    MBTiles file.
    """
    db = sqlite3.connect(path, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS tiles ("
        "zoom_level INTEGER, "
        "tile_column INTEGER, "
        "tile_row INTEGER, "
        "tile_data BLOB)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS tile_index "
        "ON tiles (zoom_level, tile_column, tile_row)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT)"
    )

    lat1, lon1, lat2, lon2 = bbox
    west  = min(lon1, lon2)
    east  = max(lon1, lon2)
    south = min(lat1, lat2)
    north = max(lat1, lat2)
    center_lat = (north + south) / 2.0
    center_lon = (east + west) / 2.0
    center_zoom = int((int(min_zoom) + int(max_zoom)) / 2)

    if name is None:
        name = os.path.basename(path)

    metadata = [
        ("name",        str(name)),
        ("format",      str(source.image_ext)),
        ("type",        "basemap"),
        ("version",     "1.0"),
        ("description", "Map section downloaded with Sideband"),
        ("attribution", "Maps & Data (c) OpenStreetMap contributors"),
        ("minzoom",     str(int(min_zoom))),
        ("maxzoom",     str(int(max_zoom))),
        ("bounds",      "{:.6f},{:.6f},{:.6f},{:.6f}".format(south, west, north, east)),
        ("center",      "{:.6f},{:.6f},{}".format(center_lat, center_lon, center_zoom)),
    ]
    db.executemany("INSERT INTO metadata (name, value) VALUES (?, ?)", metadata)
    db.commit()

    return db


class TilePrefetcher:
    """
    Downloads every tile covering a region, in a small background thread
    pool that is kept separate from the map view's own tile downloader, so
    the visible map is not starved while a region download is running.

    Callbacks are always invoked on the Kivy event loop thread, and are
    given the prefetcher instance as their only argument:

    * ``progress`` – called periodically while downloading. The instance
      exposes ``downloaded``, ``total``, ``skipped`` and ``failed`` counts.
    * ``finished`` – called once when the download completes or is stopped.
    * ``error``  – called with the prefetcher as argument if the job could
      not be started at all (for example an unwritable destination).
    """

    def __init__(self, source, bbox, min_zoom, max_zoom, mbtiles_path,
                 progress=None, finished=None, error=None, workers=None):
        self.source       = source
        self.bbox         = bbox
        self.min_zoom     = int(min_zoom)
        self.max_zoom     = int(max_zoom)
        self.mbtiles_path = mbtiles_path
        self.workers      = workers or DEFAULT_WORKERS

        self.on_progress = progress
        self.on_finished = finished
        self.on_error    = error

        self.downloaded  = 0
        self.skipped     = 0
        self.failed      = 0
        self.total       = 0
        self.cache_only  = False

        self._cancel     = threading.Event()
        self._active     = False
        self._lock       = threading.Lock()
        self._queue      = []
        self._pending    = 0
        self._db         = None
        self._last_commit = 0.0
        self._progress_event = None

    def is_running(self):
        return self._active

    def cancel(self):
        """Requests the download to stop. Remaining tiles are discarded."""
        self._cancel.set()

    def stop(self):
        """Alias for :meth:`cancel`."""
        self.cancel()

    def start(self, cache_only=False):
        """
        Builds the tile queue and starts downloading. When ``cache_only``
        is set, no MBTiles file is written, and tiles are only placed in
        the map cache.
        """
        if self._active:
            return

        self.cache_only = cache_only
        self.downloaded = 0
        self.skipped    = 0
        self.failed     = 0
        self._pending   = 0
        self._cancel.clear()

        if not cache_only:
            try:
                self._db = create_mbtiles(
                    self.mbtiles_path,
                    self.source,
                    self.bbox,
                    self.min_zoom,
                    self.max_zoom,
                )
            except Exception as e:
                self._active = False
                self._db = None
                if self.on_error:
                    Clock.schedule_once(lambda dt: self.on_error(self), 0)
                else:
                    raise
                return

        # The queue is built after the database is opened, so tiles that are
        # already in the map cache can be copied straight into the MBTiles
        # file without being downloaded again.
        self._queue = self._build_queue()
        self.total  = len(self._queue)
        self._active    = True

        self._progress_event = Clock.schedule_interval(
            self._emit_progress, 0.25
        )
        self._dispatch_progress()

        if self.total == 0:
            self._finish()
            return

        for i in range(min(self.workers, self.total)):
            self._start_next()

    def _build_queue(self):
        queue = []
        for z in range(self.min_zoom, self.max_zoom + 1):
            x_first, y_first, x_last, y_last = xyz_range_for_bbox(
                self.source, self.bbox, z
            )
            for x in range(x_first, x_last + 1):
                for y in range(y_first, y_last + 1):
                    # Already cached tiles cost nothing, so they are left
                    # out of the queue (and out of the progress total) and
                    # written straight into the MBTiles file instead.
                    if exists(tile_cache_fn(self.source, x, y, z)):
                        try:
                            with open(tile_cache_fn(self.source, x, y, z), "rb") as fd:
                                self._write_tile(x, y, z, fd.read())
                            self.skipped += 1
                        except Exception:
                            queue.append((x, y, z))
                    else:
                        queue.append((x, y, z))
        return queue

    def _start_next(self):
        with self._lock:
            if self._cancel.is_set() or not self._queue:
                return
            x, y, z = self._queue.pop(0)
            self._pending += 1

        threading.Thread(
            target=self._worker,
            args=(x, y, z),
            daemon=True,
        ).start()

    def _worker(self, x, y, z):
        cache_fn = None
        try:
            with self._lock:
                cancelled = self._cancel.is_set()

            if cancelled:
                return

            cache_fn = tile_cache_fn(self.source, x, y, z)
            if exists(cache_fn):
                data = None
                with self._lock:
                    self.skipped += 1
            else:
                data = self._fetch(x, y, z)
                if data is None:
                    with self._lock:
                        self.failed += 1
                    return
                try:
                    with open(cache_fn, "wb") as fd:
                        fd.write(data)
                except Exception:
                    # A failed cache write is not fatal; the tile is
                    # still written to the MBTiles file below.
                    pass

            if not self.cache_only and data is not None:
                self._write_tile(x, y, z, data)

            with self._lock:
                self.downloaded += 1

        except Exception as e:
            with self._lock:
                self.failed += 1
            try:
                import RNS
                RNS.log("Error while downloading map tile: " + str(e), RNS.LOG_ERROR)
            except Exception:
                print("Map download: error while fetching tile: " + str(e))

        finally:
            with self._lock:
                self._pending -= 1
                done = self._cancel.is_set() or (
                    not self._queue and self._pending <= 0
                )

            if done:
                self._finish()
            else:
                self._start_next()

    def _fetch(self, x, y, z):
        uri = tile_url(self.source, x, y, z)
        for attempt in range(REQUEST_ATTEMPTS):
            try:
                response = requests.get(
                    uri,
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                return response.content
            except Exception as e:
                if attempt < REQUEST_ATTEMPTS - 1:
                    time.sleep(REQUEST_RETRY_WAIT)
                else:
                    try:
                        import RNS
                        RNS.log(
                            "Error while fetching map tile " + uri + ": " + str(e),
                            RNS.LOG_ERROR,
                        )
                    except Exception:
                        pass
        return None

    def _write_tile(self, x, y, z, data):
        with self._lock:
            if self._db is None or self._cancel.is_set():
                return
            try:
                self._db.execute(
                    "INSERT OR REPLACE INTO tiles "
                    "(zoom_level, tile_column, tile_row, tile_data) "
                    "VALUES (?, ?, ?, ?)",
                    (z, x, tms_y(z, y), sqlite3.Binary(data)),
                )
                now = time.time()
                if now - self._last_commit > 0.5:
                    self._db.commit()
                    self._last_commit = now
            except Exception as e:
                try:
                    import RNS
                    RNS.log("Error while writing map tile: " + str(e), RNS.LOG_ERROR)
                except Exception:
                    print("Map download: error while writing tile: " + str(e))

    def _finish(self):
        with self._lock:
            if not self._active:
                return
            self._active = False
            self._queue = []
            db = self._db
            self._db = None

        if db is not None:
            try:
                db.commit()
                db.close()
            except Exception:
                pass

        if self._progress_event is not None:
            try:
                self._progress_event.cancel()
            except Exception:
                pass
            self._progress_event = None

        Clock.schedule_once(self._emit_finished, 0)

    def _emit_progress(self, dt=None):
        self._dispatch_progress()

    def _dispatch_progress(self):
        if self.on_progress:
            self.on_progress(self)

    def _emit_finished(self, dt=None):
        self._dispatch_progress()
        if self.on_finished:
            self.on_finished(self)
