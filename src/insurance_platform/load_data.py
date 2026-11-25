"""Main data loading pipeline for Insurance Geospatial Intelligence Platform."""

import logging
import sys
import time
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
import requests
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
    ACS_VARIABLES,
    CENSUS_API_KEY,
    CENSUS_BASE_URL,
)
from insurance_platform.geocode_utils import create_postal_centroid_lookup

logger = get_logger(__name__)

# Census API batch size (max 50 variables per request)
CENSUS_BATCH_SIZE = 45
# Rate limiting: 500 requests/second default, be conservative
CENSUS_RATE_LIMIT_DELAY = 0.01  # seconds between requests


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
    Load Census demographics data from ACS API.
    Falls back to placeholder if no API key configured.
    """
    # Get list of ZIP codes from ZCTA data
    if tx_zcta is not None:
        zip_codes = tx_zcta["zip_code"].tolist()
    else:
        # Fallback: load from database
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT zip_code FROM {TABLE_ZCTA}"))
            zip_codes = [row[0] for row in result]

    logger.info(f"Need demographics for {len(zip_codes)} ZIP codes")

    # Check if Census API key is configured
    if not CENSUS_API_KEY:
        logger.warning("No Census API key configured. Using placeholder demographics.")
        demographics_df = _create_placeholder_demographics(zip_codes)
    else:
        logger.info("Loading Census demographics from ACS API...")
        demographics_df = _fetch_census_acs_data(zip_codes)

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


def _fetch_census_acs_data(zip_codes: list) -> pd.DataFrame:
    """
    Fetch real Census ACS data for the given ZIP codes.
    Batches requests to stay within API limits (max 50 variables per request).
    """
    if not CENSUS_API_KEY:
        return _create_placeholder_demographics(zip_codes)

    # Convert variable dict to list of (name, code) tuples
    variables = list(ACS_VARIABLES.items())
    var_names = [v[0] for v in variables]
    var_codes = [v[1] for v in variables]

    # Split variables into batches (max ~45 per request to be safe)
    batches = []
    for i in range(0, len(var_codes), CENSUS_BATCH_SIZE):
        batch_vars = var_codes[i : i + CENSUS_BATCH_SIZE]
        batch_names = var_names[i : i + CENSUS_BATCH_SIZE]
        batches.append((batch_names, batch_vars))

    logger.info(
        f"Fetching {len(variables)} variables in {len(batches)} batches for {len(zip_codes)} ZIP codes"
    )

    # Prepare ZIP code filter for Texas (state FIPS 48)
    # API expects format: zip code tabulation area:*
    # with in=state:48 for Texas only
    zip_filter = ",".join(zip_codes)

    all_results = {}

    for batch_idx, (batch_names, batch_vars) in enumerate(batches):
        # Build API request
        vars_param = ",".join(["NAME"] + batch_vars)
        url = f"{CENSUS_BASE_URL}?get={vars_param}&for=zip%20code%20tabulation%20area:{zip_filter}&in=state:48&key={CENSUS_API_KEY}"

        try:
            logger.debug(
                f"Batch {batch_idx + 1}/{len(batches)}: requesting {len(batch_vars)} variables"
            )
            response = requests.get(url, timeout=60)

            if response.status_code == 429:
                # Rate limited - wait and retry
                logger.warning("Rate limited by Census API, waiting 2 seconds...")
                time.sleep(2)
                response = requests.get(url, timeout=60)

            response.raise_for_status()
            data = response.json()

            # First row is headers
            headers = data[0]
            rows = data[1:]

            # Map results by ZIP code
            for row in rows:
                row_dict = dict(zip(headers, row))
                zip_code = row_dict.get("zip code tabulation area", "").zfill(5)
                if zip_code not in all_results:
                    all_results[zip_code] = {}
                for var_name in batch_names:
                    var_code = ACS_VARIABLES[var_name]
                    value = row_dict.get(var_code)
                    # Handle missing/suppressed data (empty string or negative)
                    if value is not None and value != "" and value != "-":
                        try:
                            all_results[zip_code][var_name] = float(value)
                        except (ValueError, TypeError):
                            all_results[zip_code][var_name] = None
                    else:
                        all_results[zip_code][var_name] = None

            # Rate limiting
            if batch_idx < len(batches) - 1:
                time.sleep(CENSUS_RATE_LIMIT_DELAY)

        except requests.exceptions.RequestException as e:
            logger.error(f"Census API request failed for batch {batch_idx}: {e}")
            # Continue with other batches

    # If no data was fetched from API (all batches failed), fall back to placeholder
    if not all_results:
        logger.warning(
            "All Census API batches failed. Falling back to placeholder demographics."
        )
        return _create_placeholder_demographics(zip_codes)

    # Build DataFrame with all variables
    records = []
    for zip_code in zip_codes:
        record = {"zip_code": zip_code}
        if zip_code in all_results:
            record.update(all_results[zip_code])
        else:
            # ZIP not found in API response - fill with None
            for var_name in var_names:
                record[var_name] = None
        records.append(record)

    df = pd.DataFrame(records)

    # Compute derived columns
    df = _compute_derived_demographics(df)

    logger.info(f"Successfully fetched Census data for {len(df)} ZIP codes")
    return df


def _compute_derived_demographics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute derived demographic metrics from raw ACS variables."""
    # Make a copy to avoid SettingWithCopyWarning
    df = df.copy()

    # Spanish speaking percentage
    if "spanish_speaking_home" in df.columns and "total_population_5plus" in df.columns:
        df["spanish_speaking_pct"] = (
            df["spanish_speaking_home"]
            / df["total_population_5plus"].replace(0, pd.NA)
            * 100
        ).round(1)

    # Hispanic population percentage
    if "hispanic_population" in df.columns and "total_population" in df.columns:
        df["hispanic_pct"] = (
            df["hispanic_population"] / df["total_population"].replace(0, pd.NA) * 100
        ).round(1)

    # Renter percentage
    if "renter_occupied" in df.columns and "owner_occupied" in df.columns:
        # Need occupied_housing_units - derive from owner + renter
        df["occupied_housing_units"] = df["owner_occupied"] + df["renter_occupied"]
        df["renter_pct"] = (
            df["renter_occupied"] / df["occupied_housing_units"].replace(0, pd.NA) * 100
        ).round(1)

    # Vehicles per household
    if (
        "vehicles_available_total" in df.columns
        and "occupied_housing_units" in df.columns
    ):
        df["vehicles_per_household"] = (
            df["vehicles_available_total"]
            / df["occupied_housing_units"].replace(0, pd.NA)
        ).round(2)

    # Commute percentages
    if "total_commuters" in df.columns:
        total_commuters = df["total_commuters"].replace(0, pd.NA)
        if "commute_car_alone" in df.columns:
            df["car_commute_pct"] = (
                df["commute_car_alone"] / total_commuters * 100
            ).round(1)
        if "commute_carpool" in df.columns:
            df["carpool_commute_pct"] = (
                df["commute_carpool"] / total_commuters * 100
            ).round(1)
        if "commute_transit" in df.columns:
            df["transit_commute_pct"] = (
                df["commute_transit"] / total_commuters * 100
            ).round(1)
        if "commute_walk" in df.columns:
            df["walk_commute_pct"] = (df["commute_walk"] / total_commuters * 100).round(
                1
            )
        if "commute_work_home" in df.columns:
            df["wfh_pct"] = (df["commute_work_home"] / total_commuters * 100).round(1)
        if "commute_time_avg" in df.columns and "total_commuters" in df.columns:
            # Average commute time in minutes
            df["avg_commute_time"] = (df["commute_time_avg"] / total_commuters).round(1)

    # Uninsured rate (using B27001_005E as proxy)
    if "uninsured_rate" in df.columns and "total_population" in df.columns:
        df["uninsured_pct"] = (
            df["uninsured_rate"] / df["total_population"].replace(0, pd.NA) * 100
        ).round(1)

    # Fill NaN with None for database compatibility
    df = df.where(pd.notna(df), None)

    return df


