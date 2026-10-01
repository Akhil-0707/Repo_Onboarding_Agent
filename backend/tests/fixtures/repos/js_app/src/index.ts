import { createServer } from "./server";

const port = Number(process.env.PORT ?? 3000);

createServer().listen(port, () => {
  console.log(`listening on ${port}`);
});
