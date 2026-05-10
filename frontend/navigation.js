/**
 * navigation.js — Leaflet + OpenStreetMap, OSRM routing, Nominatim geocoding
 * No API key required.
 */

import { speak } from "./voice.js";
import { sendCommand } from "./camera.js";

let _map            = null;
let _routeLayer     = null;
let _userMarker     = null;
let _currentSteps   = [];
let _positionWatchId   = null;
let _guidanceIntervalId = null;
let _currentPosition   = null;

// ── Map init ──────────────────────────────────────────────────────────────────

export async function initMaps() {
  await _loadLeaflet();
  _setupMap();
  loadSavedRoutes();
}

export function invalidateMap() {
  if (_map) _map.invalidateSize();
}

function _loadLeaflet() {
  return new Promise((resolve) => {
    if (window.L) { resolve(); return; }

    const link = document.createElement("link");
    link.rel  = "stylesheet";
    link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(link);

    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.onload = resolve;
    document.head.appendChild(script);
  });
}

function _setupMap() {
  const container = document.getElementById("map-container");
  // Leaflet needs explicit height
  container.style.height = "240px";

  _map = L.map(container, { zoomControl: false, attributionControl: false })
           .setView([28.6139, 77.2090], 17);   // default: New Delhi

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
  }).addTo(_map);

  // Pan to real location
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        _currentPosition = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        _map.setView([_currentPosition.lat, _currentPosition.lng], 17);
        _updateUserMarker();
        const instr = document.getElementById("nav-instruction");
        if (instr && instr.textContent.includes("GPS")) {
          instr.textContent = "GPS found. Type a destination and tap Go.";
        }
        const gpsLabel = document.getElementById("gps-label");
        if (gpsLabel) gpsLabel.textContent = "GPS ✓";
      },
      (err) => {
        const instr = document.getElementById("nav-instruction");
        if (instr) instr.textContent = "GPS denied. Enable location permission and refresh.";
        const gpsLabel = document.getElementById("gps-label");
        if (gpsLabel) gpsLabel.textContent = "No GPS";
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  } else {
    const instr = document.getElementById("nav-instruction");
    if (instr) instr.textContent = "Geolocation not supported in this browser.";
  }
}

function _updateUserMarker() {
  if (!_currentPosition || !_map) return;
  const latlng = [_currentPosition.lat, _currentPosition.lng];
  if (_userMarker) {
    _userMarker.setLatLng(latlng);
  } else {
    _userMarker = L.circleMarker(latlng, {
      radius: 8, color: "#4fc3f7", fillColor: "#4fc3f7", fillOpacity: 1,
    }).addTo(_map);
  }
}

// ── Route navigation ──────────────────────────────────────────────────────────

export async function navigateTo(destination) {
  if (!_currentPosition) {
    speak("Waiting for your GPS location. Please try again in a moment.");
    return;
  }

  speak(`Finding a walking route to ${destination}.`);

  const res = await fetch("/navigate/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin_lat: _currentPosition.lat,
      origin_lng: _currentPosition.lng,
      destination,
    }),
  });

  if (!res.ok) {
    speak("Sorry, I could not find a route to that destination.");
    return;
  }

  const data = await res.json();
  if (data.error) {
    speak(`Route error: ${data.error}`);
    return;
  }

  _currentSteps = data.steps;

  speak(
    `Route found. ${data.total_distance}, about ${data.total_duration} on foot. ` +
    `First instruction: ${data.steps[0]?.instruction || "Head to your destination."}`
  );

  // Draw polyline from GeoJSON geometry returned by OSRM
  if (_map && data.geometry) {
    if (_routeLayer) _map.removeLayer(_routeLayer);
    const coords = data.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
    _routeLayer = L.polyline(coords, { color: "#4fc3f7", weight: 5 }).addTo(_map);
    _map.fitBounds(_routeLayer.getBounds(), { padding: [30, 30] });
  }

  document.getElementById("nav-instruction").textContent =
    data.steps[0]?.instruction || "";
  _startGPSGuidance();

  // Auto-save route
  _saveRoute(destination, data);
}

function _startGPSGuidance() {
  clearInterval(_guidanceIntervalId);
  if (_positionWatchId) navigator.geolocation.clearWatch(_positionWatchId);

  _positionWatchId = navigator.geolocation.watchPosition(
    (pos) => {
      _currentPosition = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      if (_map) _map.setView([_currentPosition.lat, _currentPosition.lng]);
      _updateUserMarker();
    },
    null,
    { enableHighAccuracy: true }
  );

  // Poll guidance every 10 seconds
  _guidanceIntervalId = setInterval(async () => {
    if (!_currentPosition || !_currentSteps.length) return;

    const res = await fetch("/navigate/position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat:   _currentPosition.lat,
        lng:   _currentPosition.lng,
        steps: _currentSteps,
      }),
    });

    if (!res.ok) return;
    const data = await res.json();
    speak(data.guidance);
    document.getElementById("nav-instruction").textContent = data.guidance;

    if (data.guidance.includes("arrived")) {
      clearInterval(_guidanceIntervalId);
      navigator.geolocation.clearWatch(_positionWatchId);
    }
  }, 10_000);
}

async function _saveRoute(destination, routeData) {
  if (!_currentPosition || !routeData.end_lat) return;
  await fetch("/navigate/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name:             destination,
      destination_name: destination,
      start_lat: _currentPosition.lat,
      start_lng: _currentPosition.lng,
      end_lat:   routeData.end_lat,
      end_lng:   routeData.end_lng,
    }),
  });
}

// ── Saved routes ──────────────────────────────────────────────────────────────

export async function loadSavedRoutes() {
  const res = await fetch("/navigate/saved");
  if (!res.ok) return;
  const routes = await res.json();

  const container = document.getElementById("saved-routes");
  if (!container) return;
  container.innerHTML = "<p class='section-label'>Saved routes</p>";

  routes.forEach((route) => {
    const btn = document.createElement("button");
    btn.className   = "route-btn";
    btn.textContent = `${route.destination_name} (used ${route.use_count}x)`;
    btn.onclick     = () => navigateTo(route.destination_name);
    container.appendChild(btn);
  });
}

// ── POI search ────────────────────────────────────────────────────────────────

export async function findPOI(category) {
  if (!_currentPosition) {
    speak("I need your GPS location first. Please wait a moment.");
    return;
  }

  const params = new URLSearchParams({
    lat:      _currentPosition.lat,
    lng:      _currentPosition.lng,
    category,
  });

  const res = await fetch(`/poi/nearby?${params}`);
  if (!res.ok) { speak("Could not search for nearby places."); return; }

  const data = await res.json();
  speak(data.speech);
}

// ── Expose to window so voice.js can call them ────────────────────────────────
window.navigateTo  = navigateTo;
window.findPOI     = findPOI;
window.sendCommand = sendCommand;
