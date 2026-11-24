// Insurance Geospatial Intelligence - MapLibre GL JS Application

// ============================================
// CONFIGURATION
// ============================================
const CONFIG = {
    GEOJSON_URL: 'zip_opportunity_metrics.geojson',
    MAP: {
        center: [-99.0, 31.0],
        zoom: 5.5,
        minZoom: 4.5,
        maxZoom: 14,
        pitch: 40,
        bearing: 0,
        // OpenStreetMap raster tiles - free, no API key, real map data
        style: {
            version: 8,
            sources: {
                'osm': {
                    type: 'raster',
                    tiles: [
                        'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                        'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                        'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'
                    ],
                    tileSize: 256,
                    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                    maxzoom: 19
                }
            },
            layers: [{
                id: 'osm-layer',
                type: 'raster',
                source: 'osm'
            }]
        }
    },
    // Opportunity score gradient - tuned to actual data distribution (min=0.34, max=0.69, avg=0.52)
    // Most ZIPs fall in 0.45-0.60 range, so we spread colors there for visual discrimination
    OPPORTUNITY_COLORS: [
        [0.34, '#1e3a5f'],  // Deep navy - actual minimum
        [0.40, '#2563eb'],  // Blue
        [0.45, '#3b82f6'],  // Light blue
        [0.50, '#16a34a'],  // Green - median
        [0.55, '#84cc16'],  // Lime
        [0.60, '#d97706'],  // Amber
        [0.65, '#db2777'],  // Pink
        [0.69, '#fef08a']   // Gold - actual maximum
    ],
    // Extrusion heights (meters)
    // min: 100m base height so all ZIPs visible at state zoom
    // max: 200km so highest-scoring ZIP (0.69) is clearly tallest
    // Using exponential interpolation (factor 1.5) for more pronounced height differences
    EXTRUSION: {
        min: 200,
        max: 200000,
        base: 0
    },
    // Scale bar thresholds (meters) - standard imperial breaks
    SCALE_THRESHOLDS: [
        { max: 160934, label: '100 mi', width: 100 },  // 100 miles
        { max: 80467, label: '50 mi', width: 100 },    // 50 miles
        { max: 40234, label: '25 mi', width: 100 },    // 25 miles
        { max: 16093, label: '10 mi', width: 100 },    // 10 miles
        { max: 0, label: '5 mi', width: 100 }          // 5 miles (default)
    ],
    // Segment definitions (matching backend)
    SEGMENTS: {
        'Prime_Standard': { label: 'Prime Standard', color: '#0088ff', desc: 'High opportunity, strong demographics, favorable competition' },
        'Strong_Standard': { label: 'Strong Standard', color: '#00d46a', desc: 'Good opportunity, solid demographics' },
        'Prime_NonStandard': { label: 'Prime Non-Standard', color: '#ff8c00', desc: 'High non-standard score, underserved' },
        'Strong_NonStandard': { label: 'Strong Non-Standard', color: '#b870ff', desc: 'Solid non-standard fundamentals' },
        'Spanish_Standard': { label: 'Spanish Standard', color: '#ff33aa', desc: 'High Spanish-speaking %, standard market' },
        'Spanish_NonStandard': { label: 'Spanish Non-Standard', color: '#ff6ec7', desc: 'High Spanish-speaking %, non-standard market' },
        'Market_Gap_Opportunity': { label: 'Market Gap', color: '#ff3344', desc: 'High demand, few competitors - greenfield' },
        'Moderate': { label: 'Moderate', color: '#6ea8ff', desc: 'Balanced metrics - monitor for shifts' }
    },
    // Formatting helpers
    FORMAT: {
        number: (n) => n !== undefined && n !== null ? n.toLocaleString() : 'N/A',
        percent: (n) => n !== undefined && n !== null ? (n * 100).toFixed(1) + '%' : 'N/A',
        score: (n) => n !== undefined && n !== null ? (n * 100).toFixed(1) + '%' : 'N/A',
        dollar: (n) => n !== undefined && n !== null ? '$' + n.toLocaleString() : 'N/A',
        decimal: (n, d = 2) => n !== undefined && n !== null ? n.toFixed(d) : 'N/A'
    },
    // Debounce delay for slider filters (ms)
    FILTER_DEBOUNCE_MS: 150,
    // Map keyboard navigation step sizes
    MAP_KEYBOARD: {
        panDegrees: 0.05,    // ~5.5km at mid-latitudes
        zoomStep: 0.5,
        pitchStep: 5,
        bearingStep: 15
    }
};

// ============================================
// STATE
// ============================================
let state = {
    geojsonData: null,
    map: null,
    filters: {
        segment: '',
        minOpp: 0,
        minStd: 0,
        minNonStd: 0
    },
    selectedZip: null,
    ui: {
        panelCollapsed: false,
        legendCollapsed: false
    },
    // Modal focus management
    modal: {
        previousActiveElement: null,
        focusTrapElements: []
    },
    // Filter debounce timers
    filterTimers: {}
};

// ============================================
// DOM ELEMENTS (cached)
// ============================================
const els = {};

// ============================================
// INITIALIZATION
// ============================================
function initApp() {
    cacheElements();
    initMap();
    bindEvents();
    initTooltips();
    initOnboarding();
    initWorkflowSteps();
    initQuickHint();
}

// Handle both deferred and non-deferred script loading
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    // DOM already ready (e.g., script without defer)
    initApp();
}

