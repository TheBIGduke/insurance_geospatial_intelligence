-- Insurance Geospatial Intelligence Platform
-- Derived Metrics and Scoring Calculations
-- Adds strategic scoring columns to zip_opportunity_metrics

-- ============================================================================
-- ADD DERIVED METRIC COLUMNS
-- ============================================================================

ALTER TABLE zip_opportunity_metrics
ADD COLUMN IF NOT EXISTS vulnerability_index NUMERIC,
ADD COLUMN IF NOT EXISTS visibility_multiplier NUMERIC,
ADD COLUMN IF NOT EXISTS risk_alignment NUMERIC,
ADD COLUMN IF NOT EXISTS standard_market_score NUMERIC,
ADD COLUMN IF NOT EXISTS non_standard_market_score NUMERIC,
ADD COLUMN IF NOT EXISTS spanish_market_flag BOOLEAN,
ADD COLUMN IF NOT EXISTS overall_opportunity_score NUMERIC,
ADD COLUMN IF NOT EXISTS market_segment VARCHAR(50);

-- ============================================================================
-- NORMALIZATION HELPER FUNCTION
-- ============================================================================
-- Min-max normalization to 0-1 scale
CREATE OR REPLACE FUNCTION normalize_metric(
    value NUMERIC,
    min_val NUMERIC,
    max_val NUMERIC
) RETURNS NUMERIC AS $$
BEGIN
    IF max_val = min_val THEN
        RETURN 0.5;
    END IF;
    RETURN GREATEST(0, LEAST(1, (value - min_val) / (max_val - min_val)));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- CALCULATE PERCENTILES FOR NORMALIZATION
-- ============================================================================
WITH percentiles AS (
    SELECT
        -- Crash metrics
        percentile_cont(0.05) WITHIN GROUP (ORDER BY crashes_per_sqkm)::numeric AS crash_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY crashes_per_sqkm)::numeric AS crash_p95,
        -- Competitor density
        percentile_cont(0.05) WITHIN GROUP (ORDER BY competitors_per_sqkm)::numeric AS comp_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY competitors_per_sqkm)::numeric AS comp_p95,
        -- Traffic
        percentile_cont(0.05) WITHIN GROUP (ORDER BY avg_aadt)::numeric AS aadt_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_aadt)::numeric AS aadt_p95,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY max_aadt)::numeric AS max_aadt_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY max_aadt)::numeric AS max_aadt_p95,
        -- Demographics
        percentile_cont(0.05) WITHIN GROUP (ORDER BY median_home_value)::numeric AS home_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY median_home_value)::numeric AS home_p95,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY median_household_income)::numeric AS income_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY median_household_income)::numeric AS income_p95,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY vehicles_per_household)::numeric AS veh_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY vehicles_per_household)::numeric AS veh_p95,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY renter_pct)::numeric AS renter_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY renter_pct)::numeric AS renter_p95,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY spanish_speaking_pct)::numeric AS spanish_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY spanish_speaking_pct)::numeric AS spanish_p95,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY franchise_competitors)::numeric AS fran_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY franchise_competitors)::numeric AS fran_p95,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY independent_competitors)::numeric AS indep_p05,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY independent_competitors)::numeric AS indep_p95
    FROM zip_opportunity_metrics
    WHERE area_sqkm > 0
)
UPDATE zip_opportunity_metrics zom
SET
    -- ============================================================
    -- VULNERABILITY INDEX
    -- High score = Few competitors (market gap), low review scores, high traffic
    -- Components: Low competitor density (good), Low franchise ratio (good), High traffic (good)
    -- ============================================================
    vulnerability_index = (
        -- Low competitor density = high vulnerability (market gap)
        (1 - normalize_metric(zom.competitors_per_sqkm::numeric, p.comp_p05, p.comp_p95)) * 0.40 +
        -- Low franchise ratio = more independent = easier to compete
        (1 - normalize_metric(zom.franchise_ratio::numeric, 0, 1)) * 0.20 +
        -- High traffic visibility = good for new office
        normalize_metric(zom.avg_aadt::numeric, p.aadt_p05, p.aadt_p95) * 0.25 +
        -- High major highway presence
        normalize_metric(zom.major_highway_count::numeric, 0, 5) * 0.15
    ),

    -- ============================================================
    -- VISIBILITY MULTIPLIER
    -- High score = High traffic exposure, good commuter corridors
    -- ============================================================
    visibility_multiplier = (
        normalize_metric(zom.avg_aadt::numeric, p.aadt_p05, p.aadt_p95) * 0.40 +
        normalize_metric(zom.max_aadt::numeric, p.max_aadt_p05, p.max_aadt_p95) * 0.30 +
        normalize_metric(zom.road_density_km_per_sqkm::numeric, 0, 10) * 0.20 +
        normalize_metric(zom.major_highway_count::numeric, 0, 5) * 0.10
    ),

    -- ============================================================
    -- RISK ALIGNMENT
    -- High score = Lower risk (fewer crashes, less severe)
    -- ============================================================
    risk_alignment = (
        -- Low crash density = good
        (1 - normalize_metric(zom.crashes_per_sqkm::numeric, p.crash_p05, p.crash_p95)) * 0.50 +
        -- Proxy for severity: areas with very high crash counts per road km
        -- Using total_crashes / total_road_km as severity proxy
        (1 - normalize_metric(
            CASE WHEN zom.total_road_km > 0 THEN (zom.total_crashes / zom.total_road_km)::numeric ELSE 0 END,
            0, 10
        )) * 0.30 +
        -- Hail/theft proxy: using renter density as urban risk proxy (inverse)
        (1 - normalize_metric(zom.renter_pct::numeric, p.renter_p05, p.renter_p95)) * 0.20
    ),

    -- ============================================================
    -- STANDARD MARKET SCORE (Premium/Standard Auto + Home bundles)
    -- High income, high home value, high vehicles, franchise dealers nearby
    -- ============================================================
    standard_market_score = (
        normalize_metric(zom.median_home_value::numeric, p.home_p05, p.home_p95) * 0.30 +
        normalize_metric(zom.median_household_income::numeric, p.income_p05, p.income_p95) * 0.20 +
        normalize_metric(zom.vehicles_per_household::numeric, p.veh_p05, p.veh_p95) * 0.25 +
        normalize_metric(zom.franchise_competitors::numeric, p.fran_p05, p.fran_p95) * 0.15 +
        (1 - normalize_metric(zom.renter_pct::numeric, p.renter_p05, p.renter_p95)) * 0.10
    ),

    -- ============================================================
    -- NON-STANDARD MARKET SCOE (SR-22, Liability-only, Non-standard)
    -- High renter %, lower income, independent dealers, Spanish-speaking
    -- ============================================================
    non_standard_market_score = (
        normalize_metric(zom.renter_pct::numeric, p.renter_p05, p.renter_p95) * 0.30 +
        (1 - normalize_metric(zom.median_household_income::numeric, p.income_p05, p.income_p95)) * 0.20 +
        normalize_metric(zom.independent_competitors::numeric, p.indep_p05, p.indep_p95) * 0.25 +
        normalize_metric(zom.crashes_per_sqkm::numeric, p.crash_p05, p.crash_p95) * 0.15 +
        normalize_metric(zom.spanish_speaking_pct::numeric, p.spanish_p05, p.spanish_p95) * 0.10
    ),

    -- ============================================================
    -- SPANISH MARKET FLAG
    -- ============================================================
    spanish_market_flag = (zom.spanish_speaking_pct > 30)

