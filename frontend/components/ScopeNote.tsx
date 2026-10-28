import { FlaskConical, Users } from "lucide-react";
import type { ReactNode } from "react";

/** Кого касаются изменения на странице: только гостя (его песочница) или всех клиентов бота. */
export function ScopeNote({ owner, guest, clinic }: { owner: boolean; guest: ReactNode; clinic: ReactNode }) {
  return (
    <div
      className={`mt-3 flex max-w-2xl items-start gap-3 rounded-2xl border px-4 py-3 ${
        owner ? "border-warn/25 bg-warn-soft" : "border-accent/25 bg-accent-soft/70"
      }`}
    >
      <span
        className={`grid size-8 shrink-0 place-items-center rounded-xl ${
          owner ? "bg-warn/10 text-warn" : "bg-accent/10 text-accent"
        }`}
      >
        {owner ? <Users className="size-4" /> : <FlaskConical className="size-4" />}
      </span>
      <div className="text-sm leading-relaxed">
        <p className="font-semibold text-ink">{owner ? "Изменения для всех клиентов" : "Изменения видите только вы"}</p>
        <p className="mt-0.5 text-ink-2">{owner ? clinic : guest}</p>
      </div>
    </div>
  );
}