// Cache DOM elements
function cacheElements() {
    // Loading
    els.loadingOverlay = document.getElementById('loadingOverlay');

    // Map legend
    els.legendToggle = document.getElementById('legendToggle');
    els.legendGradient = document.getElementById('legendGradient');
    els.legendSegments = document.getElementById('legendSegments');

    // Scale bar
    els.scaleBarLine = document.getElementById('scaleBarLine');
    els.scaleBarLabel = document.getElementById('scaleBarLabel');

    // Panel
    els.panel = document.getElementById('sidePanel');
    els.panelToggle = document.getElementById('headerPanelToggle');
    els.panelContent = document.getElementById('panelContent');

    // Filters
    els.segmentFilter = document.getElementById('segmentFilter');
    els.oppScoreFilter = document.getElementById('oppScoreFilter');
    els.oppScoreValue = document.getElementById('oppScoreValue');
    els.stdScoreFilter = document.getElementById('stdScoreFilter');
    els.stdScoreValue = document.getElementById('stdScoreValue');
    els.nonStdScoreFilter = document.getElementById('nonStdScoreFilter');
    els.nonStdScoreValue = document.getElementById('nonStdScoreValue');
    els.vulnScoreFilter = document.getElementById('vulnScoreFilter');
    els.vulnScoreValue = document.getElementById('vulnScoreValue');
    els.visScoreFilter = document.getElementById('visScoreFilter');
    els.visScoreValue = document.getElementById('visScoreValue');
    els.riskScoreFilter = document.getElementById('riskScoreFilter');
    els.riskScoreValue = document.getElementById('riskScoreValue');
    els.activeFiltersCount = document.getElementById('activeFiltersCount');

    // Advanced filters collapsible
    els.advancedFilters = document.getElementById('advancedFilters');
    els.advancedContent = document.getElementById('advancedContent');
    els.advancedToggle = document.querySelector('#advancedFilters .collapsible-toggle');

    // Detail
    els.detailContent = document.getElementById('detailContent');
    els.copyBtn = document.getElementById('copyBtn');

    // Stats
    els.statTotalZips = document.getElementById('statTotalZips');
    els.statFilteredZips = document.getElementById('statFilteredZips');
    els.statAvgOpp = document.getElementById('statAvgOpp');

    // Buttons
    els.resetBtn = document.getElementById('resetBtn');
    els.helpBtn = document.getElementById('helpBtn');
    els.helpModal = document.getElementById('helpModal');
    els.helpClose = document.getElementById('helpClose');

    // Toast container
    els.toastContainer = document.getElementById('toastContainer');

    // Populate segment filter
    populateSegmentFilter();

    // Populate legend segments
    populateLegendSegments();
}

// Initialize MapLibre map
function initMap() {
    // Check WebGL2 support (MapLibre v4.x removed maplibregl.supported()/isSupported())
    const testCanvas = document.createElement('canvas');
    const gl = testCanvas.getContext('webgl2') || testCanvas.getContext('webgl');
    if (!gl) {
        showMapError('Your browser does not support MapLibre GL (requires WebGL). Please use a modern browser.');
        return;
    }

    try {
        state.map = new maplibregl.Map({
            container: 'map',
            style: CONFIG.MAP.style,
            center: CONFIG.MAP.center,
            zoom: CONFIG.MAP.zoom,
            pitch: CONFIG.MAP.pitch,
            bearing: CONFIG.MAP.bearing,
            minZoom: CONFIG.MAP.minZoom,
            maxZoom: CONFIG.MAP.maxZoom,
            antialias: true,
            preserveDrawingBuffer: true
        });

        // Disable touch-action on map canvas so MapLibre handles gestures
        const canvas = state.map.getCanvas();
        if (canvas) {
            canvas.style.touchAction = 'none';
        }

        // Handle window resize for dynamic layout changes
        window.addEventListener('resize', () => {
            if (state.map) {
                state.map.resize();
            }
            updateScaleBar();
        });

        // Watch for panel toggle to resize map
        const panel = document.getElementById('sidePanel');
        if (panel) {
            const observer = new MutationObserver(() => {
                if (state.map) {
                    state.map.resize();
                }
            });
            observer.observe(panel, { attributes: true, attributeFilter: ['class', 'style'] });
        }

        // Also observe panel width changes via ResizeObserver
        if (panel && window.ResizeObserver) {
            const resizeObserver = new ResizeObserver(() => {
                if (state.map) {
                    state.map.resize();
                }
                updateScaleBar();
            });
            resizeObserver.observe(panel);
        }

        state.map.on('load', () => {
            // Add scale control
            state.map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-right');

            // Load data
            loadGeoJSON();

            // Update scale bar on move
            state.map.on('moveend', updateScaleBar);
            updateScaleBar();
        });

        // Click handling
        state.map.on('click', 'zip-layer', (e) => {
            if (e.features.length > 0) {
                showZipInfo(e.features[0].properties);
                state.selectedZip = e.features[0].properties.zip_code;
            }
        });

        // Hover effects
        state.map.on('mouseenter', 'zip-layer', () => {
            state.map.getCanvas().style.cursor = 'pointer';
        });
        state.map.on('mouseleave', 'zip-layer', () => {
            state.map.getCanvas().style.cursor = '';
        });

        // Error handling
        state.map.on('error', (e) => {
            console.error('Map error:', e.error);
            showToast('Map error: ' + e.error.message, 'error');
        });

        // Keyboard navigation for map
        initMapKeyboardControls();

    } catch (err) {
        console.error('Map initialization failed:', err);
        showMapError('Failed to initialize map: ' + err.message);
    }
}

// Show map error in container
function showMapError(message) {
    const mapContainer = document.getElementById('map');
    if (mapContainer) {
        mapContainer.innerHTML = `
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:24px;text-align:center;color:var(--text-secondary);">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:16px;opacity:0.5;">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="15" y1="9" x2="9" y2="15"/>
                    <line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <p style="font-size:var(--fs-md);font-weight:500;color:var(--text-primary);margin-bottom:8px;">Map unavailable</p>
                <p style="font-size:var(--fs-sm);max-width:400px;">${message}</p>
                <button class="btn btn-primary" style="margin-top:16px;" onclick="window.location.reload()">Reload page</button>
            </div>
        `;
    }
    if (els.loadingOverlay) {
        els.loadingOverlay.classList.add('hidden');
    }
}

