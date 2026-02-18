from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import sqlite3
import json
import math
import numpy as np
from datetime import datetime, timedelta
import random
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import pickle
import os

app = Flask(__name__)
CORS(app)

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Enhanced zones table with sensor locations
    c.execute('''CREATE TABLE IF NOT EXISTS zones
                 (id INTEGER PRIMARY KEY, name TEXT, lat REAL, lng REAL, 
                  traffic_density REAL, construction_activity REAL, 
                  population_density REAL, has_sensor BOOLEAN DEFAULT 0,
                  pm25_value REAL, base_risk REAL)''')
    
    # Historical data for ML training
    c.execute('''CREATE TABLE IF NOT EXISTS air_quality_history
                 (id INTEGER PRIMARY KEY, zone_id INTEGER, timestamp TEXT,
                  pm25 REAL, traffic_index REAL, weather_index REAL,
                  wind_speed REAL, humidity REAL, temperature REAL)''')
    
    # User alerts
    c.execute('''CREATE TABLE IF NOT EXISTS user_alerts
                 (id INTEGER PRIMARY KEY, user_id TEXT, zone_id INTEGER,
                  alert_type TEXT, timestamp TEXT, is_active BOOLEAN DEFAULT 1)''')
    
    # Weather cache
    c.execute('''CREATE TABLE IF NOT EXISTS weather_forecast
                 (id INTEGER PRIMARY KEY, timestamp TEXT, hour INTEGER,
                  wind_speed REAL, humidity REAL, temperature REAL,
                  precipitation REAL)''')
    
    conn.commit()
    conn.close()

# ==================== SAMPLE DATA ====================
def init_zones():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM zones")
    if c.fetchone()[0] == 0:
        # Realistic zones with some having sensors (ground truth)
        zones = [
            # (name, lat, lng, traffic, construction, population, has_sensor, pm25)
            ("IIT BHU Main Gate", 25.2677, 82.9913, 0.9, 0.2, 0.8, 1, 85),
            ("Lanka Chowk", 25.2800, 83.0000, 0.95, 0.3, 0.9, 1, 120),
            ("Godaulia", 25.3100, 83.0100, 0.8, 0.1, 0.95, 0, None),
            ("Assi Ghat", 25.2700, 83.0060, 0.6, 0.0, 0.7, 1, 65),
            ("Varanasi Jn", 25.3250, 82.9850, 0.9, 0.1, 0.95, 0, None),
            ("BHU Campus", 25.2670, 82.9950, 0.3, 0.1, 0.6, 1, 45),
            ("Mahmoorganj", 25.2900, 82.9800, 0.7, 0.4, 0.8, 0, None),
            ("Sigra", 25.3150, 82.9950, 0.85, 0.2, 0.9, 0, None),
            ("Pandeypur", 25.3400, 82.9900, 0.6, 0.5, 0.7, 0, None),
            ("Cantt Railway", 25.3350, 82.9700, 0.75, 0.1, 0.85, 1, 95),
        ]
        
        for zone in zones:
            base_risk = calculate_base_risk(zone[3], zone[4], zone[5])
            c.execute('''INSERT INTO zones 
                        (name, lat, lng, traffic_density, construction_activity, 
                         population_density, has_sensor, pm25_value, base_risk)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (zone[0], zone[1], zone[2], zone[3], zone[4], zone[5], 
                      zone[6], zone[7], base_risk))
        
        # Generate 30 days of historical data for ML
        generate_historical_data(c)
    
    conn.commit()
    conn.close()

def generate_historical_data(cursor):
    """Generate synthetic historical data for ML training"""
    zones = cursor.execute("SELECT id, traffic_density, construction_activity FROM zones").fetchall()
    
    for zone_id, traffic, construction in zones:
        base_pm25 = 50 + (traffic * 100) + (construction * 50)
        
        for day in range(30):
            for hour in range(24):
                timestamp = (datetime.now() - timedelta(days=day, hours=hour)).strftime('%Y-%m-%d %H:%M:%S')
                
                # Time patterns
                if 7 <= hour <= 9 or 17 <= hour <= 19:
                    time_multiplier = 1.4
                elif 10 <= hour <= 16:
                    time_multiplier = 1.1
                else:
                    time_multiplier = 0.8
                
                # Weather simulation
                wind = random.uniform(2, 20)
                humidity = random.uniform(30, 90)
                temp = random.uniform(15, 40)
                
                wind_factor = max(0.3, 1 - (wind / 25))
                humidity_factor = 0.7 + (humidity / 300)
                
                pm25 = base_pm25 * time_multiplier * wind_factor * humidity_factor
                pm25 += random.uniform(-10, 10)  # Noise
                
                cursor.execute('''INSERT INTO air_quality_history 
                                (zone_id, timestamp, pm25, traffic_index, weather_index,
                                 wind_speed, humidity, temperature)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                             (zone_id, timestamp, max(10, pm25), traffic, wind_factor,
                              wind, humidity, temp))

