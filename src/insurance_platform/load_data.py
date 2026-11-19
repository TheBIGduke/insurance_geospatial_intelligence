"""Main data loading pipeline for Insurance Geospatial Intelligence Platform."""

import logging
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from settings import get_logger
from insurance_platform.config import (
    DATABASE_URL,
    ENGINE_OPTIONS,
    ZCTA_SHAPEFILE,
    CRASH_CSV,
    AGENTS_CSV,
    CENSUS_CSV,
    ROADS_SHAPEFILE,
    TABLE_ZCTA,
    TABLE_CRASHES,
    TABLE_DEMOGRAPHICS,
    TABLE_COMPETITORS,
    TABLE_ROADS,
    REGION_ZCTA_PREFIX,
    TARGET_CRS,
    REGION_BBOX,
    CHUNK_SIZE,
)
from insurance_platform.geocode_utils import create_postal_centroid_lookup

logger = get_logger(__name__)


def get_engine():
    """Create SQLAlchemy engine with PostGIS support."""
    return create_engine(DATABASE_URL, **ENGINE_OPTIONS)


def init_database(engine):
    """Initialize database with PostGIS extension."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis_topology;"))
        conn.commit()
    logger.info("PostGIS extensions enabled")


def load_zcta_boundaries(engine) -> gpd.GeoDataFrame:
    """
    Load ZCTA boundaries from Census shapefile.
    Filters to target region using bounding box, reprojects to EPSG:4326.
    """
    logger.info(f"Loading ZCTA boundaries from {ZCTA_SHAPEFILE}...")
    zcta = gpd.read_file(ZCTA_SHAPEFILE)

    # Filter to region using bounding box (more reliable than GEOID20 in 2026 data)
    min_lon, min_lat, max_lon, max_lat = REGION_BBOX
    region_zcta = zcta.cx[min_lon:max_lon, min_lat:max_lat].copy()
    logger.info(f"Found {len(region_zcta)} ZCTAs in bounding box")

    # Select and rename columns
    region_zcta = region_zcta[["ZCTA5CE20", "geometry"]].copy()
    region_zcta = region_zcta.rename(columns={"ZCTA5CE20": "zip_code"})

    # Ensure ZIP codes are 5-digit strings
    region_zcta["zip_code"] = region_zcta["zip_code"].astype(str).str.zfill(5)

    # Reproject to WGS84 (EPSG:4326)
    if region_zcta.crs != TARGET_CRS:
        logger.info(f"Reprojecting from {region_zcta.crs} to {TARGET_CRS}")
        region_zcta = region_zcta.to_crs(TARGET_CRS)

    # Drop dependent materialized views first (if they exist)
    with engine.connect() as conn:
        conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS zip_demographics CASCADE;"))
        conn.execute(
            text("DROP MATERIALIZED VIEW IF EXISTS zip_crash_metrics CASCADE;")
        )
        conn.execute(
            text("DROP MATERIALIZED VIEW IF EXISTS zip_competitor_metrics CASCADE;")
        )
        conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS zip_road_metrics CASCADE;"))
        conn.commit()

    # Load to PostGIS
    logger.info(f"Writing {len(region_zcta)} ZCTAs to {TABLE_ZCTA}...")
    region_zcta.to_postgis(
        TABLE_ZCTA,
        engine,
        if_exists="replace",
        index=False,
        dtype={"geometry": Geometry("MULTIPOLYGON", srid=4326)},
    )

    # Create spatial index
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ZCTA}_geom ON {TABLE_ZCTA} USING GIST (geometry);"
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ZCTA}_zip ON {TABLE_ZCTA} (zip_code);"
            )
        )
        conn.commit()

    logger.info("ZCTA boundaries loaded successfully")
    return region_zcta


def load_crash_data(
    engine, tx_zcta: Optional[gpd.GeoDataFrame] = None
) -> gpd.GeoDataFrame:
    """
    Load crash data from CSV, convert lat/lon to Points.
    Filters to valid coordinates within target region bounds.
    """
    logger.info(f"Loading crash data from {CRASH_CSV}...")
    crashes = pd.read_csv(CRASH_CSV, skiprows=10)

    # Clean data - remove "No Data" rows
    initial_count = len(crashes)
    crashes = crashes[
        (crashes["Latitude"] != "No Data") & (crashes["Longitude"] != "No Data")
    ].copy()

    # Convert to numeric
    crashes["Latitude"] = pd.to_numeric(crashes["Latitude"], errors="coerce")
    crashes["Longitude"] = pd.to_numeric(crashes["Longitude"], errors="coerce")
    crashes = crashes.dropna(subset=["Latitude", "Longitude"])

    logger.info(
        f"Cleaned crashes: {initial_count} -> {len(crashes)} (removed {initial_count - len(crashes)} invalid)"
    )

    # Filter to region bounding box
    min_lon, min_lat, max_lon, max_lat = REGION_BBOX
    crashes = crashes[
        (crashes["Longitude"] >= min_lon)
        & (crashes["Longitude"] <= max_lon)
        & (crashes["Latitude"] >= min_lat)
        & (crashes["Latitude"] <= max_lat)
    ].copy()
    logger.info(f"After region bbox filter: {len(crashes)} crashes")

    # Create geometry
    geometry = gpd.points_from_xy(
        crashes["Longitude"], crashes["Latitude"], crs=TARGET_CRS
    )
    crashes_gdf = gpd.GeoDataFrame(crashes, geometry=geometry, crs=TARGET_CRS)

    # Rename columns
    crashes_gdf = crashes_gdf.rename(columns={"Crash ID": "crash_id"})
    crashes_gdf["crash_id"] = crashes_gdf["crash_id"].astype(str)

    # Load to PostGIS
    logger.info(f"Writing {len(crashes_gdf)} crashes to {TABLE_CRASHES}...")
    crashes_gdf.to_postgis(
        TABLE_CRASHES,
        engine,
        if_exists="replace",
        index=False,
        dtype={"geometry": Geometry("POINT", srid=4326)},
    )

    # Create spatial index
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_CRASHES}_geom ON {TABLE_CRASHES} USING GIST (geometry);"
            )
        )
        conn.commit()

    logger.info("Crash data loaded successfully")
    return crashes_gdf


def load_census_demographics(
    engine, tx_zcta: Optional[gpd.GeoDataFrame] = None
) -> pd.DataFrame:
    """
    Load Census demographics data.
    Uses synthetic placeholder data (no Census API key configured by default).
    """
    logger.info("Loading Census demographics (placeholder)...")

    # Get list of ZIP codes from ZCTA data
    if tx_zcta is not None:
        zip_codes = tx_zcta["zip_code"].tolist()
    else:
        # Fallback: load from database
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT zip_code FROM {TABLE_ZCTA}"))
            zip_codes = [row[0] for row in result]

    logger.info(f"Need demographics for {len(zip_codes)} ZIP codes")

    # Generate placeholder demographics
    demographics_df = _create_placeholder_demographics(zip_codes)

    # Load to PostGIS (as non-spatial table)
    logger.info(
        f"Writing {len(demographics_df)} demographic records to {TABLE_DEMOGRAPHICS}..."
    )
    demographics_df.to_sql(
        TABLE_DEMOGRAPHICS,
        engine,
        if_exists="replace",
        index=False,
        method="multi",
        chunksize=CHUNK_SIZE,
    )

    # Create index
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_DEMOGRAPHICS}_zip ON {TABLE_DEMOGRAPHICS} (zip_code);"
            )
        )
        conn.commit()

    logger.info("Census demographics loaded successfully")
    return demographics_df


def _create_placeholder_demographics(zip_codes: list) -> pd.DataFrame:
    """Create placeholder demographic data for ZIP codes."""
    import numpy as np

    np.random.seed(42)
    n = len(zip_codes)

    # Generate realistic placeholder data
    data = {
        "zip_code": zip_codes,
        "median_home_value": np.random.lognormal(12.5, 0.5, n).astype(
            int
        ),  # ~$150k-$400k
        "median_gross_rent": np.random.normal(1100, 200, n).astype(int),
        "median_household_income": np.random.lognormal(11.0, 0.4, n).astype(
            int
        ),  # ~$40k-$80k
        "vehicles_per_household": np.random.uniform(1.2, 2.5, n).round(2),
        "renter_pct": np.random.uniform(20, 60, n).round(1),
        "spanish_speaking_pct": np.random.uniform(5, 40, n).round(1),
        "total_housing_units": np.random.randint(500, 15000, n),
        "occupied_housing_units": np.random.randint(400, 12000, n),
        "owner_occupied": np.random.randint(200, 8000, n),
        "renter_occupied": np.random.randint(100, 5000, n),
    }

    return pd.DataFrame(data)


def load_competitors(
    engine, tx_zcta: Optional[gpd.GeoDataFrame] = None
) -> gpd.GeoDataFrame:
    """
    Load insurance agents/competitors data.
    Filters to target state, classifies by appointment type, geocodes addresses.
    """
    logger.info(f"Loading competitors from {AGENTS_CSV}...")
    agents = pd.read_csv(AGENTS_CSV, low_memory=False)

    # Filter to target state (adjust state code as needed)
    tx_agents = agents[agents["State"] == "TX"].copy()
    logger.info(f"Target state agents: {len(tx_agents)}")

    # Classify appointment types for insurance market analysis
    # Focus on P&C (Property & Casualty) agents as competitors
    pnc_types = [
        "Property and Casualty",
        "Pers Lines Prop and Cas",
        "County Mutual",
        "Managing General Agent - P & C",
    ]

    # Filter to P&C relevant appointment types
    competitors = tx_agents[tx_agents["Appointment type"].isin(pnc_types)].copy()
    logger.info(f"P&C competitors: {len(competitors)}")

    # Classify as Franchise (large agencies) vs Independent (smaller)
    # Heuristic: Managing General Agent = Franchise-ish
    franchise_types = [
        "Managing General Agent - P & C",
    ]
    competitors["agency_type"] = competitors["Appointment type"].apply(
        lambda x: "Franchise" if x in franchise_types else "Independent"
    )

    # Get ZCTA centroids for geocoding by postal code
    if tx_zcta is not None:
        postal_lookup = create_postal_centroid_lookup(tx_zcta)
    else:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT zip_code, ST_Y(ST_Centroid(geometry)) as lat, ST_X(ST_Centroid(geometry)) as lon FROM {TABLE_ZCTA}"
                )
            )
            postal_lookup = {row[0]: (row[1], row[2]) for row in result}

    # Geocode using postal code centroids (fast, no API calls)
    logger.info("Geocoding competitors using ZCTA centroids...")
    competitors["latitude"] = None
    competitors["longitude"] = None

    for idx, row in competitors.iterrows():
        postal = str(row.get("Postal code", "")).strip()
        # Extract first 5 digits for ZCTA matching (handles ZIP+4 format)
        postal_5 = postal[:5].zfill(5) if postal else ""
        if postal_5 in postal_lookup:
            lat, lon = postal_lookup[postal_5]
            competitors.at[idx, "latitude"] = lat
            competitors.at[idx, "longitude"] = lon

    # Drop rows without coordinates
    initial = len(competitors)
    competitors = competitors.dropna(subset=["latitude", "longitude"])
    logger.info(
        f"Geocoded: {initial} -> {len(competitors)} (dropped {initial - len(competitors)})"
    )

    # Create geometry
    geometry = gpd.points_from_xy(
        competitors["longitude"], competitors["latitude"], crs=TARGET_CRS
    )
    competitors_gdf = gpd.GeoDataFrame(competitors, geometry=geometry, crs=TARGET_CRS)

    # Select relevant columns
    competitors_gdf = competitors_gdf[
        [
            "Agent NPN",
            "Agent name",
            "Appointment type",
            "City",
            "State",
            "Postal code",
            "agency_type",
            "geometry",
        ]
    ].copy()
    competitors_gdf = competitors_gdf.rename(
        columns={
            "Agent NPN": "npn",
            "Agent name": "name",
            "Appointment type": "appointment_type",
            "Postal code": "postal_code",
        }
    )

    # Load to PostGIS
    logger.info(f"Writing {len(competitors_gdf)} competitors to {TABLE_COMPETITORS}...")
    competitors_gdf.to_postgis(
        TABLE_COMPETITORS,
        engine,
        if_exists="replace",
        index=False,
        dtype={"geometry": Geometry("POINT", srid=4326)},
    )

    # Create indexes
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_COMPETITORS}_geom ON {TABLE_COMPETITORS} USING GIST (geometry);"
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_COMPETITORS}_zip ON {TABLE_COMPETITORS} (postal_code);"
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_COMPETITORS}_type ON {TABLE_COMPETITORS} (agency_type);"
            )
        )
        conn.commit()

    logger.info("Competitors loaded successfully")
    return competitors_gdf


def load_roads(engine) -> gpd.GeoDataFrame:
    """
    Load roadways shapefile.
    Note: This file doesn't contain AADT data - it's road geometry only.
    """
    logger.info(f"Loading roads from {ROADS_SHAPEFILE}...")
    roads = gpd.read_file(ROADS_SHAPEFILE)

    logger.info(f"Total road segments: {len(roads)}")

    # Reproject to WGS84
    if roads.crs != TARGET_CRS:
        logger.info(f"Reprojecting roads from {roads.crs} to {TARGET_CRS}")
        roads = roads.to_crs(TARGET_CRS)

    # Filter to region (by coordinate bounds)
    min_lon, min_lat, max_lon, max_lat = REGION_BBOX
    roads = roads.cx[min_lon:max_lon, min_lat:max_lat]
    logger.info(f"Roads in TX bbox: {len(roads)}")

    # Keep relevant columns
    keep_cols = [
        "GID",
        "RTE_NM",
        "RTE_NBR",
        "RDBD_TYPE",
        "COUNTY",
        "SYSTEM",
        "geometry",
    ]
    roads = roads[keep_cols].copy()

    # Add placeholder AADT column (to be populated from separate AADT dataset)
    roads["aadt"] = None

    # Load to PostGIS
    logger.info(f"Writing {len(roads)} road segments to {TABLE_ROADS}...")
    roads.to_postgis(
        TABLE_ROADS,
        engine,
        if_exists="replace",
        index=False,
        dtype={"geometry": Geometry("LINESTRING", srid=4326)},
    )

    # Create indexes
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ROADS}_geom ON {TABLE_ROADS} USING GIST (geometry);"
            )
        )
        # Column name is uppercase COUNTY in database
        conn.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS idx_{TABLE_ROADS}_county ON {TABLE_ROADS} ("COUNTY");'
            )
        )
        conn.commit()

    logger.info("Roads loaded successfully")
    return roads


def run_full_pipeline():
    """Execute the complete data loading pipeline."""
    logger.info("=" * 60)
    logger.info("Starting Insurance Geospatial Data Pipeline")
    logger.info("=" * 60)

    engine = get_engine()
    init_database(engine)

    # Load in order: boundaries first (needed for geocoding), then points, then tabular
    tx_zcta = load_zcta_boundaries(engine)
    load_crash_data(engine, tx_zcta)
    load_census_demographics(engine, tx_zcta)
    load_competitors(engine, tx_zcta)
    load_roads(engine)

    logger.info("=" * 60)
    logger.info("Pipeline completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_full_pipeline()