// Load GeoJSON data
async function loadGeoJSON() {
    showLoading(true);
    try {
        const response = await fetch(CONFIG.GEOJSON_URL);
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        state.geojsonData = await response.json();

        // Validate data
        if (!state.geojsonData.features || state.geojsonData.features.length === 0) {
            throw new Error('No features found in GeoJSON');
        }

        // Populate segment filter from actual data
        populateSegmentFilter();

        // Add map layers
        addMapLayers();

        // Apply initial filters
        applyFilters();

        // Update stats
        updateStats();

        showLoading(false);
        showToast(`Loaded ${state.geojsonData.features.length} ZIP codes`, 'success');
    } catch (err) {
        console.error('Failed to load GeoJSON:', err);
        showLoading(false);
        showErrorState(err.message);
    }
}

// Add map layers
function addMapLayers() {
    // Source
    state.map.addSource('zip-data', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        generateId: true,
        promoteId: 'zip_code'
    });

    // Build segment color match expression
function buildSegmentColorExpression() {
    const expr = ['match', ['get', 'market_segment']];
    Object.entries(CONFIG.SEGMENTS).forEach(([key, seg]) => {
        expr.push(key, seg.color);
    });
    expr.push('#64748b'); // default fallback
    return expr;
}

// Choropleth fill-extrusion layer - colored by market segment, height by opportunity
    state.map.addLayer({
        id: 'zip-layer',
        type: 'fill-extrusion',
        source: 'zip-data',
        paint: {
            'fill-extrusion-color': buildSegmentColorExpression(),
            'fill-extrusion-height': [
                'interpolate', ['exponential', 1.5], ['get', 'overall_opportunity_score'],
                0.34, CONFIG.EXTRUSION.min,
                0.69, CONFIG.EXTRUSION.max
            ],
            'fill-extrusion-base': CONFIG.EXTRUSION.base,
            'fill-extrusion-opacity': 0.85
        }
    });

    // Border layer
    state.map.addLayer({
        id: 'zip-borders',
        type: 'line',
        source: 'zip-data',
        paint: {
            'line-color': '#2a3548',
            'line-width': [
                'interpolate', ['linear'], ['zoom'],
                4, 0.3,
                8, 0.5,
                12, 1
            ],
            'line-opacity': 0.5
        }
    });

    // Highlight layer for selected ZIP - bottom edge (line)
    state.map.addLayer({
        id: 'zip-highlight',
        type: 'line',
        source: 'zip-data',
        filter: ['==', 'zip_code', ''],
        paint: {
            'line-color': '#d4a843',
            'line-width': 3,
            'line-opacity': 1
        }
    });

    // Highlight layer for selected ZIP - top edge (thin fill-extrusion slice)
    state.map.addLayer({
        id: 'zip-highlight-top',
        type: 'fill-extrusion',
        source: 'zip-data',
        filter: ['==', 'zip_code', ''],
        paint: {
            'fill-extrusion-color': '#d4a843',
            'fill-extrusion-height': 3,  // Thin top slice
            'fill-extrusion-base': [
                'interpolate', ['exponential', 1.5], ['get', 'overall_opportunity_score'],
                0.34, CONFIG.EXTRUSION.min - 3,
                0.69, CONFIG.EXTRUSION.max - 3
            ],
            'fill-extrusion-opacity': 1
        }
    });
}

// Build color interpolation expression (kept for reference/other uses)
function buildColorInterpolation() {
    const expr = ['interpolate', ['linear'], ['get', 'overall_opportunity_score']];
    CONFIG.OPPORTUNITY_COLORS.forEach(([stop, color]) => {
        expr.push(stop, color);
    });
    return expr;
}

// Build segment color match expression for map layer
function buildSegmentColorExpression() {
    const expr = ['match', ['get', 'market_segment']];
    Object.entries(CONFIG.SEGMENTS).forEach(([key, seg]) => {
        expr.push(key, seg.color);
    });
    expr.push('#64748b'); // default fallback
    return expr;
}

// Debounced filter application
function debouncedApplyFilters() {
    // Clear any pending timer
    if (state.filterTimers.main) {
        clearTimeout(state.filterTimers.main);
    }
    state.filterTimers.main = setTimeout(() => {
        applyFilters();
        state.filterTimers.main = null;
    }, CONFIG.FILTER_DEBOUNCE_MS);
}

// Map keyboard navigation
function initMapKeyboardControls() {
    if (!state.map) return;

    const canvas = state.map.getCanvas();
    if (!canvas) return;

    // Make canvas focusable
    canvas.setAttribute('tabindex', '0');
    canvas.setAttribute('role', 'application');
    canvas.setAttribute('aria-label', 'Insurance opportunity map. Use arrow keys to pan, +/- to zoom, Shift+arrows to tilt/rotate, Enter to select nearest ZIP.');

    canvas.addEventListener('keydown', (e) => {
        // Don't interfere with input fields
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        const { panDegrees, zoomStep, pitchStep, bearingStep } = CONFIG.MAP_KEYBOARD;
        let handled = true;

        switch (e.key) {
            case 'ArrowUp':
                if (e.shiftKey) {
                    // Shift+Up = increase pitch (tilt up)
                    state.map.setPitch(Math.min(60, state.map.getPitch() + pitchStep));
                } else {
                    // Pan north
                    state.map.panBy([0, -100], { duration: 200 });
                }
                break;
            case 'ArrowDown':
                if (e.shiftKey) {
                    // Shift+Down = decrease pitch (tilt down)
                    state.map.setPitch(Math.max(0, state.map.getPitch() - pitchStep));
                } else {
                    // Pan south
                    state.map.panBy([0, 100], { duration: 200 });
                }
                break;
            case 'ArrowLeft':
                if (e.shiftKey) {
                    // Shift+Left = rotate counter-clockwise
                    state.map.setBearing(state.map.getBearing() - bearingStep);
                } else if (e.altKey) {
                    // Alt+Left = decrease bearing (same as Shift+Left for clarity)
                    state.map.setBearing(state.map.getBearing() - bearingStep);
                } else {
                    // Pan west
                    state.map.panBy([-100, 0], { duration: 200 });
                }
                break;
            case 'ArrowRight':
                if (e.shiftKey) {
                    // Shift+Right = rotate clockwise
                    state.map.setBearing(state.map.getBearing() + bearingStep);
                } else if (e.altKey) {
                    // Alt+Right = increase bearing
                    state.map.setBearing(state.map.getBearing() + bearingStep);
                } else {
                    // Pan east
                    state.map.panBy([100, 0], { duration: 200 });
                }
                break;
            case '+':
            case '=':
                // Zoom in
                state.map.zoomIn({ duration: 200 });
                break;
            case '-':
            case '_':
                // Zoom out
                state.map.zoomOut({ duration: 200 });
                break;
            case 'Enter':
            case ' ':
                // Select nearest visible ZIP to center
                e.preventDefault();
                selectNearestZipToCenter();
                break;
            case 'Home':
                // Reset view to region
                e.preventDefault();
                state.map.flyTo({
                    center: CONFIG.MAP.center,
                    zoom: CONFIG.MAP.zoom,
                    pitch: CONFIG.MAP.pitch,
                    bearing: CONFIG.MAP.bearing,
                    duration: 1000
                });
                showToast('View reset to region', 'info');
                break;
            case 'r':
            case 'R':
                // Reset filters
                if (!e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    resetFilters();
                }
                handled = false; // Allow browser default for Ctrl+R
                break;
            default:
                handled = false;
        }

        if (handled) {
            e.preventDefault();
        }
    });

    // Focus canvas on map click so keyboard works immediately
    canvas.addEventListener('click', () => {
        canvas.focus();
    });
}

