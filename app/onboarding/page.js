import { connection } from "next/server";
import Onboarding from "./onboarding";

export default async function Page() {
  await connection();
  return <Onboarding />;
}
