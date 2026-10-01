import { Router } from "express";

import { getUser } from "../services/users";

export const router = Router();

router.get("/users/:id", async (req, res) => {
  const user = await getUser(req.params.id);
  res.status(user ? 200 : 404).json(user ?? {});
});
