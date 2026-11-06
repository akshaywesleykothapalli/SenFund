import { connection } from "next/server";
import { accountMode } from "../account-server";
import Workspace from "../workspace";

export default async function Page() {
  await connection();
  return <Workspace accountsEnabled={accountMode()} />;
}
