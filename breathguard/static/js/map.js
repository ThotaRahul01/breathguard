// Global variables
let map;
let zones = [];
let markers = [];
let userMarker = null;
let selectedZone = null;
let alertCheckInterval = null;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initMap();
    loadZones();
    startLocationTracking();
    
    // Hide loading after 2 seconds
    setTimeout(() => {
        document.getElementById('loading').classList.add('hidden');
    }, 2000);
});

function initMap() {
    // Center on Varanasi (IIT BHU)
    map = L.map('map').setView([25.2677, 82.9913], 13);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);
    
    // Add locate button
    L.control.locate = L.Control.extend({
        onAdd: function(map) {
            const btn = L.DomUtil.create('button');
            btn.innerHTML = '<i class="fas fa-crosshairs"></i>';
            btn.className = 'btn btn-primary';
            btn.style.padding = '10px';
            btn.onclick = () => locateUser();
            return btn;
        }
    });
    
    new L.control.locate({ position: 'topright' }).addTo(map);
}

function getColorForPM25(pm25) {
    if (pm25 <= 30) return '#4CAF50';
    if (pm25 <= 60) return '#8BC34A';
    if (pm25 <= 90) return '#FFC107';
    if (pm25 <= 120) return '#FF9800';
    if (pm25 <= 250) return '#F44336';
    return '#9C27B0';
}

function getColorForLevel(level) {
    const colors = ['#4CAF50', '#8BC34A', '#FFC107', '#FF9800', '#F44336', '#9C27B0'];
    return colors[level - 1] || '#888';
}

function createCustomIcon(pm25, hasSensor) {
    const color = getColorForPM25(pm25);
    const size = hasSensor ? 30 : 25;
    const border = hasSensor ? '3px solid #fff' : '2px solid rgba(255,255,255,0.5)';
    
    return L.divIcon({
        className: 'custom-marker',
        html: `<div style="
            width: ${size}px;
            height: ${size}px;
            background: ${color};
            border-radius: 50%;
            border: ${border};
            box-shadow: 0 4px 15px ${color}80;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: ${hasSensor ? '12px' : '10px'};
        ">${hasSensor ? 'S' : ''}</div>`,
        iconSize: [size, size],
        iconAnchor: [size/2, size/2]
    });
}

function loadZones() {
    fetch('/api/zones')
        .then(res => res.json())
        .then(data => {
            zones = data;
            displayZones();
            updateStats();
        })
        .catch(err => console.error('Error loading zones:', err));
}

function displayZones() {
    markers.forEach(m => map.removeLayer(m));
    markers = [];
    
    zones.forEach(zone => {
        const marker = L.marker([zone.lat, zone.lng], {
            icon: createCustomIcon(zone.pm25, zone.has_sensor)
        }).addTo(map);
        
        const popupContent = `
            <div style="min-width: 200px;">
                <h3 style="margin: 0 0 10px 0; color: ${zone.aqi_color};">${zone.name}</h3>
                <div style="font-size: 1.5rem; font-weight: bold; color: ${zone.aqi_color};">
                    ${zone.pm25} µg/m³
                </div>
                <div style="color: #666; margin: 5px 0;">${zone.aqi_category}</div>
                <div style="font-size: 0.8rem; color: #888; margin-top: 10px;">
                    Source: ${zone.data_source}
                </div>
                <button onclick="selectZone(${zone.id})" style="
                    margin-top: 10px;
                    width: 100%;
                    padding: 8px;
                    background: #1a5f7a;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                ">View Details</button>
            </div>
        `;
        
        marker.bindPopup(popupContent);
        marker.on('click', () => selectZone(zone.id));
        
        // Pulse animation for high pollution
        if (zone.aqi_level >= 4) {
            marker.getElement().style.animation = 'pulse 2s infinite';
        }
        
        markers.push(marker);
    });
}

