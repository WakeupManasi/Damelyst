import type { Route } from "../data/demoRoutes";

export type LngLat = [number, number];

const ROUTE_COLORS = ["#16a34a", "#2563eb", "#f59e0b"];

export type Place = { label: string; detail: string; coord: LngLat };

/**
 * Search places (shops, chowks, landmarks, streets) with Photon, an
 * OpenStreetMap search tuned for points of interest. Results are biased
 * toward `near` (user location or map centre) so small local places rank first.
 */
export async function searchPlaces(query: string, near?: LngLat): Promise<Place[]> {
  if (query.trim().length < 2) return [];
  let url =
    "https://photon.komoot.io/api/?limit=6&q=" + encodeURIComponent(query);
  if (near) url += `&lon=${near[0]}&lat=${near[1]}&location_bias_scale=0.5`;
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    type F = {
      geometry: { coordinates: LngLat };
      properties: Record<string, string | undefined>;
    };
    const seen = new Set<string>();
    return (data.features as F[]).map((f) => {
      const p = f.properties;
      const label = p.name || [p.housenumber, p.street].filter(Boolean).join(" ") || "Unnamed place";
      const detail = [p.street !== label ? p.street : undefined, p.district, p.city || p.county, p.state]
        .filter(Boolean)
        .join(", ");
      return { label, detail, coord: f.geometry.coordinates };
    }).filter((p) => {
      const k = `${p.label}|${p.detail}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  } catch {
    return [];
  }
}

/** Geocode free text: try Photon (good with shops/chowks), then Nominatim. */
export async function geocode(query: string, near?: LngLat): Promise<LngLat> {
  const hits = await searchPlaces(query, near);
  if (hits.length) return hits[0].coord;
  return nominatim(query);
}

async function nominatim(query: string): Promise<LngLat> {
  const url =
    "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" +
    encodeURIComponent(query);
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error("Location search failed. Try again.");
  const data = (await res.json()) as { lat: string; lon: string }[];
  if (!data.length) throw new Error(`Could not find "${query}".`);
  return [parseFloat(data[0].lon), parseFloat(data[0].lat)];
}

/** Reverse geocode coordinates to a short readable name. */
export async function reverseGeocode([lng, lat]: LngLat): Promise<string> {
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&zoom=16&lat=${lat}&lon=${lng}`
    );
    const data = await res.json();
    return (data.display_name as string)?.split(",").slice(0, 2).join(",") ??
      `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  } catch {
    return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  }
}

type OsrmStep = {
  name: string;
  ref?: string;
  distance: number;
  duration: number;
  maneuver: { type: string; modifier?: string; location: LngLat; bearing_after?: number };
};

export type NavStep = {
  instruction: string;
  /** distance to walk after this maneuver, metres */
  distance: number;
  location: LngLat;
  type: string;
  modifier?: string;
  bearing: number;
};

function instructionFor(s: OsrmStep): string {
  const road = s.name || s.ref || "";
  const onto = road ? ` onto ${road}` : "";
  const mod = s.maneuver.modifier ?? "";
  switch (s.maneuver.type) {
    case "depart":
      return `Head ${bearingWord(s.maneuver.bearing_after ?? 0)}${road ? ` on ${road}` : ""}`;
    case "arrive":
      return "You have arrived at your destination";
    case "roundabout":
    case "rotary":
      return `Enter the roundabout and exit${onto}`;
    case "continue":
    case "new name":
      return `Continue${road ? ` on ${road}` : " straight"}`;
    default:
      if (!mod || mod === "straight") return `Go straight${onto}`;
      if (mod === "uturn") return `Make a U-turn${onto}`;
      return `${mod.startsWith("slight") ? "Bear" : "Turn"} ${mod.replace("slight ", "").replace("sharp ", "sharp ")}${onto}`;
  }
}

function bearingWord(b: number): string {
  return ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"][
    Math.round(b / 45) % 8
  ];
}

export function formatDist(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.max(5, Math.round(m / 5) * 5)} m`;
}

/** Haversine distance in metres. */
export function distanceM(a: LngLat, b: LngLat): number {
  const R = 6371000, r = Math.PI / 180;
  const dLat = (b[1] - a[1]) * r, dLng = (b[0] - a[0]) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
type OsrmRoute = {
  distance: number;
  duration: number;
  geometry: { coordinates: LngLat[] };
  legs: { steps: OsrmStep[] }[];
};

export type LiveRoute = Route & { geometry: LngLat[]; steps: NavStep[] };

/**
 * Fetch walking routes (with alternatives) from the public OSRM server.
 * Safety numbers are an ESTIMATE: share of the route on named / major
 * roads, which tend to be better lit and busier than unnamed paths.
 */
export async function fetchRoutes(from: LngLat, to: LngLat): Promise<LiveRoute[]> {
  const url =
    `https://routing.openstreetmap.de/routed-foot/route/v1/foot/` +
    `${from[0]},${from[1]};${to[0]},${to[1]}` +
    `?alternatives=3&overview=full&geometries=geojson&steps=true`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Routing service unavailable. Try again.");
  const data = (await res.json()) as { code: string; routes: OsrmRoute[] };
  if (data.code !== "Ok" || !data.routes.length) {
    throw new Error("No route found between these places.");
  }

  const routes = data.routes.slice(0, 3).map((r, i) => {
    const steps = r.legs.flatMap((l) => l.steps);
    const total = steps.reduce((s, x) => s + x.distance, 0) || 1;
    const major = steps.filter((s) => s.ref).reduce((s, x) => s + x.distance, 0) / total;
    const named = steps.filter((s) => s.name).reduce((s, x) => s + x.distance, 0) / total;

    const lighting = Math.round(45 + 35 * named + 20 * major);
    const safetyScore = Math.min(98, Math.round(50 + 30 * named + 18 * major));
    const crowdLevel = major > 0.4 ? "High" : named > 0.6 ? "Medium" : "Low";
    const mainRoad = steps
      .filter((s) => s.name)
      .sort((a, b) => b.distance - a.distance)[0]?.name;

    return {
      id: i + 1,
      name: mainRoad ? `Via ${mainRoad}` : `Route ${i + 1}`,
      distance: `${(r.distance / 1000).toFixed(1)} km`,
      duration: `${Math.max(1, Math.round(r.duration / 60))} min walk`,
      safetyScore,
      lighting: Math.min(100, lighting),
      crowdLevel,
      description: `${Math.round(named * 100)}% on named streets (estimated safety).`,
      color: ROUTE_COLORS[i],
      geometry: r.geometry.coordinates,
      steps: steps.map((s) => ({
        instruction: instructionFor(s),
        distance: s.distance,
        location: s.maneuver.location,
        type: s.maneuver.type,
        modifier: s.maneuver.modifier,
        bearing: s.maneuver.bearing_after ?? 0,
      })),
    };
  });

  return routes.sort((a, b) => b.safetyScore - a.safetyScore)
    .map((r, i) => ({ ...r, color: ROUTE_COLORS[i] }));
}
