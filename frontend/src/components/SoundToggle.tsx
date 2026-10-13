import { useSyncExternalStore } from "react";

import { sound } from "../lib/sound";
import type { SoundEngine } from "../lib/sound";

export function SoundToggle({ engine = sound }: { engine?: SoundEngine }) {
  const on = useSyncExternalStore(
    (listener) => engine.subscribe(listener),
    () => engine.enabled,
  );
  const label = on ? "Turn sound off" : "Turn sound on";
  return (
    <button
      type="button"
      onClick={() => engine.setEnabled(!on)}
      aria-pressed={on}
      aria-label={label}
      title={label}
      className="btn btn-ghost h-9 w-9 p-0"
    >
      <svg
        key={on ? "on" : "off"}
        viewBox="0 0 24 24"
        className="animate-pop-in h-[18px] w-[18px]"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M11 5 6 9H3v6h3l5 4V5z" />
        {on ? (
          <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
        ) : (
          <path d="m16 9 5 6M21 9l-5 6" />
        )}
      </svg>
    </button>
  );
}
