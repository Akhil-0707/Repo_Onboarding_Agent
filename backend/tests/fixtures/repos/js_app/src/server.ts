import express from "express";

import { router } from "./routes/index";

export function createServer() {
  const app = express();
  app.use(express.json());
  app.use("/api", router);
  return app;
}
