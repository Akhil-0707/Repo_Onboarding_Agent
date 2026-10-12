import { useEffect, useRef } from "react";

import { startDotField } from "../lib/dotField";

/** Drifting dots behind every page; purely decorative and never receives the pointer. */
export function LiveBackground() {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => (canvas.current ? startDotField(canvas.current) : undefined), []);
  return (
    <canvas
      ref={canvas}
      aria-hidden="true"
      data-testid="live-background"
      className="pointer-events-none fixed inset-0 -z-10 h-full w-full"
    />
  );
}
