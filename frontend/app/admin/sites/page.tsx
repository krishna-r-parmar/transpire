import type { Metadata } from "next";
import { MasterDataPage } from "../_registers/master-data-page";

export const metadata: Metadata = {
  title: "Sites | TRANSPIRE Administration",
  description: "Manage the sites people choose when they submit an idea.",
};

export default function Page() {
  return <MasterDataPage kind="site" />;
}