// Select nearest ZIP to map center
function selectNearestZipToCenter() {
    if (!state.map || !state.geojsonData) return;

    const center = state.map.getCenter();
    const centerPoint = state.map.project(center);

    let nearestFeature = null;
    let nearestDist = Infinity;

    // Check visible features in zip-layer
    const features = state.map.queryRenderedFeatures({ layers: ['zip-layer'] });

    for (const feature of features) {
        if (feature.geometry.type === 'Polygon' || feature.geometry.type === 'MultiPolygon') {
            // Get centroid of feature
            const coords = feature.geometry.coordinates[0][0]; // First ring, first coord
            const featurePoint = state.map.project([coords[0], coords[1]]);
            const dist = Math.hypot(featurePoint.x - centerPoint.x, featurePoint.y - centerPoint.y);
            if (dist < nearestDist) {
                nearestDist = dist;
                nearestFeature = feature;
            }
        }
    }

    if (nearestFeature) {
        showZipInfo(nearestFeature.properties);
        state.selectedZip = nearestFeature.properties.zip_code;
        showToast(`Selected ZIP ${nearestFeature.properties.zip_code}`, 'info');
    } else {
        showToast('No ZIP codes visible at this zoom', 'info');
    }
}

// Apply filters
function applyFilters() {
    if (!state.geojsonData || !state.map) return;

    const filtered = state.geojsonData.features.filter(f => {
        const p = f.properties;

        // Segment filter
        if (state.filters.segment && p.market_segment !== state.filters.segment) return false;

        // Score filters
        if (p.overall_opportunity_score < state.filters.minOpp) return false;
        if (p.standard_market_score < state.filters.minStd) return false;
        if (p.non_standard_market_score < state.filters.minNonStd) return false;

        return true;
    });

    // Update source
    const source = state.map.getSource('zip-data');
    if (source) {
        source.setData({
            type: 'FeatureCollection',
            features: filtered
        });
    }

    // Update highlight if selected ZIP was filtered out
    if (state.selectedZip && !filtered.find(f => f.properties.zip_code === state.selectedZip)) {
        state.selectedZip = null;
        updateHighlight('');
        showEmptyDetail();
    }

    // Update stats
    updateStats(filtered.length);

    // Update active filters count
    updateActiveFiltersCount();
}

// Update highlight layer filters (both bottom line and top slice)
function updateHighlight(zipCode) {
    const filter = ['==', 'zip_code', zipCode || ''];
    state.map.setFilter('zip-highlight', filter);
    state.map.setFilter('zip-highlight-top', filter);
}

// Populate segment filter dropdown
function populateSegmentFilter() {
    if (!els.segmentFilter) return;

    const segments = state.geojsonData
        ? [...new Set(state.geojsonData.features.map(f => f.properties.market_segment).filter(Boolean))].sort()
        : Object.keys(CONFIG.SEGMENTS).sort();

    // Clear existing options except first
    while (els.segmentFilter.options.length > 1) {
        els.segmentFilter.remove(1);
    }

    segments.forEach(s => {
        const seg = CONFIG.SEGMENTS[s];
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = seg ? seg.label : s;
        els.segmentFilter.appendChild(opt);
    });
}

// Populate legend segments
function populateLegendSegments() {
    if (!els.legendSegments) return;

    els.legendSegments.innerHTML = '';

    Object.entries(CONFIG.SEGMENTS).forEach(([key, seg]) => {
        const item = document.createElement('div');
        item.className = 'legend-segment';

        let patternHtml = '';
        if (seg.pattern && seg.pattern !== 'none') {
            const patternDataUri = generatePatternSvg(seg.pattern, seg.color);
            if (patternDataUri) {
                patternHtml = `<span class="legend-pattern" style="background-image: url(${patternDataUri}); background-size: 16px 16px; width: 16px; height: 16px; border-radius: var(--radius-sm); display: inline-block; margin-right: var(--space-2);"></span>`;
            }
        }

        item.innerHTML = `
            ${patternHtml}
            <span class="legend-segment-dot" style="background: ${seg.color};"></span>
            <span title="${seg.desc}">${seg.label}</span>
        `;
        els.legendSegments.appendChild(item);
    });
}

