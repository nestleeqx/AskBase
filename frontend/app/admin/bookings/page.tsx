import type { Metadata } from "next";
import { BookingsView } from "@/components/bookings/BookingsView";

export const metadata: Metadata = { title: "Заявки на запись" };

export default function BookingsPage() {
  return <BookingsView />;
}
