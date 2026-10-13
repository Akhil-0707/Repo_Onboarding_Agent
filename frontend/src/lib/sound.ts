/** Quiet UI sounds, synthesised with Web Audio (no audio files): a soft tick on clicks, a gentle
 * tone when the pointer enters a card, and a faint two-note chime when a chat answer arrives.
 *
 * Browsers only start audio after a user gesture, so nothing plays before the first click or
 * key press. The choice to mute is remembered per browser (`SoundToggle`). */

const STORAGE_KEY = "repoguide.sound";
const MASTER_VOLUME = 0.15; // every sound passes through this one gain
/** Minimum gap between hover tones, so sweeping across a grid does not chatter. */
const HOVER_GAP_S = 0.07;

export type TickKind = "tab" | "card" | "control";

// Pure sine blips: a soft "tk" with no harsh overtones. Tabs sit a little higher than cards.
const TICK_HZ: Record<TickKind, number> = { tab: 1450, card: 1150, control: 950 };

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

  /** A short, soft tick: slightly higher for tabs, lower for plain controls. */
  tick(kind: TickKind): void {
    const ctx = this.ready();
    if (!ctx) return;
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(TICK_HZ[kind], t);
    osc.frequency.exponentialRampToValueAtTime(TICK_HZ[kind] * 0.85, t + 0.02);
    this.envelope(osc, t, 0.07, 0.0015, 0.022);
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

  /** Two faint rising notes: a chat answer has arrived. */
  answerReady(): void {
    const ctx = this.ready();
    if (!ctx) return;
    const t = ctx.currentTime;
    [660, 880].forEach((hz, i) => {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.setValueAtTime(hz, t + i * 0.09);
      this.envelope(osc, t + i * 0.09, 0.035, 0.01, 0.22);
    });
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
  let hovered: HTMLElement | null = null;

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
  const onLeave = () => {
    hovered = null;
  };

  doc.addEventListener("pointerdown", unlock, { capture: true });
  doc.addEventListener("keydown", unlock, { capture: true });
  doc.addEventListener("click", onClick, { capture: true });
  doc.addEventListener("pointerover", onOver, { passive: true });
  doc.documentElement.addEventListener("pointerleave", onLeave);
  return () => {
    doc.removeEventListener("pointerdown", unlock, { capture: true });
    doc.removeEventListener("keydown", unlock, { capture: true });
    doc.removeEventListener("click", onClick, { capture: true });
    doc.removeEventListener("pointerover", onOver);
    doc.documentElement.removeEventListener("pointerleave", onLeave);
  };
}