function selectZone(zoneId) {
    selectedZone = zones.find(z => z.id === zoneId);
    if (!selectedZone) return;
    
    // Show zone panel
    document.getElementById('zonePanel').classList.add('active');
    document.getElementById('forecastPanel').classList.add('active');
    
    // Update zone content
    const zoneContent = document.getElementById('zoneContent');
    zoneContent.innerHTML = `
        <h4 style="color: white; margin-bottom: 10px;">${selectedZone.name}</h4>
        <div class="aqi-badge" style="background: ${selectedZone.aqi_color}20; color: ${selectedZone.aqi_color}; border: 2px solid ${selectedZone.aqi_color};">
            <i class="fas fa-wind"></i>
            ${selectedZone.aqi_category} (${selectedZone.pm25} µg/m³)
        </div>
        <div class="data-source">
            <i class="fas fa-database"></i> Data: ${selectedZone.data_source}
            ${selectedZone.has_sensor ? ' | <i class="fas fa-satellite-dish"></i> Live Sensor' : ''}
        </div>
        
        <div style="margin-top: 15px;">
            <h5 style="color: var(--accent); margin-bottom: 10px;">Contributing Factors</h5>
            ${createFactorBar('Traffic', selectedZone.factors.traffic, '#FF6B6B')}
            ${createFactorBar('Construction', selectedZone.factors.construction, '#4ECDC4')}
            ${createFactorBar('Population', selectedZone.factors.population, '#45B7D1')}
        </div>
        
        <div style="margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 8px;">
            <div style="font-size: 0.85rem; color: #888; margin-bottom: 5px;">Current Weather</div>
            <div style="display: flex; gap: 15px; font-size: 0.9rem;">
                <span><i class="fas fa-wind"></i> ${selectedZone.factors.weather.wind_speed} km/h</span>
                <span><i class="fas fa-tint"></i> ${selectedZone.factors.weather.humidity}%</span>
            </div>
        </div>
        
        <button class="btn btn-primary" style="width: 100%; margin-top: 15px;" onclick="subscribeAlert(${selectedZone.id})">
            <i class="fas fa-bell"></i> Subscribe to Alerts
        </button>
    `;
    
    // Load forecast
    loadForecast(zoneId);
    
    // Highlight marker
    map.panTo([selectedZone.lat, selectedZone.lng]);
}

function createFactorBar(label, value, color) {
    return `
        <div style="margin: 8px 0;">
            <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
                <span>${label}</span>
                <span>${(value * 100).toFixed(0)}%</span>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                <div style="width: ${value * 100}%; height: 100%; background: ${color}; border-radius: 3px; transition: width 0.5s;"></div>
            </div>
        </div>
    `;
}

function loadForecast(zoneId) {
    fetch(`/api/forecast/${zoneId}`)
        .then(res => res.json())
        .then(data => {
            const container = document.getElementById('forecastContent');
            container.innerHTML = '';
            
            data.forecast.slice(0, 12).forEach((hour, idx) => {
                const bar = document.createElement('div');
                bar.className = 'forecast-bar';
                bar.innerHTML = `
                    <div class="forecast-time">${hour.hour}</div>
                    <div class="forecast-visual">
                        <div class="forecast-fill" style="
                            width: ${Math.min(100, (hour.pm25 / 300) * 100)}%;
                            background: ${hour.aqi_color};
                        ">${hour.pm25}</div>
                    </div>
                `;
                container.appendChild(bar);
            });
            
            // Peak info
            const peak = data.peak_pollution;
            container.innerHTML += `
                <div style="margin-top: 15px; padding: 10px; background: rgba(231, 76, 60, 0.1); border-radius: 8px; border-left: 4px solid var(--danger);">
                    <div style="font-size: 0.85rem; color: #888;">Peak Pollution Expected</div>
                    <div style="font-weight: bold; color: var(--danger);">
                        ${peak.hour} - ${peak.pm25} µg/m³ (${peak.aqi_category})
                    </div>
                </div>
            `;
        });
}

function updateStats() {
    const pm25Values = zones.map(z => z.pm25);
    const avg = pm25Values.reduce((a, b) => a + b, 0) / pm25Values.length;
    const max = Math.max(...pm25Values);
    const sensors = zones.filter(z => z.has_sensor).length;
    
    document.getElementById('avgPM25').textContent = avg.toFixed(1);
    document.getElementById('maxPM25').textContent = max.toFixed(1);
    document.getElementById('sensorCount').textContent = sensors;
    document.getElementById('safeRoutes').textContent = zones.filter(z => z.aqi_level <= 2).length;
}

// Location & Alerts
function startLocationTracking() {
    if ("geolocation" in navigator) {
        navigator.geolocation.watchPosition(
            position => {
                const { latitude, longitude } = position.coords;
                updateUserLocation(latitude, longitude);
            },
            err => console.error('Geolocation error:', err),
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
        );
    }
    
    // Check alerts every minute
    alertCheckInterval = setInterval(checkNearbyAlerts, 60000);
}

