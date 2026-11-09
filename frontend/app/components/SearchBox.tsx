"use client";

import { Search, MapPin, LocateFixed, History } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { searchPlaces, type LngLat, type Place } from "../lib/routing";

type Field = {
  text: string;
  setText: (t: string) => void;
  onPick: (p: Place) => void;
};

type SearchBoxProps = {
  from: Field;
  to: Field;
  near?: LngLat;
  /** recent destinations shown when the destination box is focused */
  history?: Place[];
  onSearch: () => void;
  onUseMyLocation: () => void;
  loading?: boolean;
};

function PlaceInput({
  field,
  placeholder,
  near,
  iconClass,
  extra,
  history = [],
}: {
  history?: Place[];
  field: Field;
  placeholder: string;
  near?: LngLat;
  iconClass: string;
  extra?: React.ReactNode;
}) {
  const [items, setItems] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const typed = useRef(false);
  const [showHistory, setShowHistory] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Empty or untouched box: offer recent destinations; otherwise the last suggestions
  const openList = () => {
    if (history.length && (!typed.current || !field.text.trim())) {
      setShowHistory(true);
      setOpen(true);
    } else if (items.length) {
      setShowHistory(false);
      setOpen(true);
    }
  };

  // Debounced suggestions while the user types
  useEffect(() => {
    if (!typed.current) return;
    const q = field.text;
    const t = setTimeout(async () => {
      const r = await searchPlaces(q, near);
      setItems(r);
      if (q.trim()) setShowHistory(false);
      // only pop the list open if the user is still in this box
      if (document.activeElement !== inputRef.current) return;
      setOpen(r.length > 0 || (!q.trim() && history.length > 0));
    }, 300);
    return () => clearTimeout(t);
  }, [field.text, near]);

  return (
    <div className="input-wrapper" style={{ position: "relative" }}>
      <MapPin size={20} className={`input-icon ${iconClass}`} />
      <input
        type="text"
        placeholder={placeholder}
        value={field.text}
        onChange={(e) => {
          typed.current = true;
          setShowHistory(e.target.value.trim() === "" && history.length > 0);
          field.setText(e.target.value);
        }}
        ref={inputRef}
        onFocus={(e) => {
          openList();
          if (history.length && !typed.current) e.currentTarget.select();
        }}
        onClick={openList}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {extra}
      {open && (
        <ul
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 50,
            marginTop: 6,
            padding: 4,
            listStyle: "none",
            background: "var(--background, #fff)",
            color: "inherit",
            border: "1px solid rgba(0,0,0,0.1)",
            borderRadius: 12,
            boxShadow: "0 10px 30px rgba(0,0,0,0.12)",
            textAlign: "left",
            maxHeight: 280,
            overflowY: "auto",
          }}
        >
          {showHistory && (
            <li style={{ padding: "6px 10px 2px", fontSize: 11, fontWeight: 700, letterSpacing: 0.5, opacity: 0.55 }}>
              RECENT
            </li>
          )}
          {(showHistory ? history : items).map((p, i) => (
            <li
              key={i}
              onMouseDown={(e) => {
                e.preventDefault();
                typed.current = false;
                field.onPick(p);
                setOpen(false);
              }}
              style={{ padding: "8px 10px", cursor: "pointer", borderRadius: 8 }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(22,163,74,0.08)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "")}
            >
              <div style={{ fontWeight: 600, fontSize: 14, display: "flex", alignItems: "center", gap: 6 }}>
                {showHistory && <History size={14} style={{ opacity: 0.6, flex: "none" }} />}
                {p.label}
              </div>
              {p.detail && <div style={{ fontSize: 12, opacity: 0.65 }}>{p.detail}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SearchBox({
  from,
  to,
  near,
  history,
  onSearch,
  onUseMyLocation,
  loading,
}: SearchBoxProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSearch();
  };

  return (
    <form className="search-box" onSubmit={handleSubmit}>
      <PlaceInput
        field={from}
        placeholder="Starting location (or blank = my location)"
        near={near}
        iconClass=""
        extra={
          <button
            type="button"
            onClick={onUseMyLocation}
            title="Use my current location"
            aria-label="Use my current location"
            style={{
              position: "absolute",
              right: 10,
              top: "50%",
              transform: "translateY(-50%)",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#16a34a",
              display: "flex",
              padding: 4,
            }}
          >
            <LocateFixed size={18} />
          </button>
        }
      />

      <PlaceInput
        field={to}
        placeholder="Destination, shop, chowk… or tap map"
        near={near}
        history={history}
        iconClass="destination"
      />

      <button type="submit" className="search-button" disabled={loading}>
        <Search size={20} />
        {loading ? "Finding…" : "Find Safe Route"}
      </button>
    </form>
  );
}
