import { redirect } from "next/navigation";

/** Лендинг сервиса появится позже, пока главная ведёт в админку. */
export default function Home() {
  redirect("/admin/dialogs");
}
