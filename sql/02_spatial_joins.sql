-- Insurance Geospatial Intelligence Platform
-- Spatial Joins and Aggregation Queries
-- Creates the core zip_opportunity_metrics table/view

-- ============================================================================
-- CORE AGGREGATION: Crashes per ZIP
-- ============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS zip_crash_metrics AS
SELECT
    z.zip_code,
    COUNT(c.crash_id) AS total_crashes,
    -- Crash density per sq km
    COUNT(c.crash_id) / (ST_Area(z.geometry::geography) / 1000000.0) AS crashes_per_sqkm
FROM zip_code_boundaries z
LEFT JOIN crashes c
    ON ST_Intersects(z.geometry, c.geometry)
GROUP BY z.zip_code, z.geometry;

-- Index for faster joins
CREATE INDEX IF NOT EXISTS idx_zip_crash_metrics_zip ON zip_crash_metrics (zip_code);

-- ============================================================================
-- CORE AGGREGATION: Competitors (Insurance Agencies) per ZIP
-- ============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS zip_competitor_metrics AS
SELECT
    z.zip_code,
    COUNT(comp.npn) AS total_competitors,
    COUNT(comp.npn) FILTER (WHERE comp.agency_type = 'Franchise') AS franchise_competitors,
    COUNT(comp.npn) FILTER (WHERE comp.agency_type = 'Independent') AS independent_competitors,
    -- Competitor density per sq km
    COUNT(comp.npn) / (ST_Area(z.geometry::geography) / 1000000.0) AS competitors_per_sqkm,
    -- Franchise ratio
    CASE
        WHEN COUNT(comp.npn) > 0
        THEN COUNT(comp.npn) FILTER (WHERE comp.agency_type = 'Franchise')::float / COUNT(comp.npn)
        ELSE 0
    END AS franchise_ratio
FROM zip_code_boundaries z
LEFT JOIN competitors comp
    ON ST_Intersects(z.geometry, comp.geometry)
GROUP BY z.zip_code, z.geometry;

CREATE INDEX IF NOT EXISTS idx_zip_competitor_metrics_zip ON zip_competitor_metrics (zip_code);

-- ============================================================================
-- CORE AGGREGATION: Traffic/Road Metrics per ZIP
-- ============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS zip_road_metrics AS
SELECT
    z.zip_code,
    -- Average AADT (where available) - cast text to numeric
    AVG(r.aadt::numeric) AS avg_aadt,
    -- Max AADT in ZIP
    MAX(r.aadt::numeric) AS max_aadt,
    -- Total road length in km
    SUM(ST_Length(r.geometry::geography)) / 1000.0 AS total_road_km,
    -- Road density (km per sq km)
    SUM(ST_Length(r.geometry::geography)) / 1000.0 / (ST_Area(z.geometry::geography) / 1000000.0) AS road_density_km_per_sqkm,
    -- Major highway presence (interstate/US highway)
    COUNT(r."GID") FILTER (WHERE r."RTE_NM" ILIKE 'I-%' OR r."RTE_NM" ILIKE 'US-%') AS major_highway_count
FROM zip_code_boundaries z
LEFT JOIN roads r
    ON ST_Intersects(z.geometry, r.geometry)
GROUP BY z.zip_code, z.geometry;

CREATE INDEX IF NOT EXISTS idx_zip_road_metrics_zip ON zip_road_metrics (zip_code);

-- ============================================================================
-- DEMOGRAPHICS: Already at ZIP level, just ensure clean join
-- Includes real ACS data + derived metrics
-- ============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS zip_demographics AS
SELECT
    d.zip_code,
    d.median_home_value,
    d.median_household_income,
    d.median_gross_rent,
    d.vehicles_per_household,
    d.renter_pct,
    d.spanish_speaking_pct,
    d.hispanic_pct,
    d.total_housing_units,
    d.occupied_housing_units,
    d.owner_occupied,
    d.renter_occupied,
    d.car_commute_pct,
    d.transit_commute_pct,
    d.wfh_pct,
    d.avg_commute_time,
    d.uninsured_pct
FROM census_demographics d
WHERE d.zip_code IN (SELECT zip_code FROM zip_code_boundaries);

CREATE INDEX IF NOT EXISTS idx_zip_demographics_zip ON zip_demographics (zip_code);

-- ============================================================================
-- UNIFIED METRICS TABLE: zip_opportunity_metrics
-- ============================================================================
-- This is the main output table for Kepler.gl visualization

DROP TABLE IF EXISTS zip_opportunity_metrics CASCADE;