// Show ZIP info in detail panel
function showZipInfo(props) {
    const f = CONFIG.FORMAT;

    els.detailContent.innerHTML = `
        <div class="zip-info-grid">
            <div class="zip-info-header">
                <span class="zip-info-title">ZIP ${props.zip_code}</span>
                <span class="segment-badge segment-${props.market_segment || 'Moderate'}">
                    ${CONFIG.SEGMENTS[props.market_segment]?.label || props.market_segment || 'Moderate'}
                </span>
            </div>

            <div class="zip-info-row">
                <span class="zip-info-label">Overall Opportunity</span>
                <span class="zip-info-value">${f.score(props.overall_opportunity_score)}</span>
                <span class="zip-info-label">Standard Market</span>
                <span class="zip-info-value">${f.score(props.standard_market_score)}</span>
                <span class="zip-info-label">Non-Standard Market</span>
                <span class="zip-info-value">${f.score(props.non_standard_market_score)}</span>
            </div>

            <div class="zip-info-row" style="border-top: 1px solid var(--border-muted); padding-top: 8px; margin-top: 4px;">
                <span class="zip-info-label">Vulnerability Index</span>
                <span class="zip-info-value">${f.score(props.vulnerability_index)}</span>
                <span class="zip-info-label">Visibility Multiplier</span>
                <span class="zip-info-value">${f.score(props.visibility_multiplier)}</span>
                <span class="zip-info-label">Risk Alignment</span>
                <span class="zip-info-value">${f.score(props.risk_alignment)}</span>
            </div>

            <div class="zip-info-row" style="border-top: 1px solid var(--border-muted); padding-top: 8px; margin-top: 4px;">
                <span class="zip-info-label">Median Home Value</span>
                <span class="zip-info-value">${f.dollar(props.median_home_value)}</span>
                <span class="zip-info-label">Median Income</span>
                <span class="zip-info-value">${f.dollar(props.median_household_income)}</span>
                <span class="zip-info-label">Vehicles / Household</span>
                <span class="zip-info-value">${f.decimal(props.vehicles_per_household)}</span>
            </div>

            <div class="zip-info-row">
                <span class="zip-info-label">Renter %</span>
                <span class="zip-info-value">${f.percent(props.renter_pct)}</span>
                <span class="zip-info-label">Spanish Speaking %</span>
                <span class="zip-info-value">${f.percent(props.spanish_speaking_pct)}</span>
            </div>

            <div class="zip-info-row" style="border-top: 1px solid var(--border-muted); padding-top: 8px; margin-top: 4px;">
                <span class="zip-info-label">Total Crashes</span>
                <span class="zip-info-value">${f.number(props.total_crashes)}</span>
                <span class="zip-info-label">Total Competitors</span>
                <span class="zip-info-value">${f.number(props.total_competitors)}</span>
                <span class="zip-info-label">Franchise / Independent</span>
                <span class="zip-info-value">${f.number(props.franchise_competitors)} / ${f.number(props.independent_competitors)}</span>
            </div>

            <div class="zip-info-row">
                <span class="zip-info-label">Avg AADT</span>
                <span class="zip-info-value">${f.number(props.avg_aadt)}</span>
                <span class="zip-info-label">Max AADT</span>
                <span class="zip-info-value">${f.number(props.max_aadt)}</span>
                <span class="zip-info-label">Area (sq km)</span>
                <span class="zip-info-value">${f.decimal(props.area_sqkm, 1)}</span>
            </div>
        </div>
    `;

    // Show copy button
    els.copyBtn.hidden = false;
    els.copyBtn.onclick = () => copyZipData(props);

    // Update highlight
    updateHighlight(props.zip_code);

    // Update stats to reflect current filter state
    updateStats();
}

function showEmptyDetail() {
    els.detailContent.innerHTML = `
        <div class="detail-empty">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                <circle cx="12" cy="10" r="3"/>
            </svg>
            <p>Click a ZIP code on the map</p>
            <span>to see detailed metrics</span>
        </div>
    `;
    els.copyBtn.hidden = true;
    updateHighlight('');
}

function copyZipData(props) {
    const data = {
        zip_code: props.zip_code,
        market_segment: props.market_segment,
        overall_opportunity_score: props.overall_opportunity_score,
        standard_market_score: props.standard_market_score,
        non_standard_market_score: props.non_standard_market_score,
        vulnerability_index: props.vulnerability_index,
        visibility_multiplier: props.visibility_multiplier,
        risk_alignment: props.risk_alignment,
        median_home_value: props.median_home_value,
        median_household_income: props.median_household_income,
        vehicles_per_household: props.vehicles_per_household,
        renter_pct: props.renter_pct,
        spanish_speaking_pct: props.spanish_speaking_pct,
        total_crashes: props.total_crashes,
        total_competitors: props.total_competitors,
        franchise_competitors: props.franchise_competitors,
        independent_competitors: props.independent_competitors,
        avg_aadt: props.avg_aadt,
        max_aadt: props.max_aadt,
        area_sqkm: props.area_sqkm
    };

    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
        .then(() => showToast('ZIP data copied to clipboard', 'success'))
        .catch(() => showToast('Failed to copy', 'error'));
}

// Update stats cards
function updateStats(filteredCount = null) {
    if (!state.geojsonData) return;

    const total = state.geojsonData.features.length;
    const filtered = filteredCount !== null ? filteredCount : total;

    // Calculate average opportunity score
    const features = filteredCount !== null
        ? state.geojsonData.features.filter(f => {
            const p = f.properties;
            if (state.filters.segment && p.market_segment !== state.filters.segment) return false;
            if (p.overall_opportunity_score < state.filters.minOpp) return false;
            if (p.standard_market_score < state.filters.minStd) return false;
            if (p.non_standard_market_score < state.filters.minNonStd) return false;
            return true;
        })
        : state.geojsonData.features;

    const avgOpp = features.length > 0
        ? features.reduce((sum, f) => sum + (f.properties.overall_opportunity_score || 0), 0) / features.length
        : 0;

    els.statTotalZips.textContent = total.toLocaleString();
    els.statFilteredZips.textContent = filtered.toLocaleString();
    els.statAvgOpp.textContent = (avgOpp * 100).toFixed(1) + '%';
}

