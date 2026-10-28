import type { Metadata } from "next";
import { AnalyticsView } from "@/components/analytics/AnalyticsView";

export const metadata: Metadata = { title: "Аналитика" };

export default function Page() {
  return <AnalyticsView />;
}