CREATE TABLE zip_opportunity_metrics AS
SELECT
    -- Primary key and geometry
    z.zip_code,
    z.geometry,

    -- Crash metrics
    COALESCE(cm.total_crashes, 0) AS total_crashes,
    COALESCE(cm.crashes_per_sqkm, 0) AS crashes_per_sqkm,

    -- Competitor metrics
    COALESCE(comp.total_competitors, 0) AS total_competitors,
    COALESCE(comp.franchise_competitors, 0) AS franchise_competitors,
    COALESCE(comp.independent_competitors, 0) AS independent_competitors,
    COALESCE(comp.competitors_per_sqkm, 0) AS competitors_per_sqkm,
    COALESCE(comp.franchise_ratio, 0) AS franchise_ratio,

    -- Road/Traffic metrics
    COALESCE(rm.avg_aadt, 0) AS avg_aadt,
    COALESCE(rm.max_aadt, 0) AS max_aadt,
    COALESCE(rm.total_road_km, 0) AS total_road_km,
    COALESCE(rm.road_density_km_per_sqkm, 0) AS road_density_km_per_sqkm,
    COALESCE(rm.major_highway_count, 0) AS major_highway_count,

    -- Demographics (real ACS data)
    COALESCE(d.median_home_value, 0) AS median_home_value,
    COALESCE(d.median_household_income, 0) AS median_household_income,
    COALESCE(d.median_gross_rent, 0) AS median_gross_rent,
    COALESCE(d.vehicles_per_household, 0) AS vehicles_per_household,
    COALESCE(d.renter_pct, 0) AS renter_pct,
    COALESCE(d.spanish_speaking_pct, 0) AS spanish_speaking_pct,
    COALESCE(d.hispanic_pct, 0) AS hispanic_pct,
    COALESCE(d.total_housing_units, 0) AS total_housing_units,
    COALESCE(d.occupied_housing_units, 0) AS occupied_housing_units,
    COALESCE(d.owner_occupied, 0) AS owner_occupied,
    COALESCE(d.renter_occupied, 0) AS renter_occupied,

    -- Commute patterns
    COALESCE(d.car_commute_pct, 0) AS car_commute_pct,
    COALESCE(d.transit_commute_pct, 0) AS transit_commute_pct,
    COALESCE(d.wfh_pct, 0) AS wfh_pct,
    COALESCE(d.avg_commute_time, 0) AS avg_commute_time,

    -- Insurance proxy
    COALESCE(d.uninsured_pct, 0) AS uninsured_pct,

    -- Area for reference
    ST_Area(z.geometry::geography) / 1000000.0 AS area_sqkm,

    -- Centroid for labeling
    ST_Y(ST_Centroid(z.geometry)) AS centroid_lat,
    ST_X(ST_Centroid(z.geometry)) AS centroid_lon

FROM zip_code_boundaries z
LEFT JOIN zip_crash_metrics cm ON z.zip_code = cm.zip_code
LEFT JOIN zip_competitor_metrics comp ON z.zip_code = comp.zip_code
LEFT JOIN zip_road_metrics rm ON z.zip_code = rm.zip_code
LEFT JOIN zip_demographics d ON z.zip_code = d.zip_code;

-- Primary key
ALTER TABLE zip_opportunity_metrics ADD PRIMARY KEY (zip_code);

-- Spatial index
CREATE INDEX idx_zip_opportunity_metrics_geom ON zip_opportunity_metrics USING GIST (geometry);

-- ============================================================================
-- REFRESH FUNCTION FOR MATERIALIZED VIEWS
-- ============================================================================
CREATE OR REPLACE FUNCTION refresh_zip_metrics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY zip_crash_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY zip_competitor_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY zip_road_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY zip_demographics;

    -- Rebuild final table
    DELETE FROM zip_opportunity_metrics;

    INSERT INTO zip_opportunity_metrics
    SELECT
        z.zip_code,
        z.geometry,
        COALESCE(cm.total_crashes, 0),
        COALESCE(cm.crashes_per_sqkm, 0),
        COALESCE(comp.total_competitors, 0),
        COALESCE(comp.franchise_competitors, 0),
        COALESCE(comp.independent_competitors, 0),
        COALESCE(comp.competitors_per_sqkm, 0),
        COALESCE(comp.franchise_ratio, 0),
        COALESCE(rm.avg_aadt, 0),
        COALESCE(rm.max_aadt, 0),
        COALESCE(rm.total_road_km, 0),
        COALESCE(rm.road_density_km_per_sqkm, 0),
        COALESCE(rm.major_highway_count, 0),
        COALESCE(d.median_home_value, 0),
        COALESCE(d.median_household_income, 0),
        COALESCE(d.median_gross_rent, 0),
        COALESCE(d.vehicles_per_household, 0),
        COALESCE(d.renter_pct, 0),
        COALESCE(d.spanish_speaking_pct, 0),
        COALESCE(d.hispanic_pct, 0),
        COALESCE(d.total_housing_units, 0),
        COALESCE(d.occupied_housing_units, 0),
        COALESCE(d.owner_occupied, 0),
        COALESCE(d.renter_occupied, 0),
        COALESCE(d.car_commute_pct, 0),
        COALESCE(d.transit_commute_pct, 0),
        COALESCE(d.wfh_pct, 0),
        COALESCE(d.avg_commute_time, 0),
        COALESCE(d.uninsured_pct, 0),
        ST_Area(z.geometry::geography) / 1000000.0,
        ST_Y(ST_Centroid(z.geometry)),
        ST_X(ST_Centroid(z.geometry))
    FROM zip_code_boundaries z
    LEFT JOIN zip_crash_metrics cm ON z.zip_code = cm.zip_code
    LEFT JOIN zip_competitor_metrics comp ON z.zip_code = comp.zip_code
    LEFT JOIN zip_road_metrics rm ON z.zip_code = rm.zip_code
    LEFT JOIN zip_demographics d ON z.zip_code = d.zip_code;
END;
$$ LANGUAGE plpgsql;
