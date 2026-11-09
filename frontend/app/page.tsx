"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  ShieldCheck,
  Navigation,
  Users,
  MapPinned,
  Sparkles,
  ArrowRight,
  Route as RouteIcon,
} from "lucide-react";

import {
  fetchRoutes,
  geocode,
  reverseGeocode,
  distanceM,
  type LiveRoute,
  type LngLat,
  type Place,
} from "./lib/routing";

import Navbar from "./components/Navbar";
import Map from "./components/Map";
import SearchBox from "./components/SearchBox";
import RouteCard from "./components/RouteCard";
import FilterPanel from "./components/FilterPanel";
import NavigationPanel from "./components/NavigationPanel";

const HISTORY_KEY = "saferoutes:history";

export default function Home() {
  /* ========================================= */
  /* STATE */
  /* ========================================= */

  const [minSafety, setMinSafety] = useState(0);

  const [wellLitOnly, setWellLitOnly] =
    useState(false);

  const [selectedRoute, setSelectedRoute] =
    useState(0);

  const [searchMessage, setSearchMessage] =
    useState("");

  /* ========================================= */
  /* FILTER ROUTES */
  /* ========================================= */

  const [routes, setRoutes] = useState<LiveRoute[]>([]);
  const [loading, setLoading] = useState(false);
  const [userPos, setUserPos] = useState<LngLat | null>(null);
  const [mapCenter, setMapCenter] = useState<LngLat | undefined>();
  const [fromText, setFromText] = useState("");
  const [toText, setToText] = useState("");
  const [fromCoord, setFromCoord] = useState<LngLat | null>(null);
  const [toCoord, setToCoord] = useState<LngLat | null>(null);
  /** true when the destination came from the address box: the pin stays put until the address changes */
  const [destLocked, setDestLocked] = useState(false);

  const filteredRoutes = useMemo(() => {
    return routes.filter((route) => {
      const safetyMatch =
        route.safetyScore >= minSafety;

      const lightingMatch =
        !wellLitOnly || route.lighting >= 70;

      return safetyMatch && lightingMatch;
    });
  }, [routes, minSafety, wellLitOnly]);

  /* ========================================= */
  /* SEARCH */
  /* ========================================= */

  /** Bring the map into view (centred on small screens, where it sits above the list). */
  const showMap = () =>
    document.getElementById("route-map")?.scrollIntoView({ behavior: "smooth", block: "start" });

  /* Recent destinations, kept in this browser */
  const [history, setHistory] = useState<Place[]>([]);
  useEffect(() => {
    try {
      setHistory(JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]"));
    } catch {}
  }, []);
  const addHistory = (p: Place) =>
    setHistory((h) => {
      const next = [p, ...h.filter((x) => x.label !== p.label)].slice(0, 6);
      try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });

  const MY_LOCATION = "📍 My location";

  const getMyPosition = (): Promise<LngLat> =>
    new Promise((resolve, reject) => {
      if (userPos) return resolve(userPos);
      if (!("geolocation" in navigator)) {
        return reject(new Error("Your browser does not support location."));
      }
      navigator.geolocation.getCurrentPosition(
        (p) => resolve([p.coords.longitude, p.coords.latitude]),
        () =>
          reject(
            new Error(
              "Location permission denied. Allow location access or type a starting place."
            )
          ),
        { enableHighAccuracy: true, timeout: 10000 }
      );
    });

  const handleUseMyLocation = async () => {
    try {
      const pos = await getMyPosition();
      setUserPos(pos);
      setFromText(MY_LOCATION);
      setFromCoord(pos);
      setSearchMessage("Using your current location as the start.");
    } catch (e) {
      setSearchMessage((e as Error).message);
    }
  };

  const near = userPos ?? mapCenter;

  const runSearch = async (overrideTo?: LngLat, jumpToMap = !overrideTo) => {
    const from = fromText;
    const to = toText;
    if (!overrideTo && !toCoord && !to.trim()) {
      setSearchMessage("Enter a destination or tap the map to drop a pin.");
      return;
    }

    setLoading(true);
    setSearchMessage(`Finding safer routes...`);

    try {
      const start =
        fromCoord ??
        (!from.trim() || from === MY_LOCATION
          ? await getMyPosition()
          : await geocode(from, near));
      const end = overrideTo ?? toCoord ?? (await geocode(to, near));
      setToCoord(end);
      if (!overrideTo) setDestLocked(true);
      if (!overrideTo && to.trim()) addHistory({ label: to, detail: "", coord: end });
      const found = await fetchRoutes(start, end);

      setRoutes(found);
      setSelectedRoute(0);
      setSearchMessage(
        `Found ${found.length} route${found.length > 1 ? "s" : ""}. Safest is highlighted.`
      );
      if (jumpToMap) showMap();
    } catch (e) {
      setSearchMessage((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  /* Tap on map / drag pin => set destination and route right away */
  const handlePickDestination = async (pos: LngLat) => {
    if (destLocked) return;
    setToCoord(pos);
    setToText("📌 Dropped pin");
    reverseGeocode(pos).then((name) => setToText(`📌 ${name}`));
    if (fromCoord || fromText.trim() || userPos) {
      runSearch(pos);
    } else {
      setSearchMessage("Destination pinned. Allow location or enter a start, then Find Safe Route.");
    }
  };

  /* ========================================= */
  /* SELECT ROUTE */
  /* ========================================= */

  const handleSelectRoute = (index: number) => {
    setSelectedRoute(index);
    showMap();
  };

  /* ========================================= */
  /* RESET SELECTED ROUTE WHEN FILTER CHANGES */
  /* ========================================= */

  const safeSelectedRoute =
    selectedRoute < filteredRoutes.length
      ? selectedRoute
      : 0;

  /* ========================================= */
  /* TURN-BY-TURN NAVIGATION */
  /* ========================================= */

  const [navigating, setNavigating] = useState(false);
  const [navStep, setNavStep] = useState(0);
  const [voice, setVoice] = useState(true);
  const [livePos, setLivePos] = useState<LngLat | null>(null);
  const activeRoute = filteredRoutes[safeSelectedRoute];
  const steps = activeRoute?.steps ?? [];

  const startNavigation = () => {
    if (!steps.length) return;
    // iOS needs permission for the compass, asked from a tap
    const DOE = window.DeviceOrientationEvent as unknown as { requestPermission?: () => Promise<string> };
    DOE?.requestPermission?.().catch(() => {});
    setNavStep(0);
    setNavigating(true);
    showMap();
  };
  const exitNavigation = () => {
    setNavigating(false);
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  };

  // Stop navigating if the route changes underneath us
  useEffect(() => {
    setNavigating(false);
  }, [routes]);

  // Follow GPS while navigating and auto-advance near each maneuver
  useEffect(() => {
    if (!navigating || !("geolocation" in navigator)) return;
    const id = navigator.geolocation.watchPosition(
      (p) => setLivePos([p.coords.longitude, p.coords.latitude]),
      () => {},
      { enableHighAccuracy: true }
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [navigating]);

  // Compass heading (degrees from north) for the direction beam
  const [compass, setCompass] = useState<number | null>(null);
  useEffect(() => {
    if (!navigating) return;
    type OEvent = DeviceOrientationEvent & { webkitCompassHeading?: number };
    const onOrient = (e: OEvent) => {
      if (typeof e.webkitCompassHeading === "number") setCompass(e.webkitCompassHeading);
      else if (e.absolute && e.alpha !== null) setCompass((360 - e.alpha) % 360);
    };
    const evt = "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
    window.addEventListener(evt, onOrient as EventListener);
    return () => window.removeEventListener(evt, onOrient as EventListener);
  }, [navigating]);

  const nextStep = steps[navStep + 1];
  const distanceToNext =
    navigating && livePos && nextStep ? distanceM(livePos, nextStep.location) : null;

  useEffect(() => {
    if (distanceToNext !== null && distanceToNext < 20 && navStep < steps.length - 1) {
      setNavStep(navStep + 1);
    }
  }, [distanceToNext, navStep, steps.length]);

  // Speak each new instruction
  const spoken = useRef(-1);
  useEffect(() => {
    if (!navigating) {
      spoken.current = -1;
      return;
    }
    if (!voice || spoken.current === navStep || !("speechSynthesis" in window)) return;
    spoken.current = navStep;
    const target = steps[navStep + 1] ?? steps[navStep];
    if (!target) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(target.instruction));
  }, [navigating, navStep, voice, steps]);

  // Where to draw "you" and which way you face: live GPS + compass when we have them,
  // otherwise the current step and the direction the route goes from there.
  const youPos: LngLat | null = navigating
    ? livePos ?? steps[navStep]?.location ?? null
    : userPos;
  const youHeading: number | null = navigating
    ? compass ?? steps[navStep]?.bearing ?? null
    : compass;

  const remaining = steps.slice(navStep).reduce((s, x) => s + x.distance, 0);

  /* ========================================= */
  /* RENDER */
  /* ========================================= */

  return (
    <main className="saferoutes-app">

      {/* ===================================== */}
      {/* NAVBAR */}
      {/* ===================================== */}

      <Navbar />

      {/* ===================================== */}
      {/* HERO */}
      {/* ===================================== */}

      <section
        className="hero"
        id="home"
      >
        <div className="hero-content">

          {/* Badge */}

          <div className="badge">
            <ShieldCheck size={15} />

            <span>
              Safety-first navigation
            </span>
          </div>

          {/* Heading */}

          <h1>
            Find a route
            <br />

            <span>
              you can trust.
            </span>
          </h1>

          {/* Description */}

          <p>
            Find safer routes with intelligent
            safety scores, lighting information,
            and community insights.
          </p>

          {/* Search */}

          <SearchBox
            from={{
              text: fromText,
              setText: (t) => {
                setFromText(t);
                setFromCoord(null);
              },
              onPick: (p) => {
                setFromText(p.label);
                setFromCoord(p.coord);
              },
            }}
            to={{
              text: toText,
              setText: (t) => {
                setToText(t);
                setToCoord(null);
                setDestLocked(false);
              },
              onPick: (p) => {
                setToText(p.label);
                setToCoord(p.coord);
                setDestLocked(true);
                addHistory(p);
                // pick a place => show routes on the map right away
                if (fromCoord || fromText.trim() || userPos) runSearch(p.coord, true);
              },
            }}
            near={near}
            history={history}
            onSearch={() => runSearch()}
            onUseMyLocation={handleUseMyLocation}
            loading={loading}
          />

          {/* Search status */}

          {searchMessage && (
            <div className="search-message">
              <Sparkles size={15} />

              <span>
                {searchMessage}
              </span>
            </div>
          )}

        </div>
      </section>

      {/* ===================================== */}
      {/* ROUTE DASHBOARD */}
      {/* ===================================== */}

      <section
        className="dashboard"
        id="routes"
      >

        {/* Dashboard heading */}

        <div className="dashboard-header">

          <div>
            <span className="section-label">
              SMART NAVIGATION
            </span>

            <h2>
              Choose your safest route
            </h2>

            <p>
              Compare routes based on safety,
              lighting, travel time and activity.
            </p>
          </div>

          <div className="route-count">

            <RouteIcon size={17} />

            <span>
              {filteredRoutes.length}
            </span>

            <small>
              routes available
            </small>

          </div>

        </div>

        {/* =================================== */}
        {/* DASHBOARD GRID */}
        {/* =================================== */}

        <div className="dashboard-grid">

          {/* ================================= */}
          {/* MAP */}
          {/* ================================= */}

          <div className="map-section" id="route-map">

            <div className="map-header">

              <div className="map-title">

                <div className="map-title-icon">
                  <MapPinned size={17} />
                </div>

                <div>
                  <strong>
                    Live route map
                  </strong>

                  <span>
                    {destLocked ? "Destination pinned from your address" : "Tap the map to drop your destination pin"}
                  </span>
                </div>

              </div>

              <div className="map-status">

                <span className="map-status-dot" />

                Live

              </div>

            </div>

            <div className="map-container-wrapper">

              <Map
                routes={filteredRoutes}
                selectedRoute={safeSelectedRoute}
                onUserLocation={setUserPos}
                destination={toCoord}
                destinationLocked={destLocked}
                onPickDestination={handlePickDestination}
                onCenterChange={setMapCenter}
                navigating={navigating}
                activeStep={navStep}
                you={youPos}
                heading={youHeading}
              />

              {/* Map overlay */}

              {activeRoute && !navigating ? (
                <button
                  type="button"
                  className="start-nav-button"
                  onClick={startNavigation}
                >
                  <Navigation size={16} />
                  Start navigation
                </button>
              ) : !navigating && (
                <div className="map-overlay">

                  <div className="map-overlay-icon">
                    <Navigation size={14} />
                  </div>

                  <div>
                    <strong>
                      Safety optimized
                    </strong>

                    <span>
                      Routes ranked by safety
                    </span>
                  </div>

                </div>
              )}

            </div>

          </div>

          {/* ================================= */}
          {/* SIDEBAR */}
          {/* ================================= */}

          <aside className="sidebar">

            {navigating && (
              <NavigationPanel
                steps={steps}
                active={navStep}
                setActive={setNavStep}
                distanceToNext={distanceToNext}
                remaining={remaining}
                voice={voice}
                setVoice={setVoice}
                onExit={exitNavigation}
              />
            )}

            {!navigating && <>
            {/* Filters */}

            <FilterPanel
              minSafety={minSafety}
              setMinSafety={setMinSafety}
              wellLitOnly={wellLitOnly}
              setWellLitOnly={setWellLitOnly}
            />

            {/* Routes */}

            <div className="routes-list">

              <div className="routes-list-header">

                <div>

                  <h3>
                    Recommended routes
                  </h3>

                  <span>
                    Based on your preferences
                  </span>

                </div>

                <div className="routes-number">
                  {filteredRoutes.length}
                </div>

              </div>

              {/* Empty state */}

              {filteredRoutes.length === 0 && (
                <div className="empty-state">

                  <div className="empty-state-icon">
                    <ShieldCheck size={22} />
                  </div>

                  <h3>
                    {routes.length ? "No routes found" : "Search to see routes"}
                  </h3>

                  <p>
                    {routes.length
                      ? "Try lowering the safety score or disabling the lighting filter."
                      : "Enter a destination above. Leave the start empty to use your current location."}
                  </p>

                </div>
              )}

              {/* Route cards */}

              {filteredRoutes.map(
                (route, index) => (
                  <RouteCard
                    key={route.id}
                    route={route}
                    selected={
                      safeSelectedRoute === index
                    }
                    onSelect={() =>
                      handleSelectRoute(index)
                    }
                    onNavigate={startNavigation}
                  />
                )
              )}

            </div>
            </>}

          </aside>

        </div>

      </section>

      {/* ===================================== */}
      {/* SAFETY FEATURES */}
      {/* ===================================== */}

      <section
        className="features"
        id="safety"
      >

        <div className="section-heading">

          <div className="section-heading-icon">
            <ShieldCheck size={20} />
          </div>

          <span className="section-label">
            SAFETY BEYOND DIRECTIONS
          </span>

          <h2>
            Navigation that thinks about safety.
          </h2>

          <p>
            SafeRoutes doesn't simply calculate
            the shortest path. It helps you choose
            a route that feels safer.
          </p>

        </div>

        <div className="feature-grid">

          {/* Feature 1 */}

          <div className="feature">

            <div className="feature-icon">
              <ShieldCheck size={24} />
            </div>

            <div className="feature-number">
              01
            </div>

            <h3>
              Safety Scores
            </h3>

            <p>
              Quickly compare routes using a
              simple safety score based on
              multiple route indicators.
            </p>

            <span className="feature-link">
              Explore safety
              <ArrowRight size={14} />
            </span>

          </div>

          {/* Feature 2 */}

          <div className="feature">

            <div className="feature-icon">
              <Users size={24} />
            </div>

            <div className="feature-number">
              02
            </div>

            <h3>
              Community Insights
            </h3>

            <p>
              Understand activity and community
              patterns around different areas.
            </p>

            <span className="feature-link">
              View insights
              <ArrowRight size={14} />
            </span>

          </div>

          {/* Feature 3 */}

          <div className="feature">

            <div className="feature-icon">
              <Navigation size={24} />
            </div>

            <div className="feature-number">
              03
            </div>

            <h3>
              Smarter Navigation
            </h3>

            <p>
              Compare multiple routes and choose
              the option that fits your journey.
            </p>

            <span className="feature-link">
              Compare routes
              <ArrowRight size={14} />
            </span>

          </div>

        </div>

      </section>

      {/* ===================================== */}
      {/* ABOUT */}
      {/* ===================================== */}

      <section
        className="about-section"
        id="about"
      >

        <div className="about-content">

          <div className="about-icon">
            <ShieldCheck size={28} />
          </div>

          <span className="section-label">
            ABOUT SAFEROUTES
          </span>

          <h2>
            Every journey should feel safer.
          </h2>

          <p>
            SafeRoutes combines real map data,
            route information and safety indicators
            into one simple navigation experience.
          </p>

          <a
            href="#routes"
            className="about-button"
          >
            Explore routes

            <ArrowRight size={16} />
          </a>

        </div>

      </section>

      {/* ===================================== */}
      {/* FOOTER */}
      {/* ===================================== */}

      <footer>

        <div className="footer-content">

          <div className="footer-brand">

            <div className="footer-logo">
              <ShieldCheck size={20} />
            </div>

            <div>
              <strong>
                SafeRoutes
              </strong>

              <span>
                Safer journeys, smarter navigation.
              </span>
            </div>

          </div>

          <div className="footer-links">

            <a href="#home">
              Home
            </a>

            <a href="#routes">
              Routes
            </a>

            <a href="#safety">
              Safety
            </a>

            <a href="#about">
              About
            </a>

          </div>

          <div className="footer-copy">
            © {new Date().getFullYear()} SafeRoutes
          </div>

        </div>

      </footer>

    </main>
  );
}
