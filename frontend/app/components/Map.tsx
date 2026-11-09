"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";

import "maplibre-gl/dist/maplibre-gl.css";
import type { LiveRoute, LngLat } from "../lib/routing";

type MapProps = {
  routes: LiveRoute[];
  selectedRoute: number;
  onUserLocation?: (pos: LngLat) => void;
  /** Pin chosen by tapping/dragging on the map */
  destination?: LngLat | null;
  onPickDestination?: (pos: LngLat) => void;
  onCenterChange?: (pos: LngLat) => void;
  /** Turn-by-turn mode: camera follows the active step */
  navigating?: boolean;
  activeStep?: number;
};

export default function Map({
  routes,
  selectedRoute,
  onUserLocation,
  destination,
  onPickDestination,
  onCenterChange,
  navigating = false,
  activeStep = 0,
}: MapProps) {
  const navRef = useRef(navigating);
  navRef.current = navigating;
  const destMarker = useRef<maplibregl.Marker | null>(null);
  const pickRef = useRef(onPickDestination);
  pickRef.current = onPickDestination;
  const centerRef = useRef(onCenterChange);
  centerRef.current = onCenterChange;
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const loaded = useRef(false);
  const markers = useRef<maplibregl.Marker[]>([]);
  const onLocRef = useRef(onUserLocation);
  onLocRef.current = onUserLocation;

  /* Create the map once */
  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    const newMap = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [75.7873, 26.9124],
      zoom: 12,
    });
    map.current = newMap;

    newMap.addControl(new maplibregl.NavigationControl(), "top-right");

    // Live location tracking (blue dot that follows the user)
    const geolocate = new maplibregl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true,
      showAccuracyCircle: true,
    });
    newMap.addControl(geolocate, "top-right");
    geolocate.on("geolocate", (e: GeolocationPosition) => {
      onLocRef.current?.([e.coords.longitude, e.coords.latitude]);
    });

    // Tap/click anywhere to set the destination pin
    newMap.getCanvas().style.cursor = "crosshair";
    newMap.on("click", (e) => {
      pickRef.current?.([e.lngLat.lng, e.lngLat.lat]);
    });
    newMap.on("moveend", () => {
      const c = newMap.getCenter();
      centerRef.current?.([c.lng, c.lat]);
    });

    newMap.on("load", () => {
      loaded.current = true;
      newMap.resize();
      // Start tracking automatically if the browser allows it
      if ("geolocation" in navigator) geolocate.trigger();
      newMap.fire("routes-ready");
    });

    return () => {
      newMap.remove();
      map.current = null;
      loaded.current = false;
    };
  }, []);

  /* Draggable destination pin */
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (!destination) {
      destMarker.current?.remove();
      destMarker.current = null;
      return;
    }
    if (!destMarker.current) {
      const mk = new maplibregl.Marker({ color: "#dc2626", draggable: true })
        .setLngLat(destination)
        .addTo(m);
      mk.on("dragend", () => {
        const p = mk.getLngLat();
        pickRef.current?.([p.lng, p.lat]);
      });
      destMarker.current = mk;
    } else {
      destMarker.current.setLngLat(destination);
    }
  }, [destination]);

  /* Draw routes whenever they or the selection change */
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    const draw = () => {
      // clear previous
      markers.current.forEach((mk) => mk.remove());
      markers.current = [];
      for (let i = 0; i < 3; i++) {
        if (m.getLayer(`route-${i}`)) m.removeLayer(`route-${i}`);
        if (m.getSource(`route-${i}`)) m.removeSource(`route-${i}`);
      }
      if (!routes.length) return;

      // draw unselected first so selected ends on top
      const order = routes.map((_, i) => i).sort((a) => (a === selectedRoute ? 1 : -1));
      for (const i of order) {
        const r = routes[i];
        const sel = i === selectedRoute;
        m.addSource(`route-${i}`, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: {},
            geometry: { type: "LineString", coordinates: r.geometry },
          },
        });
        m.addLayer({
          id: `route-${i}`,
          type: "line",
          source: `route-${i}`,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": r.color,
            "line-width": sel ? 7 : 4,
            "line-opacity": sel ? 0.95 : 0.45,
          },
        });
      }

      const geom = routes[selectedRoute]?.geometry ?? routes[0].geometry;
      // start pin (the destination pin is the draggable one above)
      markers.current.push(
        new maplibregl.Marker({ color: "#16a34a" }).setLngLat(geom[0]).addTo(m)
      );

      const bounds = geom.reduce(
        (b, c) => b.extend(c),
        new maplibregl.LngLatBounds(geom[0], geom[0])
      );
      if (!navRef.current) m.fitBounds(bounds, { padding: 60, duration: 800 });
    };

    if (loaded.current) draw();
    else m.once("routes-ready", draw);
  }, [routes, selectedRoute]);

  /* Turn-by-turn: maneuver dots + camera that follows the active step */
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      if (m.getLayer("nav-steps")) m.removeLayer("nav-steps");
      if (m.getSource("nav-steps")) m.removeSource("nav-steps");
      const route = routes[selectedRoute];
      if (!navigating || !route?.steps?.length) {
        m.easeTo({ pitch: 0, bearing: 0, duration: 600 });
        return;
      }
      m.addSource("nav-steps", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: route.steps.map((st, i) => ({
            type: "Feature",
            properties: { active: i === activeStep ? 1 : 0, done: i < activeStep ? 1 : 0 },
            geometry: { type: "Point", coordinates: st.location },
          })),
        },
      });
      m.addLayer({
        id: "nav-steps",
        type: "circle",
        source: "nav-steps",
        paint: {
          "circle-radius": ["case", ["==", ["get", "active"], 1], 9, 5],
          "circle-color": [
            "case",
            ["==", ["get", "active"], 1], "#2563eb",
            ["==", ["get", "done"], 1], "#9ca3af",
            "#ffffff",
          ],
          "circle-stroke-color": "#15803d",
          "circle-stroke-width": 2.5,
        },
      });
      const st = route.steps[activeStep] ?? route.steps[0];
      m.flyTo({ center: st.location, zoom: 17.5, pitch: 55, bearing: st.bearing, duration: 1000 });
    };
    if (loaded.current) apply();
    else m.once("routes-ready", apply);
  }, [navigating, activeStep, routes, selectedRoute]);

  return (
    <div
      ref={mapContainer}
      style={{ width: "100%", height: "600px" }}
    />
  );
}
