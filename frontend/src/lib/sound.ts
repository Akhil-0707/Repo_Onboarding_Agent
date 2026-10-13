/** Quiet UI sounds, synthesised with Web Audio (no audio files): a tick on clicks, a soft tone
 * when the pointer enters a card, and faint "grains" as the cursor travels.
 *
 * Browsers only start audio after a user gesture, so nothing plays before the first click or
 * key press. The choice to mute is remembered per browser (`SoundToggle`). */

const STORAGE_KEY = "repoguide.sound";
const MASTER_VOLUME = 0.15; // every sound passes through this one gain
/** Minimum gap between hover tones, so sweeping across a grid does not chatter. */
const HOVER_GAP_S = 0.07;
/** One trail grain per this much cursor travel (px), and never closer together than the gap. */
const TRAIL_STEP_PX = 90;
const TRAIL_GAP_S = 0.045;
/** Cursor speed (px/s) at which grains reach their (still faint) full level. */
const TRAIL_FULL_SPEED = 2600;

export type TickKind = "tab" | "card" | "control";

const TICK_HZ: Record<TickKind, number> = { tab: 2100, card: 1600, control: 1250 };

type Ctor = new () => AudioContext;

function defaultCtor(): Ctor | undefined {
  const scope = globalThis as unknown as { AudioContext?: Ctor; webkitAudioContext?: Ctor };
  return scope.AudioContext ?? scope.webkitAudioContext;
}

function readStored(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    return true; // storage unavailable: sound on, as by default
  }
}

export class SoundEngine {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private lastHover = -Infinity;
  private lastGrain = -Infinity;
  private travelled = 0;
  private readonly listeners = new Set<() => void>();
  private on: boolean;

  constructor(private readonly AudioCtor: Ctor | undefined = defaultCtor()) {
    this.on = readStored();
  }

  get enabled(): boolean {
    return this.on;
  }

  setEnabled(on: boolean): void {
    this.on = on;
    try {
      window.localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
    } catch {
      // ignore: the choice just isn't remembered
    }
    if (on) this.unlock(); // turned on from a click, which counts as the gesture
    this.listeners.forEach((listener) => listener());
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Creates or resumes the audio context; call it from a user gesture. */
  unlock(): void {
    if (!this.on || !this.AudioCtor) return;
    if (!this.ctx) this.build(new this.AudioCtor());
    if (this.ctx?.state === "suspended") void this.ctx.resume();
  }

  /** A short, crisp tick: brighter for tabs, lower for plain controls. */
  tick(kind: TickKind): void {
    const ctx = this.ready();
    if (!ctx) return;
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(TICK_HZ[kind], t);
    osc.frequency.exponentialRampToValueAtTime(TICK_HZ[kind] * 0.6, t + 0.03);
    this.envelope(osc, t, 0.14, 0.002, 0.045);
  }

  /** A soft, low tone that rises slightly: the pointer entered a card. */
  hover(): void {
    const ctx = this.ready();
    if (!ctx) return;
    const t = ctx.currentTime;
    if (t - this.lastHover < HOVER_GAP_S) return;
    this.lastHover = t;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(520, t);
    osc.frequency.exponentialRampToValueAtTime(640, t + 0.08);
    this.envelope(osc, t, 0.05, 0.012, 0.14);
  }

  /** The cursor moved `distance` px at `speed` px/s: every so often, one tiny high grain.
   * Silent while the cursor rests; a little louder (never loud) when it moves fast. */
  trail(distance: number, speed: number, random: () => number = Math.random): void {
    const ctx = this.ready();
    if (!ctx) return;
    this.travelled += Math.max(0, distance);
    const t = ctx.currentTime;
    if (this.travelled < TRAIL_STEP_PX || t - this.lastGrain < TRAIL_GAP_S) return;
    this.travelled = 0;
    this.lastGrain = t;
    const level = Math.min(1, Math.max(0, speed) / TRAIL_FULL_SPEED);
    const osc = ctx.createOscillator();
    osc.type = "sine";
    // A slightly different pitch each time, so a long stroke never sounds mechanical.
    osc.frequency.setValueAtTime(2600 * (0.94 + random() * 0.12), t);
    this.envelope(osc, t, 0.02 + level * 0.025, 0.002, 0.02);
  }

  private ready(): AudioContext | null {
    return this.on && this.ctx?.state === "running" ? this.ctx : null;
  }

  private build(ctx: AudioContext): void {
    this.ctx = ctx;
    this.master = ctx.createGain();
    this.master.gain.value = MASTER_VOLUME;
    this.master.connect(ctx.destination);
  }

  /** Plays `osc` with a fast attack and an exponential decay, then releases it. */
  private envelope(osc: OscillatorNode, t: number, peak: number, attack: number, decay: number) {
    const ctx = this.ctx!;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.linearRampToValueAtTime(peak, t + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
    osc.connect(gain).connect(this.master!);
    osc.start(t);
    osc.stop(t + attack + decay + 0.02);
  }
}

export const sound = new SoundEngine();

function closest(target: EventTarget | null, selector: string): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(selector) : null;
}

const CONTROL = "button, a[href], summary, select, [role='button']";

/** Wires the sounds to the page with delegated listeners. */
export function installSoundEffects(doc: Document = document, engine: SoundEngine = sound) {
  const view = doc.defaultView ?? window;
  const reducedMotion = view.matchMedia?.("(prefers-reduced-motion: reduce)");
  let hovered: HTMLElement | null = null;
  let last: { x: number; y: number; t: number } | null = null;

  const unlock = () => engine.unlock();
  const onClick = (event: MouseEvent) => {
    const tab = closest(event.target, "[role='tab']");
    const control = tab ?? closest(event.target, CONTROL);
    if (control && (control as HTMLButtonElement).disabled) return;
    if (tab) engine.tick("tab");
    else if (control) engine.tick("control");
    else if (closest(event.target, ".surface-hover")) engine.tick("card");
  };
  const onOver = (event: PointerEvent) => {
    if (event.pointerType === "touch") return;
    const card = closest(event.target, ".surface-hover");
    if (card === hovered) return;
    hovered = card;
    if (card) engine.hover();
  };
  const onMove = (event: PointerEvent) => {
    // The visual trail is off under reduced motion; keep its sound off too.
    if (event.pointerType === "touch" || reducedMotion?.matches) return;
    const now = event.timeStamp;
    if (last && now > last.t) {
      const distance = Math.hypot(event.clientX - last.x, event.clientY - last.y);
      engine.trail(distance, (distance / (now - last.t)) * 1000);
    }
    last = { x: event.clientX, y: event.clientY, t: now };
  };
  const onLeave = () => {
    hovered = null;
    last = null;
  };

  doc.addEventListener("pointerdown", unlock, { capture: true });
  doc.addEventListener("keydown", unlock, { capture: true });
  doc.addEventListener("click", onClick, { capture: true });
  doc.addEventListener("pointerover", onOver, { passive: true });
  doc.addEventListener("pointermove", onMove, { passive: true });
  doc.documentElement.addEventListener("pointerleave", onLeave);
  return () => {
    doc.removeEventListener("pointerdown", unlock, { capture: true });
    doc.removeEventListener("keydown", unlock, { capture: true });
    doc.removeEventListener("click", onClick, { capture: true });
    doc.removeEventListener("pointerover", onOver);
    doc.removeEventListener("pointermove", onMove);
    doc.documentElement.removeEventListener("pointerleave", onLeave);
  };
}
