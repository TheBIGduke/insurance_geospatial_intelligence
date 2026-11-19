"""Configuration for Insurance Geospatial Intelligence Platform.

All configuration is now loaded from settings.py which reads from ~/.insurance_platform/config/config.yaml
This file re-exports the settings for backward compatibility.
"""

from settings import (
    PROJECT_ROOT,
    DATA_DIR,
    SQL_DIR,
    DATABASE_URL,
    ENGINE_OPTIONS,
    ZCTA_SHAPEFILE,
    CRASH_CSV,
    AGENTS_CSV,
    CENSUS_CSV,
    ROADS_SHAPEFILE,
    REGION_STATE_FIPS,
    REGION_ZCTA_PREFIX,
    TARGET_CRS,
    REGION_BBOX,
    TABLE_ZCTA,
    TABLE_CRASHES,
    TABLE_DEMOGRAPHICS,
    TABLE_COMPETITORS,
    TABLE_ROADS,
    TABLE_FINAL,
    CHUNK_SIZE,
    METRIC_WEIGHTS,
    EXPORT_DIR,
)

# Re-export for backward compatibility
__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "SQL_DIR",
    "DATABASE_URL",
    "ENGINE_OPTIONS",
    "ZCTA_SHAPEFILE",
    "CRASH_CSV",
    "AGENTS_CSV",
    "CENSUS_CSV",
    "ROADS_SHAPEFILE",
    "REGION_STATE_FIPS",
    "REGION_ZCTA_PREFIX",
    "TARGET_CRS",
    "REGION_BBOX",
    "TABLE_ZCTA",
    "TABLE_CRASHES",
    "TABLE_DEMOGRAPHICS",
    "TABLE_COMPETITORS",
    "TABLE_ROADS",
    "TABLE_FINAL",
    "CHUNK_SIZE",
    "METRIC_WEIGHTS",
    "EXPORT_DIR",
]
