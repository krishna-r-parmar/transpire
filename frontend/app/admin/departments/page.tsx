import type { Metadata } from "next";
import { MasterDataPage } from "../_registers/master-data-page";

export const metadata: Metadata = {
  title: "Departments | TRANSPIRE Administration",
  description: "Manage departments and the sites they work at.",
};

export default function Page() {
  return <MasterDataPage kind="department" />;
}