// Update active filters count
function updateActiveFiltersCount() {
    let count = 0;
    if (state.filters.segment) count++;
    if (state.filters.minOpp > 0) count++;
    if (state.filters.minStd > 0) count++;
    if (state.filters.minNonStd > 0) count++;

    els.activeFiltersCount.textContent = count > 0 ? `${count} filter${count > 1 ? 's' : ''} active` : 'No filters active';
    els.activeFiltersCount.style.color = count > 0 ? 'var(--accent-gold)' : 'var(--text-muted)';
}

// Update scale bar - uses MapLibre's internal scale for accuracy
function updateScaleBar() {
    if (!state.map || !els.scaleBarLine || !els.scaleBarLabel) return;

    // Use MapLibre's transform to get accurate scale
    // Project two points 100px apart horizontally at center latitude
    const center = state.map.getCenter();
    const centerPoint = state.map.project(center);
    const rightPoint = state.map.unproject([centerPoint.x + 100, centerPoint.y]);

    // Calculate distance using haversine formula
    const R = 6371000; // Earth radius in meters
    const lat1 = center.lat * Math.PI / 180;
    const lat2 = rightPoint.lat * Math.PI / 180;
    const dLat = (rightPoint.lat - center.lat) * Math.PI / 180;
    const dLon = (rightPoint.lng - center.lng) * Math.PI / 180;

    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1) * Math.cos(lat2) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    const distanceMeters = R * c;

    // Find appropriate threshold
    let label = '5 mi';
    let width = 100;

    for (const threshold of CONFIG.SCALE_THRESHOLDS) {
        if (distanceMeters >= threshold.max) {
            label = threshold.label;
            width = threshold.width;
            break;
        }
    }

    els.scaleBarLine.style.width = width + 'px';
    els.scaleBarLabel.textContent = label;
}

// Show/hide loading overlay
function showLoading(show) {
    if (els.loadingOverlay) {
        els.loadingOverlay.classList.toggle('hidden', !show);
    }
}

// Show error state
function showErrorState(message) {
    els.detailContent.innerHTML = `
        <div class="detail-empty" style="color: var(--semantic-high);">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
            <p>Failed to load data</p>
            <span>${message}</span>
            <button class="btn btn-primary" style="margin-top: 12px;" onclick="loadGeoJSON()">Retry</button>
        </div>
    `;
}

// Toast notifications
function showToast(message, type = 'info') {
    if (!els.toastContainer) return;

    const icons = {
        success: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#d4a843" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `${icons[type]}<span class="toast-message">${message}</span>`;

    els.toastContainer.appendChild(toast);

    // Auto-dismiss after 4s
    setTimeout(() => {
        dismissToast(toast);
    }, 4000);
}

function dismissToast(toast) {
    // Use animationend for clean removal, fallback to timeout
    const handleEnd = () => {
        toast.removeEventListener('animationend', handleEnd);
        toast.remove();
    };
    toast.addEventListener('animationend', handleEnd);
    toast.style.animation = 'toastIn 0.2s ease reverse';

    // Fallback in case animationend doesn't fire (e.g., reduced motion)
    setTimeout(() => {
        toast.removeEventListener('animationend', handleEnd);
        toast.remove();
    }, 300);
}

// Bind event listeners
function bindEvents() {
    // Segment filter
    els.segmentFilter?.addEventListener('change', (e) => {
        state.filters.segment = e.target.value;
        applyFilters();
    });

    // Score sliders (UI is 0-100, internal is 0-1)
    const sliderMap = {
        oppScoreFilter: { key: 'minOpp', valueEl: 'oppScoreValue' },
        stdScoreFilter: { key: 'minStd', valueEl: 'stdScoreValue' },
        nonStdScoreFilter: { key: 'minNonStd', valueEl: 'nonStdScoreValue' }
    };

    Object.entries(sliderMap).forEach(([id, config]) => {
        const el = document.getElementById(id);
        const valueEl = document.getElementById(config.valueEl);
        if (!el || !valueEl) return;

        // Use debounced filter application for sliders
        el.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value) / 100; // UI 0-100 -> internal 0-1
            state.filters[config.key] = config.reverse ? 1 - val : val;
            valueEl.textContent = Math.round((config.reverse ? 1 - val : val) * 100) + '%';
            debouncedApplyFilters();
        });

        // Threshold clicks - apply immediately (button click)
        el.parentElement?.querySelectorAll('.threshold').forEach(th => {
            th.addEventListener('click', () => {
                const targetVal = parseFloat(th.dataset.value) / 100;
                const internalVal = config.reverse ? 1 - targetVal : targetVal;
                const displayVal = config.reverse ? 1 - targetVal : targetVal;
                el.value = displayVal * 100;
                state.filters[config.key] = internalVal;
                valueEl.textContent = Math.round(displayVal * 100) + '%';
                // Clear any pending debounce and apply immediately
                if (state.filterTimers.main) {
                    clearTimeout(state.filterTimers.main);
                    state.filterTimers.main = null;
                }
                applyFilters();
            });
        });
    });

    // Panel toggle (in header)
    // Panel starts open on desktop
    els.panel.classList.remove('collapsed');
    state.ui.panelCollapsed = false;
    if (els.panelToggle) {
        els.panelToggle.setAttribute('aria-expanded', 'true');
        els.panelToggle.addEventListener('click', () => {
            state.ui.panelCollapsed = !state.ui.panelCollapsed;
            const expanded = !state.ui.panelCollapsed;
            els.panel.classList.toggle('collapsed', state.ui.panelCollapsed);
            els.panelToggle.setAttribute('aria-expanded', expanded);
        });
    }

    // Legend toggle
    els.legendToggle?.addEventListener('click', () => {
        state.ui.legendCollapsed = !state.ui.legendCollapsed;
        document.getElementById('mapLegend').classList.toggle('collapsed', state.ui.legendCollapsed);
        els.legendToggle.setAttribute('aria-expanded', !state.ui.legendCollapsed);
        // Rotate icon
        els.legendToggle.querySelector('svg').style.transform = state.ui.legendCollapsed ? 'rotate(-90deg)' : 'rotate(0)';
    });

    // Reset button (in panel header)
    els.resetBtn?.addEventListener('click', resetFilters);

    // Help modal with focus management
    els.helpBtn?.addEventListener('click', () => {
        els.helpModal.showModal();
        openModal(els.helpModal);
    });
    els.helpClose?.addEventListener('click', () => {
        closeModal(els.helpModal);
        els.helpModal.close();
    });
    els.helpModal?.addEventListener('click', (e) => {
        if (e.target === els.helpModal) {
            closeModal(els.helpModal);
            els.helpModal.close();
        }
    });

    // Onboarding modal with focus management
    const onboardingModal = document.getElementById('onboardingModal');
    onboardingModal?.addEventListener('click', (e) => {
        if (e.target === onboardingModal) {
            closeModal(onboardingModal);
            closeOnboarding();
        }
    });

    // Keyboard: ESC closes modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (els.helpModal?.open) {
                closeModal(els.helpModal);
                els.helpModal.close();
            }
            if (onboardingModal?.open) {
                closeModal(onboardingModal);
                closeOnboarding();
            }
        }
    });

    // Initialize mobile panel swipe
    initPanelSwipe();
}

