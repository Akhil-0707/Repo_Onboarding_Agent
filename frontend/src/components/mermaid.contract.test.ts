import mermaid from "mermaid";
import { describe, expect, it } from "vitest";

// The backend renders architecture diagrams (apps/agents/mermaid.py). This keeps its output
// format honest against the Mermaid version the frontend ships: every node shape, edge style
// and class statement it can emit must parse.
const SERVER_OUTPUT = `flowchart TD
    m_cli(["Command line"])
    m_core["Core"]
    m_db[("Models ORM x 1 a b")]
    m_pay{{"Payments"}}
    m_web[/"Web UI"/]
    m_conf[["Settings"]]
    m_cli -->|"click href javascript:alert(1)"| m_core
    m_core --> m_db
    m_core -.->|"3 imports"| m_pay
    m_web -.->|"1 import"| m_conf
    classDef data fill:#fef3c7,stroke:#d97706,color:#451a03
    classDef entry fill:#e0e7ff,stroke:#4f46e5,color:#1e1b4b
    classDef external fill:#f5f5f4,stroke:#78716c,color:#1c1917,stroke-dasharray:4 3
    class m_db data
    class m_cli entry
    class m_pay external`;

describe("server-rendered Mermaid", () => {
  it("parses with the bundled Mermaid version", async () => {
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
    await expect(mermaid.parse(SERVER_OUTPUT)).resolves.toMatchObject({
      diagramType: "flowchart-v2",
    });
  });

  it("rejects broken syntax (the parser is really running)", async () => {
    await expect(mermaid.parse("flowchart TD\n    a[[[ --> ")).rejects.toThrow();
  });
});
