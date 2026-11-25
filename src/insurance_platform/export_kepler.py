"""Export utilities for Kepler.gl visualization."""

import json
import logging
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text

from settings import get_logger
from insurance_platform.config import (
    DATABASE_URL,
    ENGINE_OPTIONS,
    EXPORT_DIR,
    TABLE_FINAL,
    TARGET_CRS,
)

logger = get_logger(__name__)


def get_engine():
    return create_engine(DATABASE_URL, **ENGINE_OPTIONS)


def export_geojson(output_path: Optional[Path] = None) -> Path:
    """
    Export zip_opportunity_metrics as GeoJSON for Kepler.gl.
    """
    if output_path is None:
        output_path = EXPORT_DIR / "zip_opportunity_metrics.geojson"

    logger.info(f"Exporting to GeoJSON: {output_path}")

    engine = get_engine()

    # Query with geometry as WKT for GeoPandas
    query = f"""
    SELECT
        zip_code,
        ST_AsText(geometry) as wkt_geometry,
        total_crashes,
        crashes_per_sqkm,
        total_competitors,
        franchise_competitors,
        independent_competitors,
        competitors_per_sqkm,
        franchise_ratio,
        avg_aadt,
        max_aadt,
        total_road_km,
        road_density_km_per_sqkm,
        major_highway_count,
        median_home_value,
        median_household_income,
        median_gross_rent,
        vehicles_per_household,
        renter_pct,
        spanish_speaking_pct,
        hispanic_pct,
        total_housing_units,
        occupied_housing_units,
        owner_occupied,
        renter_occupied,
        car_commute_pct,
        transit_commute_pct,
        wfh_pct,
        avg_commute_time,
        uninsured_pct,
        area_sqkm,
        centroid_lat,
        centroid_lon,
        vulnerability_index,
        visibility_multiplier,
        risk_alignment,
        standard_market_score,
        non_standard_market_score,
        spanish_market_flag,
        spanish_market_score,
        market_segment,
        overall_opportunity_score,
        profitability_index
    FROM {TABLE_FINAL}
    WHERE area_sqkm > 0
    ORDER BY overall_opportunity_score DESC
    """

    df = pd.read_sql(query, engine)

    # Convert WKT to geometry
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.GeoSeries.from_wkt(df["wkt_geometry"], crs=TARGET_CRS),
        crs=TARGET_CRS,
    )
    gdf = gdf.drop(columns=["wkt_geometry"])

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write GeoJSON
    gdf.to_file(output_path, driver="GeoJSON")

    logger.info(f"Exported {len(gdf)} features to {output_path}")
    return output_path


def export_csv(output_path: Optional[Path] = None) -> Path:
    """
    Export zip_opportunity_metrics as CSV with WKT geometry for Kepler.gl.
    Kepler.gl can read CSV with WKT geometry column.
    """
    if output_path is None:
        output_path = EXPORT_DIR / "zip_opportunity_metrics.csv"

    logger.info(f"Exporting to CSV: {output_path}")

    engine = get_engine()

    query = f"""
    SELECT
        zip_code,
        ST_AsText(geometry) as geometry_wkt,
        total_crashes,
        crashes_per_sqkm,
        total_competitors,
        franchise_competitors,
        independent_competitors,
        competitors_per_sqkm,
        franchise_ratio,
        avg_aadt,
        max_aadt,
        total_road_km,
        road_density_km_per_sqkm,
        major_highway_count,
        median_home_value,
        median_household_income,
        median_gross_rent,
        vehicles_per_household,
        renter_pct,
        spanish_speaking_pct,
        hispanic_pct,
        total_housing_units,
        occupied_housing_units,
        owner_occupied,
        renter_occupied,
        car_commute_pct,
        transit_commute_pct,
        wfh_pct,
        avg_commute_time,
        uninsured_pct,
        area_sqkm,
        centroid_lat,
        centroid_lon,
        vulnerability_index,
        visibility_multiplier,
        risk_alignment,
        standard_market_score,
        non_standard_market_score,
        spanish_market_flag,
        spanish_market_score,
        market_segment,
        overall_opportunity_score,
        profitability_index
    FROM {TABLE_FINAL}
    WHERE area_sqkm > 0
    ORDER BY overall_opportunity_score DESC
    """

    df = pd.read_sql(query, engine)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    logger.info(f"Exported {len(df)} rows to {output_path}")
    return output_path


