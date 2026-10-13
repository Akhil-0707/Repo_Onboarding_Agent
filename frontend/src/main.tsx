import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./index.css";
import { installPointerEffects } from "./lib/pointerEffects";
import { installScrollActivity } from "./lib/scrollActivity";
import { installSoundEffects } from "./lib/sound";

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root not found");

installPointerEffects();
installScrollActivity();
installSoundEffects();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