def calculate_base_risk(traffic, construction, population):
    """Calculate base risk score (0-100)"""
    risk = (traffic * 0.35 + construction * 0.25 + population * 0.25) * 100
    return min(100, max(0, risk))

# ==================== INVERSE DISTANCE WEIGHTING ====================
class IDWInterpolator:
    """Spatial interpolation using Inverse Distance Weighting"""
    
    def __init__(self, power=2):
        self.power = power
    
    def interpolate(self, target_lat, target_lng, known_points):
        """
        known_points: list of (lat, lng, value)
        Returns interpolated value
        """
        if not known_points:
            return None
        
        weights = []
        values = []
        
        for lat, lng, value in known_points:
            dist = self.haversine_distance(target_lat, target_lng, lat, lng)
            if dist == 0:
                return value  # Exact match
            
            weight = 1 / (dist ** self.power)
            weights.append(weight)
            values.append(value)
        
        # Weighted average
        interpolated = sum(w * v for w, v in zip(weights, values)) / sum(weights)
        return interpolated
    
    @staticmethod
    def haversine_distance(lat1, lon1, lat2, lon2):
        """Calculate distance in km between two points"""
        R = 6371  # Earth's radius in km
        
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c

# ==================== ML PREDICTOR ====================
class AirQualityPredictor:
    """Random Forest predictor for 24-hour forecasting"""
    
    def __init__(self):
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
    
    def train(self, conn):
        """Train model on historical data"""
        c = conn.cursor()
        c.execute('''SELECT pm25, traffic_index, weather_index, 
                     wind_speed, humidity, temperature,
                     strftime('%H', timestamp) as hour
                     FROM air_quality_history''')
        data = c.fetchall()
        
        if len(data) < 100:
            return False
        
        X = np.array([[d[1], d[2], d[3], d[4], d[5], int(d[6])] for d in data])
        y = np.array([d[0] for d in data])
        
        self.scaler.fit(X)
        X_scaled = self.scaler.transform(X)
        
        self.model.fit(X_scaled, y)
        self.is_trained = True
        return True
    
    def predict(self, traffic, weather, wind, humidity, temp, hour):
        """Predict PM2.5 for given conditions"""
        if not self.is_trained:
            return None
        
        X = np.array([[traffic, weather, wind, humidity, temp, hour]])
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)[0]

# Global predictor instance
predictor = AirQualityPredictor()

# ==================== RISK CALCULATION ====================
def get_weather_factor():
    """Get current weather conditions"""
    wind_speed = random.uniform(3, 18)
    humidity = random.uniform(35, 85)
    temp = random.uniform(20, 38)
    
    # Wind disperses pollution
    wind_factor = max(0.3, 1 - (wind_speed / 25))
    # Humidity traps pollution
    humidity_factor = 0.6 + (humidity / 250)
    
    weather_impact = (wind_factor * 0.6 + humidity_factor * 0.4)
    
    return {
        'wind_speed': round(wind_speed, 1),
        'humidity': round(humidity, 1),
        'temperature': round(temp, 1),
        'weather_factor': round(weather_impact, 2)
    }

def calculate_pm25(traffic, construction, population, weather_data, time_factor=1.0):
    """Calculate PM2.5 based on factors"""
    base_pm25 = 30  # Background level
    
    # Contribution from each factor
    traffic_pm25 = traffic * 80 * time_factor
    construction_pm25 = construction * 40
    population_pm25 = population * 30
    
    # Weather impact
    weather_multiplier = weather_data['weather_factor']
    
    total_pm25 = (base_pm25 + traffic_pm25 + construction_pm25 + population_pm25) * weather_multiplier
    return round(max(10, min(500, total_pm25)), 1)

