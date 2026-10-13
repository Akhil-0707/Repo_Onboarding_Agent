import { afterEach, describe, expect, it, vi } from "vitest";

import { installSoundEffects, SoundEngine } from "./sound";

function param() {
  return {
    value: 0,
    setValueAtTime: vi.fn(),
    linearRampToValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
    setTargetAtTime: vi.fn(),
    cancelScheduledValues: vi.fn(),
  };
}

function node<T extends object>(extra: T) {
  const n = { ...extra, connect: vi.fn((next: unknown) => next) };
  return n;
}

/** A minimal stand-in for AudioContext that records what gets created. */
class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  state: AudioContextState = "suspended";
  currentTime = 0;
  sampleRate = 100;
  destination = {};
  oscillators: { type: string; frequency: ReturnType<typeof param>; start: unknown }[] = [];
  gains: { gain: ReturnType<typeof param> }[] = [];
  constructor() {
    FakeAudioContext.instances.push(this);
  }
  resume = vi.fn(async () => {
    this.state = "running";
  });
  createGain() {
    const gain = node({ gain: param() });
    this.gains.push(gain);
    return gain;
  }
  createOscillator() {
    const osc = node({ type: "", frequency: param(), start: vi.fn(), stop: vi.fn() });
    this.oscillators.push(osc);
    return osc;
  }
}

async function unlocked() {
  const engine = new SoundEngine(FakeAudioContext as unknown as new () => AudioContext);
  engine.unlock();
  const ctx = FakeAudioContext.instances.at(-1)!;
  await ctx.resume.mock.results[0]!.value;
  return { engine, ctx };
}

afterEach(() => {
  FakeAudioContext.instances = [];
});

describe("SoundEngine", () => {
  it("stays silent until a user gesture unlocks audio", () => {
    const engine = new SoundEngine(FakeAudioContext as unknown as new () => AudioContext);
    engine.tick("tab");
    engine.hover();
    expect(FakeAudioContext.instances).toHaveLength(0);
  });

  it("ticks higher for tabs than for cards and controls", async () => {
    const { engine, ctx } = await unlocked();
    engine.tick("tab");
    engine.tick("card");
    engine.tick("control");
    const pitches = ctx.oscillators.map((o) => o.frequency.setValueAtTime.mock.calls[0]![0]);
    expect(pitches[0]).toBeGreaterThan(pitches[1]!);
    expect(pitches[1]).toBeGreaterThan(pitches[2]!);
  });

  it("plays one hover tone per short gap", async () => {
    const { engine, ctx } = await unlocked();
    engine.hover();
    engine.hover();
    expect(ctx.oscillators).toHaveLength(1);
    ctx.currentTime = 0.2;
    engine.hover();
    expect(ctx.oscillators).toHaveLength(2);
    expect(ctx.oscillators[1]!.type).toBe("sine");
  });

  it("ticks softly: pure, short sine blips well below the hover tone's length", async () => {
    const { engine, ctx } = await unlocked();
    engine.tick("card");
    expect(ctx.oscillators[0]!.type).toBe("sine");
    const envelope = ctx.gains[1]!.gain; // [0] is the master volume
    const [peak] = envelope.linearRampToValueAtTime.mock.calls[0]!;
    const [, end] = envelope.exponentialRampToValueAtTime.mock.calls[0]!;
    expect(peak).toBeLessThanOrEqual(0.07);
    expect(end).toBeLessThan(0.03); // over in under 30 ms
  });

  it("chimes two faint rising notes when an answer arrives", async () => {
    const { engine, ctx } = await unlocked();
    engine.answerReady();
    const notes = ctx.oscillators.map((o) => o.frequency.setValueAtTime.mock.calls[0]![0]);
    expect(notes).toHaveLength(2);
    expect(notes[1]).toBeGreaterThan(notes[0]!);
  });

  it("can be muted, remembers it, and wakes again when turned on", async () => {
    const { engine, ctx } = await unlocked();
    const listener = vi.fn();
    engine.subscribe(listener);
    engine.setEnabled(false);
    expect(listener).toHaveBeenCalled();
    expect(window.localStorage.getItem("repoguide.sound")).toBe("off");
    engine.tick("tab");
    expect(ctx.oscillators).toHaveLength(0);
    expect(new SoundEngine(FakeAudioContext as unknown as new () => AudioContext).enabled).toBe(
      false,
    );

    engine.setEnabled(true);
    engine.tick("tab");
    expect(ctx.oscillators).toHaveLength(1);
  });

  it("does nothing where Web Audio is missing", () => {
    const engine = new SoundEngine(undefined);
    engine.unlock();
    engine.tick("card");
    expect(engine.enabled).toBe(true);
  });
});

describe("installSoundEffects", () => {
  let uninstall: () => void = () => undefined;
  afterEach(() => {
    uninstall();
    document.body.innerHTML = "";
  });

  function fakeEngine() {
    return { unlock: vi.fn(), tick: vi.fn(), hover: vi.fn() };
  }

  function install(engine: ReturnType<typeof fakeEngine>) {
    uninstall = installSoundEffects(document, engine as unknown as SoundEngine);
  }

  function pointer(type: string, target: Element, init: MouseEventInit & { timeStamp?: number }) {
    const event = new MouseEvent(type, { bubbles: true, ...init });
    Object.defineProperty(event, "pointerType", { value: "mouse" });
    if (init.timeStamp !== undefined)
      Object.defineProperty(event, "timeStamp", { value: init.timeStamp });
    target.dispatchEvent(event);
  }

  it("ticks for tabs, controls and cards, and unlocks on gestures", () => {
    const engine = fakeEngine();
    install(engine);
    document.body.innerHTML = `
      <button role="tab" id="tab">Tour</button>
      <button id="btn">Go</button><button id="off" disabled>No</button>
      <div class="surface-hover" id="card"><p id="text">Card</p></div>
      <p id="plain">Text</p>`;
    const el = (id: string) => document.getElementById(id)!;

    el("tab").dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    expect(engine.unlock).toHaveBeenCalled();
    el("tab").click();
    el("btn").click();
    el("text").click();
    el("plain").click();
    el("off").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(engine.tick.mock.calls.map(([kind]) => kind)).toEqual(["tab", "control", "card"]);
  });

  it("plays the hover tone once per card entered", () => {
    const engine = fakeEngine();
    install(engine);
    document.body.innerHTML = `<div class="surface-hover" id="a"><span id="inner">x</span></div>
      <div class="surface-hover" id="b"></div>`;
    pointer("pointerover", document.getElementById("a")!, {});
    pointer("pointerover", document.getElementById("inner")!, {});
    pointer("pointerover", document.getElementById("b")!, {});
    expect(engine.hover).toHaveBeenCalledTimes(2);
  });
});

describe("volume", () => {
  it("keeps every sound behind one quiet master volume", async () => {
    const { ctx } = await unlocked();
    expect(ctx.gains[0]!.gain.value).toBe(0.15);
  });
});