function updateUserLocation(lat, lng) {
    if (!userMarker) {
        userMarker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'user-location',
                html: '<div style="width: 20px; height: 20px; background: #3498db; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 0 10px rgba(52, 152, 219, 0.3);"></div>',
                iconSize: [20, 20]
            })
        }).addTo(map);
    } else {
        userMarker.setLatLng([lat, lng]);
    }
    
    // Check alerts immediately on location update
    checkNearbyAlerts(lat, lng);
}

function checkNearbyAlerts(lat, lng) {
    if (!lat || !lng) return;
    
    fetch('/api/check-alerts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lng, user_id: 'user_001' })
    })
    .then(res => res.json())
    .then(data => {
        const dangerAlerts = data.alerts.filter(a => a.type === 'danger_zone');
        
        if (dangerAlerts.length > 0) {
            document.getElementById('dangerAlert').classList.add('active');
            document.getElementById('noAlert').style.display = 'none';
            document.getElementById('alertMessage').textContent = dangerAlerts[0].message;
            
            // Show notification
            showNotification(dangerAlerts[0].message);
        } else {
            document.getElementById('dangerAlert').classList.remove('active');
            document.getElementById('noAlert').style.display = 'block';
        }
    });
}

function showNotification(message) {
    const notif = document.getElementById('notification');
    document.getElementById('notification-text').textContent = message;
    notif.classList.add('show');
    
    setTimeout(() => {
        notif.classList.remove('show');
    }, 5000);
}

// Green Routes
function switchTab(tab) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    event.target.closest('.nav-tab').classList.add('active');
    
    // Show/hide panels based on tab
    if (tab === 'routes') {
        document.getElementById('routesPanel').style.display = 'block';
        document.getElementById('zonePanel').style.display = 'none';
        document.getElementById('forecastPanel').style.display = 'none';
    } else {
        document.getElementById('routesPanel').style.display = 'none';
        document.getElementById('zonePanel').style.display = 'block';
        if (tab === 'forecast') {
            document.getElementById('forecastPanel').style.display = 'block';
        }
    }
}

function planGreenRoute() {
    const start = document.getElementById('startLoc').value;
    const end = document.getElementById('endLoc').value;
    
    // Mock coordinates for demo (in real app, use geocoding)
    const startCoords = { lat: 25.2677, lng: 82.9913 }; // IIT BHU
    const endCoords = { lat: 25.3100, lng: 83.0100 };   // Godaulia
    
    fetch(`/api/green-corridors?start_lat=${startCoords.lat}&start_lng=${startCoords.lng}&end_lat=${endCoords.lat}&end_lng=${endCoords.lng}`)
        .then(res => res.json())
        .then(data => {
            const results = document.getElementById('routeResults');
            results.innerHTML = `
                <div style="background: rgba(39, 174, 96, 0.1); border: 1px solid var(--success); border-radius: 8px; padding: 15px;">
                    <div style="color: var(--success); font-weight: bold; margin-bottom: 10px;">
                        <i class="fas fa-check-circle"></i> ${data.route_type}
                    </div>
                    <div style="font-size: 0.9rem; color: #aaa; margin-bottom: 10px;">
                        Via: ${data.recommended_waypoints.map(w => w.name).join(' → ')}
                    </div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        ${data.recommended_waypoints.map(w => `
                            <span style="background: ${getColorForPM25(w.pm25)}30; color: ${getColorForPM25(w.pm25)}; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem;">
                                ${w.name}: ${w.pm25}
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
            
            // Draw route on map (simplified)
            const latlngs = data.recommended_waypoints.map(w => [w.lat, w.lng]);
            L.polyline(latlngs, { color: '#27ae60', weight: 4, opacity: 0.8 }).addTo(map);
        });
}

function subscribeAlert(zoneId) {
    fetch('/api/alerts/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zone_id: zoneId, user_id: 'user_001', alert_type: 'threshold' })
    })
    .then(res => res.json())
    .then(data => {
        alert('✅ Alert subscription activated!');
    });
}

function locateUser() {
    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(pos => {
            map.setView([pos.coords.latitude, pos.coords.longitude], 15);
        });
    }
}

function findSafeRoute() {
    switchTab('routes');
    document.getElementById('routesPanel').scrollIntoView({ behavior: 'smooth' });
}

// Auto-refresh every 5 minutes
setInterval(loadZones, 300000);