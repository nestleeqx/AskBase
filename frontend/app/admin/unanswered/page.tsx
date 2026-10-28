import type { Metadata } from "next";
import { UnansweredView } from "@/components/unanswered/UnansweredView";

export const metadata: Metadata = { title: "Бот не смог ответить" };

export default function Page() {
  return <UnansweredView />;
}