FROM percentiles p
WHERE zom.area_sqkm > 0;

-- ============================================================================
-- SECOND UPDATE: Calculate derived scores that depend on the above columns
-- (PostgreSQL evaluates all SET expressions against OLD values in a single UPDATE)
-- ============================================================================
WITH pctl AS (
    SELECT
        percentile_cont(0.75) WITHIN GROUP (ORDER BY median_home_value) AS home_p75
    FROM zip_opportunity_metrics
    WHERE area_sqkm > 0
)
UPDATE zip_opportunity_metrics zom
SET
    -- ============================================================
    -- MARKET SEGMENT CLASSIFICATION
    -- ============================================================
    market_segment = CASE
        WHEN zom.spanish_speaking_pct > 30 AND zom.renter_pct > 50 THEN 'Spanish_NonStandard'
        WHEN zom.spanish_speaking_pct > 30 AND zom.median_home_value > pctl.home_p75 THEN 'Spanish_Standard'
        WHEN zom.standard_market_score > 0.7 THEN 'Prime_Standard'
        WHEN zom.standard_market_score > 0.5 THEN 'Strong_Standard'
        WHEN zom.non_standard_market_score > 0.7 THEN 'Prime_NonStandard'
        WHEN zom.non_standard_market_score > 0.5 THEN 'Strong_NonStandard'
        WHEN zom.vulnerability_index > 0.7 THEN 'Market_Gap_Opportunity'
        ELSE 'Moderate'
    END,

    -- ============================================================
    -- OVERALL OPPORTUNITY SCORE
    -- Weighted combination for general ranking
    -- ============================================================
    overall_opportunity_score = (
        zom.vulnerability_index * 0.25 +
        zom.visibility_multiplier * 0.20 +
        zom.risk_alignment * 0.15 +
        GREATEST(zom.standard_market_score, zom.non_standard_market_score) * 0.40
    )
FROM pctl
WHERE zom.area_sqkm > 0;

-- ============================================================================
-- CREATE INDEXES ON SCORED COLUMNS
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_zip_opp_vulnerability ON zip_opportunity_metrics (vulnerability_index DESC);
CREATE INDEX IF NOT EXISTS idx_zip_opp_visibility ON zip_opportunity_metrics (visibility_multiplier DESC);
CREATE INDEX IF NOT EXISTS idx_zip_opp_risk ON zip_opportunity_metrics (risk_alignment DESC);
CREATE INDEX IF NOT EXISTS idx_zip_opp_standard ON zip_opportunity_metrics (standard_market_score DESC);
CREATE INDEX IF NOT EXISTS idx_zip_opp_nonstandard ON zip_opportunity_metrics (non_standard_market_score DESC);
CREATE INDEX IF NOT EXISTS idx_zip_opp_overall ON zip_opportunity_metrics (overall_opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_zip_opp_segment ON zip_opportunity_metrics (market_segment);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Score distribution
-- SELECT
--     market_segment,
--     COUNT(*) as count,
--     ROUND(AVG(overall_opportunity_score)::numeric, 3) as avg_opportunity,
--     ROUND(AVG(standard_market_score)::numeric, 3) as avg_standard,
--     ROUND(AVG(non_standard_market_score)::numeric, 3) as avg_nonstandard
-- FROM zip_opportunity_metrics
-- GROUP BY market_segment
-- ORDER BY avg_opportunity DESC;

-- Top 20 opportunities by segment
-- SELECT zip_code, market_segment, overall_opportunity_score,
--        standard_market_score, non_standard_market_score,
--        vulnerability_index, visibility_multiplier, risk_alignment,
--        median_home_value, median_household_income, renter_pct,
--        total_competitors, franchise_competitors, independent_competitors,
--        avg_aadt, max_aadt, total_crashes
-- FROM zip_opportunity_metrics
-- ORDER BY overall_opportunity_score DESC
-- LIMIT 20;
