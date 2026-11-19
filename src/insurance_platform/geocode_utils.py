"""Geocoding utilities for address-to-coordinate conversion.

Provides ZCTA centroid lookup for fast offline geocoding by postal code.
"""

from settings import get_logger

logger = get_logger(__name__)


def create_postal_centroid_lookup(zcta_gdf) -> dict:
    """
    Create a lookup dict of postal_code -> (lat, lon) from ZCTA polygons.
    Uses centroid of each ZCTA polygon.
    """
    lookup = {}
    for _, row in zcta_gdf.iterrows():
        zip_code = str(row["zip_code"]).zfill(5)
        centroid = row.geometry.centroid
        lookup[zip_code] = (centroid.y, centroid.x)  # lat, lon
    return lookup
