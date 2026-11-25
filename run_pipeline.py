#!/usr/bin/env python3
"""
Insurance Geospatial Intelligence Platform
Main Orchestration Script

Run the complete pipeline:
1. Load all data into PostGIS
2. Run spatial joins and aggregations
3. Calculate derived metrics
4. Export for Kepler.gl visualization

Usage:
    python run_pipeline.py [--skip-load] [--skip-sql] [--skip-export]
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from settings import (
    DATABASE_URL,
    SQL_DIR,
    get_logger,
)
from insurance_platform.load_data import run_full_pipeline
from insurance_platform.export_kepler import run_exports

logger = get_logger(__name__)


def run_sql_file(sql_file: Path, db_url: str):
    """Execute a SQL file using psql."""
    logger.info(f"Running SQL: {sql_file.name}")
    # Convert SQLAlchemy URL to psql-compatible URL
    psql_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    try:
        result = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=on", psql_url, "-f", str(sql_file)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error(f"SQL execution failed: {result.stderr}")
            return False
        logger.info(f"Completed: {sql_file.name}")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"SQL execution timed out: {sql_file.name}")
        return False
    except Exception as e:
        logger.error(f"Error running SQL: {e}")
        return False


def run_sql_pipeline(db_url: str):
    """Run all SQL migration files in order."""
    sql_files = [
        "01_create_schema.sql",
        "02_spatial_joins.sql",
        "03_derived_metrics.sql",
    ]

    for sql_file in sql_files:
        sql_path = SQL_DIR / sql_file
        if not sql_path.exists():
            logger.error(f"SQL file not found: {sql_path}")
            return False

        if not run_sql_file(sql_path, db_url):
            logger.error(f"Failed at {sql_file}, stopping pipeline")
            return False

    return True


def check_database_connection(db_url: str) -> bool:
    """Verify database is accessible."""
    try:
        import psycopg2
        from urllib.parse import urlparse

        # Parse URL to DSN format for psycopg2
        parsed = urlparse(db_url)
        dsn = f"host={parsed.hostname} port={parsed.port or 5432} dbname={parsed.path.lstrip('/')} user={parsed.username} password={parsed.password or ''}"
        conn = psycopg2.connect(dsn)
        conn.close()
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Insurance Geospatial Intelligence Pipeline"
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Skip data loading phase (assumes data already in DB)",
    )
    parser.add_argument(
        "--skip-sql",
        action="store_true",
        help="Skip SQL spatial joins and metrics phase",
    )
    parser.add_argument(
        "--skip-export", action="store_true", help="Skip Kepler.gl export phase"
    )
    parser.add_argument(
        "--only-load", action="store_true", help="Only run data loading phase"
    )
    parser.add_argument("--only-sql", action="store_true", help="Only run SQL pipeline")
    parser.add_argument(
        "--only-export", action="store_true", help="Only run export phase"
    )

    args = parser.parse_args()

    # Build DB URL for psql (without SQLAlchemy dialect prefix)
    psql_url = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")

    logger.info("=" * 60)
    logger.info("Insurance Geospatial Intelligence Pipeline")
    logger.info("=" * 60)

    # Check database connection
    if not check_database_connection(psql_url):
        logger.error(
            "Cannot connect to database. Ensure PostgreSQL is running and database exists."
        )
        logger.info(
            "Create database with: createdb -h localhost -U postgres insurance_geospatial_intelligence"
        )
        sys.exit(1)

    success = True

    # Phase 1: Data Loading
    if not (args.skip_load or args.only_sql or args.only_export):
        logger.info("\n>>> PHASE 1: Data Loading")
        logger.info("-" * 40)
        try:
            run_full_pipeline()
            logger.info("Data loading completed successfully")
        except Exception as e:
            logger.error(f"Data loading failed: {e}")
            success = False

    if args.only_load:
        logger.info("Only-load mode, exiting.")
        sys.exit(0 if success else 1)

    # Phase 2: SQL Pipeline
    if not (args.skip_sql or args.only_load or args.only_export):
        if success:
            logger.info("\n>>> PHASE 2: Spatial Joins & Derived Metrics")
            logger.info("-" * 40)
            success = run_sql_pipeline(psql_url)
        else:
            logger.warning("Skipping SQL phase due to previous failure")

    if args.only_sql:
        logger.info("Only-SQL mode, exiting.")
        sys.exit(0 if success else 1)

    # Phase 3: Export
    if not (args.skip_export or args.only_load or args.only_sql):
        if success:
            logger.info("\n>>> PHASE 3: Kepler.gl Export")
            logger.info("-" * 40)
            try:
                run_exports()
                logger.info("Export completed successfully")
            except Exception as e:
                logger.error(f"Export failed: {e}")
                success = False
        else:
            logger.warning("Skipping export due to previous failure")

    if args.only_export:
        logger.info("Only-export mode, exiting.")
        sys.exit(0 if success else 1)

    # Summary
    logger.info("\n" + "=" * 60)
    if success:
        logger.info("PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info("Output files in exports/ directory:")
        logger.info("  - zip_opportunity_metrics.geojson (for Kepler.gl)")
        logger.info("  - zip_opportunity_metrics.csv (for Kepler.gl)")
        logger.info("  - kepler_config.json (Kepler.gl visualization config)")
        logger.info("\nNext steps:")
        logger.info("  1. Open https://kepler.gl/")
        logger.info("  2. Drag and drop zip_opportunity_metrics.geojson")
        logger.info("  3. Import kepler_config.json for pre-configured visualization")
    else:
        logger.error("PIPELINE FAILED - Check logs above")
    logger.info("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
