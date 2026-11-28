-- Insurance Geospatial Intelligence Platform
-- Schema Creation and Indexes
-- Run after loading raw data tables

-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ============================================================================
-- TABLE: zip_code_boundaries (loaded from shapefile)
-- ============================================================================
-- Columns: zip_code (PK), geometry (MULTIPOLYGON, SRID=4326)
-- Indexes created during load

-- ============================================================================
-- TABLE: crashes (loaded from CSV)
-- ============================================================================
-- Columns: crash_id, latitude, longitude, geometry (POINT, SRID=4326)

-- ============================================================================
-- TABLE: census_demographics (loaded from Census API/CSV)
-- ============================================================================
-- Columns: zip_code (PK), median_home_value, median_household_income,
--          vehicles_per_household, renter_pct, spanish_speaking_pct, etc.

-- ============================================================================
-- TABLE: competitors (loaded from insurance agents CSV)
-- ============================================================================
-- Columns: npn, name, appointment_type, agency_type (Franchise/Independent),
--          city, state, postal_code,
--          geometry (POINT, SRID=4326)

-- ============================================================================
-- TABLE: roads (loaded from shapefile)
-- ============================================================================
-- Columns: gid, rte_nm, rte_nbr, rdbd_type, county, system,
--          geometry (LINESTRING, SRID=4326), aadt (nullable)

-- ============================================================================
-- Additional Indexes for Performance
-- ============================================================================

-- Spatial indexes (already created during load, but ensuring)
CREATE INDEX IF NOT EXISTS idx_zip_code_boundaries_geom ON zip_code_boundaries USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_crashes_geom ON crashes USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_competitors_geom ON competitors USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_roads_geom ON roads USING GIST (geometry);

-- Attribute indexes
CREATE INDEX IF NOT EXISTS idx_zip_code_boundaries_zip ON zip_code_boundaries (zip_code);
CREATE INDEX IF NOT EXISTS idx_census_demographics_zip ON census_demographics (zip_code);
CREATE INDEX IF NOT EXISTS idx_census_demographics_source ON census_demographics (data_source);
CREATE INDEX IF NOT EXISTS idx_competitors_postal ON competitors (postal_code);
CREATE INDEX IF NOT EXISTS idx_competitors_type ON competitors (agency_type);
CREATE INDEX IF NOT EXISTS idx_roads_county ON roads ("COUNTY");

-- ============================================================================
-- TABLE: data_quality (tracks pipeline data source and quality flags)
-- ============================================================================
CREATE TABLE IF NOT EXISTS data_quality (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    data_source VARCHAR(50) NOT NULL,  -- 'census_api', 'placeholder', etc.
    record_count INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_data_quality_table ON data_quality (table_name);
CREATE INDEX IF NOT EXISTS idx_data_quality_created ON data_quality (created_at);

-- Insert initial data quality record for census_demographics
INSERT INTO data_quality (table_name, data_source, record_count, notes)
SELECT
    'census_demographics' as table_name,
    COALESCE(data_source, 'unknown') as data_source,
    COUNT(*) as record_count,
    'Auto-recorded during pipeline run' as notes
FROM census_demographics
GROUP BY data_source
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Helper Function: Point in Polygon Check
-- ============================================================================
-- PostGIS ST_Intersects is used for spatial joins
-- ST_Contains is stricter (point must be inside, not on boundary)
-- For our use case, ST_Intersects is appropriate

-- ============================================================================
-- Validation Queries
-- ============================================================================

-- Check row counts
-- SELECT 'zip_code_boundaries' as table, COUNT(*) FROM zip_code_boundaries
-- UNION ALL SELECT 'crashes', COUNT(*) FROM crashes
-- UNION ALL SELECT 'census_demographics', COUNT(*) FROM census_demographics
-- UNION ALL SELECT 'competitors', COUNT(*) FROM competitors
-- UNION ALL SELECT 'roads', COUNT(*) FROM roads;

-- Check CRS
-- SELECT ST_SRID(geometry) FROM zip_code_boundaries LIMIT 1;
-- SELECT ST_SRID(geometry) FROM crashes LIMIT 1;
-- SELECT ST_SRID(geometry) FROM competitors LIMIT 1;
-- SELECT ST_SRID(geometry) FROM roads LIMIT 1;

-- Sample spatial join test
-- SELECT z.zip_code, COUNT(c.crash_id) as crash_count
-- FROM zip_code_boundaries z
-- JOIN crashes c ON ST_Intersects(z.geometry, c.geometry)
-- GROUP BY z.zip_code
-- ORDER BY crash_count DESC
-- LIMIT 10;