def export_kepler_config(output_path: Optional[Path] = None) -> Path:
    """
    Generate a Kepler.gl configuration JSON for quick visualization setup.
    """
    if output_path is None:
        output_path = EXPORT_DIR / "kepler_config.json"

    config = {
        "version": "v1",
        "config": {
            "visState": {
                "filters": [
                    {
                        "id": "market_segment_filter",
                        "type": "multiSelect",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Market Segment",
                        "column": "market_segment",
                        "domain": [],
                        "enlarged": False,
                    },
                    {
                        "id": "opportunity_score_filter",
                        "type": "range",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Overall Opportunity Score",
                        "column": "overall_opportunity_score",
                        "domain": [0, 1],
                    },
                    {
                        "id": "standard_score_filter",
                        "type": "range",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Standard Market Score",
                        "column": "standard_market_score",
                        "domain": [0, 1],
                    },
                    {
                        "id": "nonstandard_score_filter",
                        "type": "range",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Non-Standard Market Score",
                        "column": "non_standard_market_score",
                        "domain": [0, 1],
                    },
                    {
                        "id": "spanish_market_filter",
                        "type": "range",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Spanish Market Score",
                        "column": "spanish_market_score",
                        "domain": [0, 1],
                    },
                    {
                        "id": "profitability_filter",
                        "type": "range",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Profitability Index",
                        "column": "profitability_index",
                        "domain": [0, 1],
                    },
                    {
                        "id": "spanish_speaking_filter",
                        "type": "range",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Spanish Speaking %",
                        "column": "spanish_speaking_pct",
                        "domain": [0, 100],
                    },
                    {
                        "id": "hispanic_filter",
                        "type": "range",
                        "dataId": "zip_opportunity_metrics",
                        "name": "Hispanic Population %",
                        "column": "hispanic_pct",
                        "domain": [0, 100],
                    },
                ],
                "layers": [
                    {
                        "id": "zip_choropleth",
                        "type": "geojson",
                        "config": {
                            "dataId": "zip_opportunity_metrics",
                            "label": "ZIP Opportunity Metrics",
                            "color": [
                                "overall_opportunity_score",
                                {
                                    "type": "quantile",
                                    "colors": [
                                        "#fee5d9",
                                        "#fcae91",
                                        "#fb6a4a",
                                        "#de2d26",
                                        "#a50f15",
                                    ],
                                    "size": 5,
                                },
                            ],
                            "columns": {"geojson": "geometry"},
                            "isVisible": True,
                            "visConfig": {
                                "opacity": 0.8,
                                "thickness": 0.5,
                                "strokeColor": [100, 100, 100],
                                "colorRange": {
                                    "name": "Global Warming",
                                    "type": "sequential",
                                    "category": "Uber",
                                    "colors": [
                                        "#5A1846",
                                        "#900C3F",
                                        "#C70039",
                                        "#E3611C",
                                        "#F1920E",
                                        "#FFC300",
                                    ],
                                },
                                "strokeColorRange": {
                                    "name": "Global Warming",
                                    "type": "sequential",
                                    "category": "Uber",
                                    "colors": [
                                        "#5A1846",
                                        "#900C3F",
                                        "#C70039",
                                        "#E3611C",
                                        "#F1920E",
                                        "#FFC300",
                                    ],
                                },
                                "radius": 10,
                                "sizeRange": [0, 10],
                                "radiusRange": [0, 50],
                                "heightRange": [0, 500000],
                                "elevationScale": 5,
                                "stroked": True,
                                "filled": True,
                                "enable3d": True,
                                "wireframe": False,
                            },
                            "hidden": False,
                            "textLabel": [
                                {
                                    "field": "zip_code",
                                    "color": [255, 255, 255],
                                    "size": 12,
                                    "offset": [0, 0],
                                    "anchor": "start",
                                    "alignment": "center",
                                    "background": True,
                                    "backgroundColor": [0, 0, 0, 128],
                                }
                            ],
                        },
                        "visualChannels": {
                            "colorField": {
                                "name": "overall_opportunity_score",
                                "type": "real",
                            },
                            "colorScale": "quantile",
                        },
                    },
                    {
                        "id": "competitors_point",
                        "type": "point",
                        "config": {
                            "dataId": "competitors",
                            "label": "Competitor Locations",
                            "color": [255, 0, 0],
                            "columns": {
                                "lat": "latitude",
                                "lng": "longitude",
                                "altitude": None,
                            },
                            "isVisible": True,
                            "visConfig": {
                                "radius": 50,
                                "fixedRadius": False,
                                "opacity": 0.8,
                                "outline": False,
                                "thickness": 1,
                                "strokeColor": None,
                                "colorRange": {
                                    "name": "Global Warming",
                                    "type": "sequential",
                                    "category": "Uber",
                                },
                                "sizeRange": [0, 10],
                                "radiusRange": [0, 50],
                                "heightRange": [0, 500000],
                                "elevationScale": 5,
                                "stroked": False,
                                "filled": True,
                                "enable3d": False,
                            },
                            "hidden": False,
                            "textLabel": [
                                {
                                    "field": "name",
                                    "color": [0, 0, 0],
                                    "size": 10,
                                    "offset": [0, 0],
                                    "anchor": "start",
                                    "alignment": "center",
                                    "background": False,
                                }
                            ],
                        },
                        "visualChannels": {
                            "colorField": {"name": "agency_type", "type": "string"},
                            "colorScale": "ordinal",
                        },
                    },
                    {
                        "id": "crashes_heatmap",
                        "type": "heatmap",
                        "config": {
                            "dataId": "crashes",
                            "label": "Crash Density Heatmap",
                            "color": [
                                "crash_id",
                                {
                                    "type": "quantile",
                                    "colors": [
                                        "#fee5d9",
                                        "#fcae91",
                                        "#fb6a4a",
                                        "#de2d26",
                                        "#a50f15",
                                    ],
                                    "size": 5,
                                },
                            ],
                            "columns": {
                                "lat": "latitude",
                                "lng": "longitude",
                                "altitude": None,
                            },
                            "isVisible": True,
                            "visConfig": {
                                "opacity": 0.8,
                                "radiusPixels": 20,
                                "intensity": 1,
                                "threshold": 0.05,
                                "colorRange": {
                                    "name": "Global Warming",
                                    "type": "sequential",
                                    "category": "Uber",
                                },
                                "sizeRange": [0, 10],
                                "radiusRange": [0, 50],
                                "heightRange": [0, 500000],
                                "elevationScale": 5,
                            },
                            "hidden": True,
                            "textLabel": [],
                        },
                        "visualChannels": {
                            "colorField": {"name": "crash_id", "type": "real"},
                            "colorScale": "quantile",
                        },
                    },
                ],
                "interactionConfig": {
                    "tooltip": {
                        "fieldsToShow": {
                            "zip_opportunity_metrics": [
                                {"name": "zip_code", "format": None},
                                {"name": "market_segment", "format": None},
                                {"name": "overall_opportunity_score", "format": ".3f"},
                                {"name": "profitability_index", "format": ".3f"},
                                {"name": "standard_market_score", "format": ".3f"},
                                {"name": "non_standard_market_score", "format": ".3f"},
                                {"name": "spanish_market_score", "format": ".3f"},
                                {"name": "vulnerability_index", "format": ".3f"},
                                {"name": "visibility_multiplier", "format": ".3f"},
                                {"name": "risk_alignment", "format": ".3f"},
                                {"name": "median_home_value", "format": "$,.0f"},
                                {"name": "median_household_income", "format": "$,.0f"},
                                {"name": "median_gross_rent", "format": "$,.0f"},
                                {"name": "vehicles_per_household", "format": ".2f"},
                                {"name": "renter_pct", "format": ".1f"},
                                {"name": "spanish_speaking_pct", "format": ".1f"},
                                {"name": "hispanic_pct", "format": ".1f"},
                                {"name": "car_commute_pct", "format": ".1f"},
                                {"name": "transit_commute_pct", "format": ".1f"},
                                {"name": "wfh_pct", "format": ".1f"},
                                {"name": "avg_commute_time", "format": ".1f"},
                                {"name": "uninsured_pct", "format": ".1f"},
                                {"name": "total_competitors", "format": None},
                                {"name": "franchise_competitors", "format": None},
                                {"name": "independent_competitors", "format": None},
                                {"name": "avg_aadt", "format": ",.0f"},
                                {"name": "max_aadt", "format": ",.0f"},
                                {"name": "total_crashes", "format": None},
                            ],
                            "competitors": [
                                {"name": "name", "format": None},
                                {"name": "agency_type", "format": None},
                                {"name": "appointment_type", "format": None},
                                {"name": "city", "format": None},
                                {"name": "postal_code", "format": None},
                            ],
                            "crashes": [{"name": "crash_id", "format": None}],
                        },
                        "compareMode": False,
                        "compareType": "absolute",
                        "enabled": True,
                    },
                    "brush": {"size": 0.5, "enabled": True},
                    "geocoder": {"enabled": True},
                    "coordinate": {"enabled": True},
                },
                "layerBlending": "normal",
                "splitMaps": [],
                "animationConfig": {"currentTime": None, "speed": 1},
            },
            "mapState": {
                "bearing": 0,
                "dragRotate": False,
                "latitude": 31.0,
                "longitude": -99.0,
                "pitch": 45,
                "zoom": 5.5,
                "isSplit": False,
            },
            "mapStyle": {
                "styleType": "dark",
                "topLayerGroups": {},
                "visibleLayerGroups": {
                    "label": True,
                    "road": True,
                    "border": False,
                    "building": True,
                    "water": True,
                    "land": True,
                    "3d building": False,
                },
                "threeDBuildingColor": [
                    9.665468314072013,
                    17.18305478057247,
                    31.1442867897876,
                ],
                "mapStyles": {},
            },
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    logger.info(f"Kepler.gl config saved to {output_path}")
    return output_path


def run_exports():
    """Run all exports."""
    logger.info("Starting exports for Kepler.gl...")

    export_geojson()
    export_csv()
    export_kepler_config()

    logger.info("All exports completed!")


if __name__ == "__main__":
    run_exports()