// Reset all filters
function resetFilters() {
    state.filters = {
        segment: '',
        minOpp: 0,
        minStd: 0,
        minNonStd: 0
    };

    // Reset UI
    els.segmentFilter.value = '';

    const sliders = [
        { id: 'oppScoreFilter', val: 0, reverse: false },
        { id: 'stdScoreFilter', val: 0, reverse: false },
        { id: 'nonStdScoreFilter', val: 0, reverse: false }
    ];

    sliders.forEach(({ id, val, reverse }) => {
        const el = document.getElementById(id);
        const valueEl = document.getElementById(id.replace('Filter', 'Value'));
        if (el) el.value = val;
        if (valueEl) {
            const displayVal = reverse ? Math.round((1 - val / 100) * 100) : val;
            valueEl.textContent = displayVal + '%';
        }
    });

    applyFilters();
    showToast('Filters reset', 'info');
}

// Initialize tooltips (CSS-based, but ensure they work on focus too)
function initTooltips() {
    // Tooltips work via CSS [data-tooltip] - just ensure focus works
    document.querySelectorAll('[data-tooltip]').forEach(el => {
        el.addEventListener('focus', () => el.setAttribute('data-tooltip-visible', 'true'));
        el.addEventListener('blur', () => el.removeAttribute('data-tooltip-visible'));
    });
}

// Quick hint with dismissal
function initQuickHint() {
    const hint = document.getElementById('quickHint');
    if (!hint) return;

    // Check if dismissed this session
    if (sessionStorage.getItem('quickHintDismissed') === 'true') {
        hint.remove();
        return;
    }

    // Show hint
    setTimeout(() => {
        hint.classList.add('visible');
    }, 1000);

    // Auto-hide after 8 seconds
    setTimeout(() => {
        if (hint.parentElement) {
            hint.classList.remove('visible');
            setTimeout(() => hint.remove(), 500);
        }
    }, 9000);

    // Click to dismiss
    hint.addEventListener('click', () => {
        hint.classList.remove('visible');
        setTimeout(() => hint.remove(), 500);
        sessionStorage.setItem('quickHintDismissed', 'true');
    });
}

// Modal focus management
function openModal(modal) {
    // Store previous active element
    state.modal.previousActiveElement = document.activeElement;

    // Find focusable elements in modal
    const focusableSelectors = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    state.modal.focusTrapElements = Array.from(modal.querySelectorAll(focusableSelectors));

    // Focus first focusable element
    if (state.modal.focusTrapElements.length > 0) {
        state.modal.focusTrapElements[0].focus();
    }

    // Add focus trap
    modal.addEventListener('keydown', handleModalKeydown);
}

function closeModal(modal) {
    // Remove focus trap
    modal.removeEventListener('keydown', handleModalKeydown);

    // Restore focus to trigger element
    if (state.modal.previousActiveElement && typeof state.modal.previousActiveElement.focus === 'function') {
        state.modal.previousActiveElement.focus();
    }
    state.modal.previousActiveElement = null;
    state.modal.focusTrapElements = [];
}

function handleModalKeydown(e) {
    if (e.key !== 'Tab') return;

    const focusable = state.modal.focusTrapElements;
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
        // Shift+Tab: go to last if on first
        if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
        }
    } else {
        // Tab: go to first if on last
        if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }
}

// Touch swipe for mobile panel drawer
function initPanelSwipe() {
    const panel = document.getElementById('sidePanel');
    if (!panel) return;

    let startX = 0;
    let currentX = 0;
    let isDragging = false;

    panel.addEventListener('touchstart', (e) => {
        // Only enable swipe when panel is open (not collapsed)
        if (panel.classList.contains('collapsed')) return;

        startX = e.touches[0].clientX;
        isDragging = true;
    }, { passive: true });

    panel.addEventListener('touchmove', (e) => {
        if (!isDragging) return;

        currentX = e.touches[0].clientX;
        const deltaX = currentX - startX;

        // Only allow swipe right (closing) on mobile
        if (deltaX > 0) {
            e.preventDefault();
            panel.style.transform = `translateX(${Math.min(deltaX, 380)}px)`;
        }
    }, { passive: false });

    panel.addEventListener('touchend', () => {
        if (!isDragging) return;
        isDragging = false;

        const deltaX = currentX - startX;

        if (deltaX > 100) {
            // Swipe threshold met - close panel
            state.ui.panelCollapsed = true;
            panel.classList.add('collapsed');
            panel.style.transform = '';
            if (els.panelToggle) {
                els.panelToggle.setAttribute('aria-expanded', 'false');
            }
        } else {
            // Snap back
            panel.style.transform = '';
        }
    }, { passive: true });
}

