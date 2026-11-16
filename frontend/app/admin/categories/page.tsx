import type { Metadata } from "next";
import { MasterDataPage } from "../_registers/master-data-page";

export const metadata: Metadata = {
  title: "Categories | TRANSPIRE Administration",
  description: "Manage idea categories and their subcategories.",
};

export default function Page() {
  return <MasterDataPage kind="category" />;
}
