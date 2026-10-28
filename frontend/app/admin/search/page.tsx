import type { Metadata } from "next";
import { SearchView } from "@/components/search/SearchView";

export const metadata: Metadata = { title: "Проверка поиска" };

export default function SearchPage() {
  return <SearchView />;
}
