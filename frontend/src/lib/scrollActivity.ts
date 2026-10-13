/** Marks an element as `data-scrolling` while it is being scrolled (and briefly after), so
 * `index.css` can show its scrollbar only when it is in use. */

/** How long the scrollbar stays visible after the last scroll event. */
export const SCROLL_IDLE_MS = 900;

export function installScrollActivity(doc: Document = document): () => void {
  const view = doc.defaultView ?? window;
  const timers = new Map<Element, number>();

  const onScroll = (event: Event) => {
    const target = event.target;
    const element =
      target === doc ? doc.documentElement : target instanceof Element ? target : null;
    if (!element) return;
    if (!timers.has(element)) element.setAttribute("data-scrolling", "");
    else view.clearTimeout(timers.get(element));
    timers.set(
      element,
      view.setTimeout(() => {
        element.removeAttribute("data-scrolling");
        timers.delete(element);
      }, SCROLL_IDLE_MS),
    );
  };

  // Scroll events do not bubble: listen in the capture phase to see every scroller.
  doc.addEventListener("scroll", onScroll, { capture: true, passive: true });
  return () => {
    doc.removeEventListener("scroll", onScroll, { capture: true });
    timers.forEach((timer, element) => {
      view.clearTimeout(timer);
      element.removeAttribute("data-scrolling");
    });
    timers.clear();
  };
}
