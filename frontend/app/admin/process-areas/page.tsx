import type { Metadata } from "next";
import { MasterDataPage } from "../_registers/master-data-page";

export const metadata: Metadata = {
  title: "Process areas | TRANSPIRE Administration",
  description: "Manage the process areas an idea can improve.",
};

export default function Page() {
  return <MasterDataPage kind="process_area" />;
}
