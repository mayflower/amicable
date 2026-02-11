import type { Metadata } from "next";

import DbSmokeTest from "./_components/DbSmokeTest";

export const metadata: Metadata = {
  title: "Amicable Starter",
};

export default function Page() {
  return <DbSmokeTest />;
}
