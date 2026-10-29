import type { Metadata } from "next";
import { Suspense } from "react";
import { BookingsView } from "@/components/bookings/BookingsView";

export const metadata: Metadata = { title: "Заявки на запись" };

export default function BookingsPage() {
  // Заявка из диалога или уведомления — в адресе (?id=…): страница прокрутит к ней и подсветит
  return (
    <Suspense>
      <BookingsView />
    </Suspense>
  );
}
