# Author: Kaléin Tamaríz
"""
Insurance Geospatial Intelligence Platform - Main Entry Point

Single FastAPI server that:
1. Serves the MapLibre GL viewer from exports/
2. Provides API endpoints for pipeline execution
3. Handles HTTPS with auto-generated certificates
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from settings import config, get_logger

logger = get_logger(__name__)

# Add src to path for pipeline imports
sys.path.insert(0, str(Path(__file__).parent / "src"))


# --- FastAPI app ---
app = FastAPI(
    title="Insurance Geospatial Intelligence API",
    description="Location intelligence platform for insurance market analysis",
    version=config["API"]["version"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static files ---
static_folder: str = "exports"
EXPORTS_DIR = Path(__file__).parent / static_folder


# --- Pipeline state ---
pipeline_status = {
    "running": False,
    "phase": None,
    "progress": 0,
    "message": "",
    "success": None,
}


# --- Request/Response models ---
class PipelineRequest(BaseModel):
    skip_load: bool = False
    skip_sql: bool = False
    skip_export: bool = False
    only_load: bool = False
    only_sql: bool = False
    only_export: bool = False


class PipelineResponse(BaseModel):
    success: bool
    message: str
    status: dict


# --- Pipeline execution functions ---
def check_database_connection(db_url: str) -> bool:
    """Verify database is accessible."""
    try:
        import psycopg2
        from urllib.parse import urlparse

        parsed = urlparse(db_url)
        dsn = f"host={parsed.hostname} port={parsed.port or 5432} dbname={parsed.path.lstrip('/')} user={parsed.username} password={parsed.password or ''}"
        conn = psycopg2.connect(dsn)
        conn.close()
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def run_sql_file(sql_file: Path, db_url: str) -> bool:
    """Execute a SQL file using psql."""
    logger.info(f"Running SQL: {sql_file.name}")
    psql_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    try:
        result = subprocess.run(
            ["psql", psql_url, "-f", str(sql_file)],
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


def run_sql_pipeline(db_url: str, sql_dir: Path) -> bool:
    """Run all SQL migration files in order."""
    sql_files = [
        "01_create_schema.sql",
        "02_spatial_joins.sql",
        "03_derived_metrics.sql",
    ]

    for i, sql_file in enumerate(sql_files):
        pipeline_status["phase"] = f"SQL: {sql_file}"
        pipeline_status["progress"] = int((i / len(sql_files)) * 100)
        sql_path = sql_dir / sql_file
        if not sql_path.exists():
            logger.error(f"SQL file not found: {sql_path}")
            return False

        if not run_sql_file(sql_path, db_url):
            logger.error(f"Failed at {sql_file}, stopping pipeline")
            return False

    return True


def run_pipeline_background(request: PipelineRequest):
    """Run the full pipeline in background."""
    global pipeline_status

    pipeline_status = {
        "running": True,
        "phase": "Starting",
        "progress": 0,
        "message": "Pipeline started",
        "success": None,
    }

    try:
        from settings import DATABASE_URL, SQL_DIR
        from insurance_platform.load_data import run_full_pipeline
        from insurance_platform.export_kepler import run_exports

        psql_url = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")

        # Check database
        pipeline_status["phase"] = "Checking database"
        pipeline_status["progress"] = 5
        if not check_database_connection(psql_url):
            raise Exception("Database connection failed")

        # Phase 1: Data Loading
        if not (request.skip_load or request.only_sql or request.only_export):
            pipeline_status["phase"] = "Phase 1: Data Loading"
            pipeline_status["progress"] = 10
            logger.info(">>> PHASE 1: Data Loading")
            run_full_pipeline()
            logger.info("Data loading completed successfully")

        if request.only_load:
            pipeline_status["success"] = True
            pipeline_status["message"] = "Only-load mode completed"
            pipeline_status["running"] = False
            pipeline_status["progress"] = 100
            return

        # Phase 2: SQL Pipeline
        if not (request.skip_sql or request.only_load or request.only_export):
            pipeline_status["phase"] = "Phase 2: Spatial Joins & Derived Metrics"
            pipeline_status["progress"] = 50
            logger.info(">>> PHASE 2: Spatial Joins & Derived Metrics")
            if not run_sql_pipeline(psql_url, SQL_DIR):
                raise Exception("SQL pipeline failed")

        if request.only_sql:
            pipeline_status["success"] = True
            pipeline_status["message"] = "Only-SQL mode completed"
            pipeline_status["running"] = False
            pipeline_status["progress"] = 100
            return

        # Phase 3: Export
        if not (request.skip_export or request.only_load or request.only_sql):
            pipeline_status["phase"] = "Phase 3: Kepler.gl Export"
            pipeline_status["progress"] = 90
            logger.info(">>> PHASE 3: Kepler.gl Export")
            run_exports()
            logger.info("Export completed successfully")

        if request.only_export:
            pipeline_status["success"] = True
            pipeline_status["message"] = "Only-export mode completed"
            pipeline_status["running"] = False
            pipeline_status["progress"] = 100
            return

        # Success
        pipeline_status["success"] = True
        pipeline_status["message"] = "PIPELINE COMPLETED SUCCESSFULLY!"
        pipeline_status["progress"] = 100

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        pipeline_status["success"] = False
        pipeline_status["message"] = f"Pipeline failed: {str(e)}"
    finally:
        pipeline_status["running"] = False


# --- API Endpoints ---
@app.get("/", summary="Root endpoint", response_class=FileResponse)
async def get_root():
    """Serve the main index.html"""
    logger.info("--- root endpoint called ---")
    return FileResponse(f"{static_folder}/index.html")


@app.get("/health", summary="Health check")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "insurance-intelligence"}


@app.get("/api/status", summary="Get pipeline status")
async def get_status():
    """Get current pipeline execution status"""
    return pipeline_status


@app.post("/api/pipeline/run", response_model=PipelineResponse, summary="Run pipeline")
async def run_pipeline(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Start the pipeline execution in background"""
    if pipeline_status["running"]:
        raise HTTPException(status_code=409, detail="Pipeline already running")

    background_tasks.add_task(run_pipeline_background, request)

    return PipelineResponse(
        success=True,
        message="Pipeline started in background",
        status=pipeline_status,
    )


