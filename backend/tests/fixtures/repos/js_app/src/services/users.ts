export interface User {
  id: string;
  name: string;
}

export class UserStore {
  private users = new Map<string, User>([["1", { id: "1", name: "ada" }]]);

  find(id: string): User | undefined {
    return this.users.get(id);
  }
}

const store = new UserStore();

export async function getUser(id: string): Promise<User | undefined> {
  return store.find(id);
}