def get_aqi_category(pm25):
    """Get AQI category from PM2.5"""
    if pm25 <= 30:
        return 'Good', '#4CAF50', 1
    elif pm25 <= 60:
        return 'Satisfactory', '#8BC34A', 2
    elif pm25 <= 90:
        return 'Moderate', '#FFC107', 3
    elif pm25 <= 120:
        return 'Poor', '#FF9800', 4
    elif pm25 <= 250:
        return 'Very Poor', '#F44336', 5
    else:
        return 'Severe', '#9C27B0', 6

# ==================== API ROUTES ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/zones')
def get_zones():
    """Get all zones with interpolated values"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Get zones with sensors (ground truth)
    c.execute("SELECT id, name, lat, lng, has_sensor, pm25_value, traffic_density, construction_activity, population_density FROM zones")
    all_zones = c.fetchall()
    
    # Separate sensor and non-sensor zones
    sensor_zones = [(z[2], z[3], z[5]) for z in all_zones if z[4] == 1 and z[5] is not None]
    
    # IDW Interpolator
    idw = IDWInterpolator(power=2)
    weather = get_weather_factor()
    
    zones_data = []
    for zone in all_zones:
        zone_id, name, lat, lng, has_sensor, pm25_sensor, traffic, construction, population = zone
        
        if has_sensor and pm25_sensor:
            pm25 = pm25_sensor
            data_source = "Sensor"
        else:
            # Interpolate using IDW
            interpolated = idw.interpolate(lat, lng, sensor_zones)
            if interpolated:
                pm25 = interpolated
                data_source = "IDW Interpolated"
            else:
                # Fallback to model
                pm25 = calculate_pm25(traffic, construction, population, weather)
                data_source = "Model Predicted"
        
        aqi_cat, color, aqi_level = get_aqi_category(pm25)
        
        # Calculate risk score (0-100)
        risk_score = min(100, (pm25 / 300) * 100)
        
        zones_data.append({
            'id': zone_id,
            'name': name,
            'lat': lat,
            'lng': lng,
            'pm25': round(pm25, 1),
            'aqi_category': aqi_cat,
            'aqi_color': color,
            'aqi_level': aqi_level,
            'risk_score': round(risk_score, 1),
            'data_source': data_source,
            'has_sensor': bool(has_sensor),
            'factors': {
                'traffic': traffic,
                'construction': construction,
                'population': population,
                'weather': weather
            }
        })
    
    conn.close()
    return jsonify(zones_data)

@app.route('/api/forecast/<int:zone_id>')
def get_forecast(zone_id):
    """Get 24-hour forecast for a zone"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT traffic_density, construction_activity, population_density FROM zones WHERE id = ?", (zone_id,))
    zone = c.fetchone()
    
    if not zone:
        return jsonify({'error': 'Zone not found'}), 404
    
    traffic, construction, population = zone
    
    # Train predictor if not trained
    if not predictor.is_trained:
        predictor.train(conn)
    
    # Generate 24-hour forecast
    forecast = []
    current_time = datetime.now()
    
    for i in range(24):
        future_time = current_time + timedelta(hours=i)
        hour = future_time.hour
        
        # Time factor
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            time_factor = 1.4
        elif 10 <= hour <= 16:
            time_factor = 1.1
        else:
            time_factor = 0.8
        
        # Simulated future weather (in real app, use weather API)
        wind = random.uniform(3, 20)
        humidity = random.uniform(30, 90)
        temp = random.uniform(18, 40)
        weather_factor = max(0.3, 1 - (wind / 25))
        
        # Predict using ML if available, else use formula
        if predictor.is_trained:
            pm25 = predictor.predict(traffic, weather_factor, wind, humidity, temp, hour)
            pm25 = pm25 * time_factor if pm25 else calculate_pm25(traffic, construction, population, 
                                                                  {'weather_factor': weather_factor}, time_factor)
        else:
            pm25 = calculate_pm25(traffic, construction, population, 
                                 {'weather_factor': weather_factor}, time_factor)
        
        aqi_cat, color, level = get_aqi_category(pm25)
        
        forecast.append({
            'hour': future_time.strftime('%H:00'),
            'datetime': future_time.isoformat(),
            'pm25': round(pm25, 1),
            'aqi_category': aqi_cat,
            'aqi_color': color,
            'wind_speed': round(wind, 1),
            'humidity': round(humidity, 1)
        })
    
    conn.close()
    return jsonify({
        'zone_id': zone_id,
        'forecast': forecast,
        'peak_pollution': max(forecast, key=lambda x: x['pm25']),
        'safe_hours': [f for f in forecast if f['aqi_level'] <= 2] if 'aqi_level' in forecast[0] else []
    })