def _create_placeholder_demographics(zip_codes: list) -> pd.DataFrame:
    """Create placeholder demographic data for ZIP codes (fallback only)."""
    import numpy as np

    np.random.seed(42)
    n = len(zip_codes)

    # Generate realistic placeholder data
    data = {
        "zip_code": zip_codes,
        "median_home_value": np.random.lognormal(12.5, 0.5, n).astype(int),
        "median_gross_rent": np.random.normal(1100, 200, n).astype(int),
        "median_household_income": np.random.lognormal(11.0, 0.4, n).astype(int),
        "vehicles_per_household": np.random.uniform(1.2, 2.5, n).round(2),
        "renter_pct": np.random.uniform(20, 60, n).round(1),
        "spanish_speaking_pct": np.random.uniform(5, 40, n).round(1),
        "hispanic_pct": np.random.uniform(10, 90, n).round(1),
        "total_housing_units": np.random.randint(500, 15000, n),
        "occupied_housing_units": np.random.randint(400, 12000, n),
        "owner_occupied": np.random.randint(200, 8000, n),
        "renter_occupied": np.random.randint(100, 5000, n),
        "car_commute_pct": np.random.uniform(70, 95, n).round(1),
        "transit_commute_pct": np.random.uniform(0, 10, n).round(1),
        "wfh_pct": np.random.uniform(5, 25, n).round(1),
        "avg_commute_time": np.random.uniform(15, 45, n).round(1),
        "uninsured_pct": np.random.uniform(5, 25, n).round(1),
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
