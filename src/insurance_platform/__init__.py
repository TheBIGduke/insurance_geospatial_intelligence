"""Insurance Geospatial Intelligence Platform.

A location intelligence platform for the insurance market,
similar to Placer.ai or SiteZeus. Ingests public demographic, mobility,
and risk data, performs spatial joins, and outputs a unified metric
layer per ZIP code (ZCTA) for visualization in Kepler.gl.
"""

__version__ = "0.1.0"
__author__ = "kalein.mondragon"

from .config import (
    DATABASE_URL,
    DATA_DIR,
    SQL_DIR,
    EXPORT_DIR,
)

from .load_data import run_full_pipeline
from .export_kepler import run_exports

__all__ = [
    "DATABASE_URL",
    "DATA_DIR",
    "SQL_DIR",
    "EXPORT_DIR",
    "run_full_pipeline",
    "run_exports",
]