@app.route('/api/green-corridors')
def get_green_corridors():
    """Find safest routes between points"""
    start_lat = request.args.get('start_lat', type=float)
    start_lng = request.args.get('start_lng', type=float)
    end_lat = request.args.get('end_lat', type=float)
    end_lng = request.args.get('end_lng', type=float)
    
    if not all([start_lat, start_lng, end_lat, end_lng]):
        return jsonify({'error': 'Missing coordinates'}), 400
    
    # Get current zone data
    zones_data = get_zones().get_json()
    
    # Simple algorithm: Find waypoints with lowest PM2.5
    # In real app, use proper routing algorithm (A*, Dijkstra)
    
    # Sort zones by PM2.5 (lowest first)
    safe_zones = sorted(zones_data, key=lambda x: x['pm25'])
    
    # Find zones near the route (simplified)
    route_zones = []
    for zone in safe_zones[:3]:  # Top 3 safest
        route_zones.append({
            'name': zone['name'],
            'lat': zone['lat'],
            'lng': zone['lng'],
            'pm25': zone['pm25'],
            'aqi': zone['aqi_category']
        })
    
    return jsonify({
        'start': {'lat': start_lat, 'lng': start_lng},
        'end': {'lat': end_lat, 'lng': end_lng},
        'recommended_waypoints': route_zones,
        'route_type': 'Green Corridor - Low Pollution'
    })

@app.route('/api/alerts/subscribe', methods=['POST'])
def subscribe_alert():
    """Subscribe to zone alerts"""
    data = request.json
    user_id = data.get('user_id', 'anonymous')
    zone_id = data.get('zone_id')
    alert_type = data.get('alert_type', 'enter')  # 'enter' or 'threshold'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute('''INSERT INTO user_alerts (user_id, zone_id, alert_type, timestamp)
                 VALUES (?, ?, ?, ?)''',
              (user_id, zone_id, alert_type, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'subscribed', 'message': f'Alert set for zone {zone_id}'})

@app.route('/api/check-alerts', methods=['POST'])
def check_alerts():
    """Check if user is entering danger zone"""
    data = request.json
    user_lat = data.get('lat')
    user_lng = data.get('lng')
    user_id = data.get('user_id', 'anonymous')
    
    if not user_lat or not user_lng:
        return jsonify({'error': 'Location required'}), 400
    
    # Get zones
    zones_data = get_zones().get_json()
    
    alerts = []
    for zone in zones_data:
        # Calculate distance (simplified)
        dist = IDWInterpolator.haversine_distance(user_lat, user_lng, zone['lat'], zone['lng'])
        
        if dist < 0.5:  # Within 500m
            if zone['aqi_level'] >= 4:  # Poor or worse
                alerts.append({
                    'type': 'danger_zone',
                    'zone_name': zone['name'],
                    'distance_km': round(dist, 2),
                    'pm25': zone['pm25'],
                    'aqi': zone['aqi_category'],
                    'message': f'⚠️ WARNING: You are entering {zone["name"]} with {zone["aqi_category"]} air quality (PM2.5: {zone["pm25"]})',
                    'recommendation': 'Consider alternative route or wear mask'
                })
            elif zone['aqi_level'] <= 2:
                alerts.append({
                    'type': 'safe_zone',
                    'zone_name': zone['name'],
                    'distance_km': round(dist, 2),
                    'pm25': zone['pm25'],
                    'message': f'✅ {zone["name"]} has {zone["aqi_category"]} air quality'
                })
    
    return jsonify({
        'user_location': {'lat': user_lat, 'lng': user_lng},
        'alerts': alerts,
        'timestamp': datetime.now().isoformat()
    })

# ==================== INITIALIZATION ====================
if __name__ == '__main__':
    init_db()
    init_zones()
    
    # Train ML model on startup
    conn = sqlite3.connect('database.db')
    predictor.train(conn)
    conn.close()
    
    print("🚀 BreathGuard server starting...")
    print("📊 ML Model trained and ready")
    print("🗺️  IDW Interpolator active")
    app.run(debug=True, host='0.0.0.0', port=5000)