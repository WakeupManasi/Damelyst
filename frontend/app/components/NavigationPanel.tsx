"use client";

import {
  ArrowUp,
  ArrowLeft,
  ArrowRight,
  ArrowUpLeft,
  ArrowUpRight,
  CornerUpLeft,
  RotateCw,
  Flag,
  ChevronLeft,
  ChevronRight,
  X,
  Volume2,
  VolumeX,
} from "lucide-react";
import { formatDist, type NavStep } from "../lib/routing";

export function StepIcon({ step, size = 20 }: { step: NavStep; size?: number }) {
  if (step.type === "arrive") return <Flag size={size} />;
  if (step.type === "roundabout" || step.type === "rotary") return <RotateCw size={size} />;
  const m = step.modifier ?? "";
  if (m === "uturn") return <CornerUpLeft size={size} />;
  if (m === "slight left") return <ArrowUpLeft size={size} />;
  if (m === "slight right") return <ArrowUpRight size={size} />;
  if (m.includes("left")) return <ArrowLeft size={size} />;
  if (m.includes("right")) return <ArrowRight size={size} />;
  return <ArrowUp size={size} />;
}

type Props = {
  steps: NavStep[];
  active: number;
  setActive: (i: number) => void;
  /** live distance (m) from the user to the next maneuver, if GPS is available */
  distanceToNext: number | null;
  remaining: number;
  voice: boolean;
  setVoice: (v: boolean) => void;
  onExit: () => void;
};

export default function NavigationPanel({
  steps,
  active,
  setActive,
  distanceToNext,
  remaining,
  voice,
  setVoice,
  onExit,
}: Props) {
  const step = steps[active];
  const next = steps[active + 1];
  if (!step) return null;

  return (
    <div className="nav-panel">
      <div className="nav-current">
        <div className="nav-current-icon">
          <StepIcon step={next ?? step} size={30} />
        </div>
        <div className="nav-current-text">
          <span className="nav-dist">
            {next
              ? `In ${formatDist(distanceToNext ?? step.distance)}`
              : "Arrived"}
          </span>
          <strong>{next ? next.instruction : step.instruction}</strong>
          <small>
            {formatDist(remaining)} left · step {active + 1} of {steps.length}
          </small>
        </div>
        <div className="nav-actions">
          <button
            type="button"
            aria-label={voice ? "Mute voice" : "Turn on voice"}
            onClick={() => setVoice(!voice)}
          >
            {voice ? <Volume2 size={16} /> : <VolumeX size={16} />}
          </button>
          <button type="button" aria-label="Exit navigation" onClick={onExit}>
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="nav-stepper">
        <button
          type="button"
          disabled={active === 0}
          onClick={() => setActive(active - 1)}
        >
          <ChevronLeft size={16} /> Prev
        </button>
        <button
          type="button"
          disabled={active >= steps.length - 1}
          onClick={() => setActive(active + 1)}
        >
          Next <ChevronRight size={16} />
        </button>
      </div>

      <ol className="nav-steps">
        {steps.map((s, i) => (
          <li
            key={i}
            className={i === active ? "active" : i < active ? "done" : ""}
            onClick={() => setActive(i)}
          >
            <span className="nav-step-icon">
              <StepIcon step={s} size={15} />
            </span>
            <span className="nav-step-text">{s.instruction}</span>
            {s.distance > 0 && <span className="nav-step-dist">{formatDist(s.distance)}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}