// ============================================
// WORKFLOW STEPS INTERACTION
// ============================================
function initWorkflowSteps() {
    document.querySelectorAll('.workflow-step').forEach(step => {
        step.addEventListener('click', () => {
            const targetStep = step.dataset.step;
            activateWorkflowStep(targetStep);
            scrollToStep(targetStep);
        });

        // Keyboard activation (Enter/Space) - buttons handle this natively, but ensure aria-selected updates
        step.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                step.click();
            }
        });
    });
}

function activateWorkflowStep(stepNum) {
    document.querySelectorAll('.workflow-step').forEach(step => {
        const isActive = step.dataset.step === stepNum;
        step.classList.toggle('active', isActive);
        step.setAttribute('aria-selected', isActive);
    });

    // Toggle visibility of workflow step sections
    document.querySelectorAll('.workflow-step-section').forEach(section => {
        const isActive = section.dataset.stepSection === stepNum;
        section.classList.toggle('active', isActive);
    });
}

function scrollToStep(stepNum) {
    const targets = {
        '1': '#segmentFilter',
        '2': '#oppScoreFilter',
        '3': '#map'
    };
    const target = document.querySelector(targets[stepNum]);
    if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Add a brief highlight
        target.style.boxShadow = '0 0 0 3px rgba(212, 168, 67, 0.5)';
        setTimeout(() => { target.style.boxShadow = ''; }, 1500);
    }
}

// Update workflow step based on user interaction
function updateWorkflowFromInteraction(stepNum) {
    activateWorkflowStep(stepNum);
}

// ============================================
// ONBOARDING MODAL
// ============================================
function initOnboarding() {
    const modal = document.getElementById('onboardingModal');
    const dontShow = document.getElementById('dontShowAgain');
    const footerNav = document.getElementById('onboardingFooterNav');

    // Check if user dismissed before
    if (localStorage.getItem('onboardingDismissed') === 'true') {
        return;
    }

    // Create footer navigation buttons
    createOnboardingFooterNav();

    // Show modal after a brief delay
    setTimeout(() => {
        modal.showModal();
        openModal(modal);
        // Initialize footer nav for step 1
        updateOnboardingFooterNav('1');
    }, 500);

    // Navigation buttons - use event delegation on footer
    footerNav?.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-next], [data-prev], #onboardingDone');
        if (!btn) return;

        if (btn.id === 'onboardingDone') {
            closeOnboarding();
        } else if (btn.dataset.next) {
            showOnboardingStep(btn.dataset.next);
        } else if (btn.dataset.prev) {
            showOnboardingStep(btn.dataset.prev);
        }
    });

    // Also bind click on the buttons directly as fallback
    document.getElementById('footerPrevBtn')?.addEventListener('click', (e) => {
        e.stopPropagation();
        const step = e.target.dataset.prev;
        if (step) showOnboardingStep(step);
    });
    document.getElementById('footerNextBtn')?.addEventListener('click', (e) => {
        e.stopPropagation();
        const step = e.target.dataset.next;
        if (step) showOnboardingStep(step);
    });
    document.getElementById('onboardingDone')?.addEventListener('click', (e) => {
        e.stopPropagation();
        closeOnboarding();
    });

    // Don't show again
    dontShow?.addEventListener('change', (e) => {
        if (e.target.checked) {
            localStorage.setItem('onboardingDismissed', 'true');
        }
    });

    // Close on backdrop click - handled by bindEvents with focus management
}

function createOnboardingFooterNav() {
    const footerNav = document.getElementById('onboardingFooterNav');
    if (!footerNav) return;

    footerNav.innerHTML = `
        <button class="btn btn-ghost" data-prev="1" id="footerPrevBtn" style="display: none;">← Back</button>
        <button class="btn btn-primary" data-next="2" id="footerNextBtn">Next →</button>
        <button class="btn btn-primary" id="onboardingDone" style="display: none;">Start Exploring →</button>
    `;
}

function showOnboardingStep(stepNum) {
    document.querySelectorAll('.onboarding-step').forEach(step => {
        step.classList.toggle('active', step.dataset.step === stepNum);
    });
    updateOnboardingFooterNav(stepNum);
}

function updateOnboardingFooterNav(stepNum) {
    const prevBtn = document.getElementById('footerPrevBtn');
    const nextBtn = document.getElementById('footerNextBtn');
    const doneBtn = document.getElementById('onboardingDone');

    if (!prevBtn || !nextBtn || !doneBtn) return;

    // Hide all by default
    prevBtn.style.display = 'none';
    nextBtn.style.display = 'none';
    doneBtn.style.display = 'none';

    switch (stepNum) {
        case '1':
            nextBtn.style.display = 'inline-flex';
            nextBtn.dataset.next = '2';
            nextBtn.textContent = 'Next →';
            break;
        case '2':
            prevBtn.style.display = 'inline-flex';
            prevBtn.dataset.prev = '1';
            nextBtn.style.display = 'inline-flex';
            nextBtn.dataset.next = '3';
            nextBtn.textContent = 'Next →';
            break;
        case '3':
            prevBtn.style.display = 'inline-flex';
            prevBtn.dataset.prev = '2';
            nextBtn.style.display = 'inline-flex';
            nextBtn.dataset.next = '4';
            nextBtn.textContent = 'Next →';
            break;
        case '4':
            prevBtn.style.display = 'inline-flex';
            prevBtn.dataset.prev = '3';
            doneBtn.style.display = 'inline-flex';
            break;
    }
}

function closeOnboarding() {
    const modal = document.getElementById('onboardingModal');
    closeModal(modal);
    modal.close();

    // Reveal side panel after onboarding completes
    const panel = document.getElementById('sidePanel');
    if (panel && panel.classList.contains('collapsed')) {
        panel.classList.remove('collapsed');
        // Update panel toggle button state
        if (els.panelToggle) {
            els.panelToggle.setAttribute('aria-expanded', 'true');
        }
    }
}

// Make functions globally accessible for inline handlers
window.loadGeoJSON = loadGeoJSON;
