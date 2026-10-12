/** Graphite styling for server-rendered Mermaid diagrams. */

const CLASS_DEF = /^(\s*)classDef\s+(\w+)\s.*$/gm;

/** Graphite palette: the server's per-kind colours become neutral shades; the entry point is
 * inverted like the brand mark and external systems keep a dashed outline. */
export function graphiteDiagram(source: string, dark: boolean): string {
  return source.replace(CLASS_DEF, (_line, indent: string, kind: string) => {
    const strong = kind === "entry";
    const fill = strong ? (dark ? "#e2e8f0" : "#0f172a") : dark ? "#1e293b" : "#f1f5f9";
    const stroke = strong ? fill : dark ? "#475569" : "#cbd5e1";
    const color = strong ? (dark ? "#0f172a" : "#ffffff") : dark ? "#e2e8f0" : "#0f172a";
    const dashed = kind === "external" ? ",stroke-dasharray:4 3" : "";
    return `${indent}classDef ${kind} fill:${fill},stroke:${stroke},color:${color}${dashed}`;
  });
}

export function themeVariables(dark: boolean) {
  return dark
    ? {
        background: "#0b1020",
        primaryColor: "#1e293b",
        primaryTextColor: "#e2e8f0",
        primaryBorderColor: "#475569",
        lineColor: "#64748b",
        textColor: "#cbd5e1",
        edgeLabelBackground: "#0b1020",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      }
    : {
        background: "#ffffff",
        primaryColor: "#f1f5f9",
        primaryTextColor: "#0f172a",
        primaryBorderColor: "#cbd5e1",
        lineColor: "#94a3b8",
        textColor: "#334155",
        edgeLabelBackground: "#ffffff",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      };
}
