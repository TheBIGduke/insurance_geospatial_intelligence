# Authors: Mauricio Arteaga
# Kaléin Tamaríz
import os
from pathlib import Path
import yaml
import logging
import sys

try:
    import colorlog

    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False

PACKAGE_NAME: str = "insurance_platform"

APP_DATA_DIR: str = os.path.join(os.path.expanduser("~"), f".{PACKAGE_NAME}")

PROJECT_DIR: str = os.path.dirname(
    os.path.abspath(__file__)
)  # Directory of the settings.py file

# Get more attributes from 'config.yaml'
config_path: Path = Path(APP_DATA_DIR) / "config" / "config.yaml"

if config_path.exists():
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
else:
    # Fallback to template config for development
    template_path = Path(PROJECT_DIR) / "config" / "config_template.yaml"
    if template_path.exists():
        with open(template_path, "r") as f:
            config = yaml.safe_load(f)
        print(
            f"Using template config from {template_path}. For production, run installer.sh to create config at {config_path}"
        )
    else:
        print(
            f"Config file not found at {config_path}. Please run installer.sh to create it."
        )
        exit(1)

# Database URL from config
DB_CONFIG = config["database"]
DATABASE_URL = f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['name']}"

# SQLAlchemy engine options
ENGINE_OPTIONS = {
    "pool_pre_ping": True,
    "pool_recycle": DB_CONFIG.get("pool_recycle", 3600),
    "pool_size": DB_CONFIG.get("pool_size", 5),
    "max_overflow": DB_CONFIG.get("max_overflow", 10),
    "pool_timeout": DB_CONFIG.get("pool_timeout", 30),
}

# Census API
CENSUS_CONFIG = config.get("census", {})
CENSUS_API_KEY = CENSUS_CONFIG.get("api_key", "")
CENSUS_BASE_URL = CENSUS_CONFIG.get(
    "base_url", "https://api.census.gov/data/2023/acs/acs5"
)

# Logging configuration with color support
LOG_CONFIG = config.get("logging", {})
LOG_LEVEL = getattr(logging, LOG_CONFIG.get("level", "INFO"))
LOG_FORMAT = LOG_CONFIG.get("format", "%(asctime)s-%(name)s-%(levelname)s-%(message)s")
LOG_DATEFMT = LOG_CONFIG.get("datefmt", "%Y-%m-%d %H:%M:%S")
LOG_COLORS = LOG_CONFIG.get("colors", True) and HAS_COLORLOG and sys.stdout.isatty()

if LOG_COLORS:
    # Colored logging with colorlog
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            fmt="%(log_color)s%(asctime)s-%(name)s-%(levelname)s-%(message)s",
            datefmt=LOG_DATEFMT,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
            secondary_log_colors={},
            style="%",
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    root_logger.handlers = [handler]
else:
    # Standard logging without colors
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
    )


# Convenience function for getting colored loggers
def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the configured formatting."""
    return logging.getLogger(name)


# Data paths
DATA_CONFIG = config.get("data", {})
PROJECT_ROOT = Path(PROJECT_DIR)
ZCTA_SHAPEFILE = PROJECT_ROOT / DATA_CONFIG.get(
    "zcta_shapefile", "data/tl_2026_us_zcta520.zip"
)
CRASH_CSV = PROJECT_ROOT / DATA_CONFIG.get("crash_csv", "data/my_list.csv")
AGENTS_CSV = PROJECT_ROOT / DATA_CONFIG.get(
    "agents_csv",
    "data/agents_tdi_2026.csv",
)
CENSUS_CSV = PROJECT_ROOT / DATA_CONFIG.get(
    "census_csv", "data/ACSST1Y2025.S2504-2026-11-18T174206.csv"
)
ROADS_SHAPEFILE = PROJECT_ROOT / DATA_CONFIG.get(
    "roads_shapefile", "data/txdot_roads.shp"
)

# Export settings
EXPORT_CONFIG = config.get("export", {})
EXPORT_DIR = PROJECT_ROOT / EXPORT_CONFIG.get("dir", "exports")
EXPORT_DIR.mkdir(exist_ok=True)

# Directory paths (for backward compatibility)
DATA_DIR = PROJECT_ROOT / "data"
SQL_DIR = PROJECT_ROOT / "sql"

# Region constants
REGION_CONFIG = config.get("region", {})
REGION_STATE_FIPS = REGION_CONFIG.get("state_fips", "48")
REGION_ZCTA_PREFIX = REGION_CONFIG.get("zcta_prefix", "48")
REGION_BBOX = tuple(REGION_CONFIG.get("bbox", [-106.65, 25.84, -93.51, 36.50]))

# CRS settings
CRS_CONFIG = config.get("crs", {})
TARGET_CRS = CRS_CONFIG.get("target", "EPSG:4326")

# Table names
TABLE_ZCTA = "zip_code_boundaries"
TABLE_CRASHES = "crashes"
TABLE_DEMOGRAPHICS = "census_demographics"
TABLE_COMPETITORS = "competitors"
TABLE_ROADS = "roads"
TABLE_FINAL = "zip_opportunity_metrics"

# Chunk sizes for large data loading
PIPELINE_CONFIG = config.get("pipeline", {})
CHUNK_SIZE = PIPELINE_CONFIG.get("chunk_size", 10000)

# Census API variables for ZIP-level data
ACS_VARIABLES = {
    # DP04 - Selected Housing Characteristics
    "median_home_value": "DP04_0089E",
    "median_gross_rent": "DP04_0134E",
    "total_housing_units": "DP04_0001E",
    "occupied_housing_units": "DP04_0002E",
    "owner_occupied": "DP04_0003E",
    "renter_occupied": "DP04_0004E",
    "vehicles_per_household": "DP04_0058E",
    # B25044 - Tenure by Vehicles Available
    "vehicles_available_total": "B25044_001E",
    "vehicles_0": "B25044_003E",
    "vehicles_1": "B25044_004E",
    "vehicles_2": "B25044_005E",
    "vehicles_3": "B25044_006E",
    "vehicles_4": "B25044_007E",
    # B19013 - Median Household Income
    "median_household_income": "B19013_001E",
    # B16001 - Language Spoken at Home
    "spanish_speaking_home": "B16001_006E",
    "total_population_5plus": "B16001_001E",
}

# Derived metric weights
METRIC_WEIGHTS = {
    "standard_market": {
        "median_home_value": 0.30,
        "vehicles_per_household": 0.25,
        "franchise_dealers": 0.20,
        "median_income": 0.15,
        "renter_pct": -0.10,
    },
    "non_standard_market": {
        "renter_pct": 0.30,
        "independent_dealers": 0.25,
        "median_income": -0.20,
        "crash_density": 0.15,
        "spanish_speaking_pct": 0.10,
    },
    "vulnerability_index": {
        "competitor_density": -0.40,
        "review_score_proxy": 0.30,
        "traffic_visibility": 0.30,
    },
    "visibility_multiplier": {
        "avg_aadt": 0.50,
        "max_aadt": 0.30,
        "road_density": 0.20,
    },
    "risk_alignment": {
        "crash_density": -0.40,
        "severe_crash_pct": -0.30,
        "hail_proxy": -0.30,
    },
}
