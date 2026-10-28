import type { Metadata } from "next";
import { Suspense } from "react";
import { DialogsView } from "@/components/dialogs/DialogsView";

export const metadata: Metadata = { title: "Диалоги" };

export default function DialogsPage() {
  // Открытый диалог — в адресе (?id=…): ссылку из уведомления в Telegram можно открыть сразу
  return (
    <Suspense>
      <DialogsView />
    </Suspense>
  );
}