@app.post("/api/pipeline/load", summary="Run data loading only")
async def run_load_only(background_tasks: BackgroundTasks):
    """Run only the data loading phase"""
    request = PipelineRequest(only_load=True)
    background_tasks.add_task(run_pipeline_background, request)
    return {"message": "Data loading started", "status": pipeline_status}


@app.post("/api/pipeline/sql", summary="Run SQL pipeline only")
async def run_sql_only(background_tasks: BackgroundTasks):
    """Run only the SQL pipeline phase"""
    request = PipelineRequest(only_sql=True)
    background_tasks.add_task(run_pipeline_background, request)
    return {"message": "SQL pipeline started", "status": pipeline_status}


@app.post("/api/pipeline/export", summary="Run export only")
async def run_export_only(background_tasks: BackgroundTasks):
    """Run only the export phase"""
    request = PipelineRequest(only_export=True)
    background_tasks.add_task(run_pipeline_background, request)
    return {"message": "Export started", "status": pipeline_status}


@app.get("/api/metrics/summary", summary="Get metrics summary")
async def get_metrics_summary():
    """Get summary statistics from the opportunity metrics"""
    try:
        from settings import DATABASE_URL, ENGINE_OPTIONS
        from sqlalchemy import create_engine, text

        engine = create_engine(DATABASE_URL, **ENGINE_OPTIONS)
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT
                    COUNT(*) as total_zips,
                    ROUND(AVG(overall_opportunity_score)::numeric, 3) as avg_opportunity,
                    ROUND(AVG(standard_market_score)::numeric, 3) as avg_standard,
                    ROUND(AVG(non_standard_market_score)::numeric, 3) as avg_nonstandard,
                    COUNT(*) FILTER (WHERE market_segment = 'Prime_Standard') as prime_standard,
                    COUNT(*) FILTER (WHERE market_segment = 'Strong_Standard') as strong_standard,
                    COUNT(*) FILTER (WHERE market_segment = 'Prime_NonStandard') as prime_nonstandard,
                    COUNT(*) FILTER (WHERE market_segment = 'Strong_NonStandard') as strong_nonstandard,
                    COUNT(*) FILTER (WHERE market_segment = 'Market_Gap_Opportunity') as market_gap,
                    COUNT(*) FILTER (WHERE market_segment = 'Spanish_Standard') as spanish_standard,
                    COUNT(*) FILTER (WHERE market_segment = 'Spanish_NonStandard') as spanish_nonstandard,
                    COUNT(*) FILTER (WHERE market_segment = 'Moderate') as moderate
                FROM zip_opportunity_metrics
                WHERE area_sqkm > 0
            """
                )
            )
            row = result.fetchone()
            return {
                "total_zips": row[0],
                "avg_opportunity_score": row[1],
                "avg_standard_score": row[2],
                "avg_nonstandard_score": row[3],
                "segments": {
                    "Prime_Standard": row[4],
                    "Strong_Standard": row[5],
                    "Prime_NonStandard": row[6],
                    "Strong_NonStandard": row[7],
                    "Market_Gap_Opportunity": row[8],
                    "Spanish_Standard": row[9],
                    "Spanish_NonStandard": row[10],
                    "Moderate": row[11],
                },
            }
    except Exception as e:
        logger.error(f"Failed to get metrics summary: {e}")
        return {
            "error": str(e),
            "message": "Ensure pipeline has been run and database is accessible",
        }


@app.get("/api/data-quality", summary="Get data quality status")
async def get_data_quality():
    """Check if real or mock demographic data is being used"""
    try:
        from settings import DATABASE_URL, ENGINE_OPTIONS
        from sqlalchemy import create_engine, text

        engine = create_engine(DATABASE_URL, **ENGINE_OPTIONS)
        with engine.connect() as conn:
            # Check census_demographics data source
            result = conn.execute(
                text(
                    """
                SELECT
                    data_source,
                    COUNT(*) as count
                FROM census_demographics
                GROUP BY data_source
            """
                )
            )
            demographics_sources = {row[0]: row[1] for row in result}

            # Check data_quality table for latest record
            result = conn.execute(
                text(
                    """
                SELECT table_name, data_source, record_count, created_at, notes
                FROM data_quality
                WHERE table_name = 'census_demographics'
                ORDER BY created_at DESC
                LIMIT 1
            """
                )
            )
            quality_row = result.fetchone()

            is_mock = demographics_sources.get("placeholder", 0) > 0
            primary_source = (
                max(demographics_sources, key=demographics_sources.get)
                if demographics_sources
                else "unknown"
            )

            return {
                "is_mock_data": is_mock,
                "primary_data_source": primary_source,
                "demographics_breakdown": demographics_sources,
                "quality_record": (
                    {
                        "table_name": quality_row[0] if quality_row else None,
                        "data_source": quality_row[1] if quality_row else None,
                        "record_count": quality_row[2] if quality_row else None,
                        "created_at": (
                            quality_row[3].isoformat()
                            if quality_row and quality_row[3]
                            else None
                        ),
                        "notes": quality_row[4] if quality_row else None,
                    }
                    if quality_row
                    else None
                ),
                "message": (
                    "Using mock demographic data - Census API unavailable. Configure CENSUS_API_KEY for real data."
                    if is_mock
                    else "Using real Census ACS data"
                ),
            }
    except Exception as e:
        logger.error(f"Failed to get data quality: {e}")
        return {
            "error": str(e),
            "is_mock_data": True,
            "message": "Unable to determine data source",
        }


# --- Mount static files (must be last) ---
frontend_path: str = os.path.abspath(
    os.path.join(os.path.dirname(__file__), static_folder)
)
app.mount("/", StaticFiles(directory=frontend_path, html=True), name=static_folder)


# --- Main entry point ---
if __name__ == "__main__":
    import uvicorn

    # Check for SSL certificates generated by mkcert
    cert_file = os.path.join(os.path.dirname(__file__), "certs", "cert.pem")
    key_file = os.path.join(os.path.dirname(__file__), "certs", "key.pem")

    host = config["API"].get("host", "0.0.0.0")
    port = config["API"].get("port", 8080)

    if os.path.exists(cert_file) and os.path.exists(key_file):
        logger.info(
            "Starting server with HTTPS using certificates in certs/ directory."
        )
        uvicorn.run(
            app, host=host, port=port, ssl_keyfile=key_file, ssl_certfile=cert_file
        )
    else:
        logger.info("Starting server with HTTP (no certificates found).")
        uvicorn.run(app, host=host, port=port)
