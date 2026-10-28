import { FileText, FileType2, Globe, ScrollText } from "lucide-react";
import type { DocKind } from "@/lib/types";

const STYLES: Record<DocKind, { icon: typeof FileText; className: string }> = {
  pdf: { icon: FileText, className: "bg-danger-soft text-danger" },
  docx: { icon: FileType2, className: "bg-info-soft text-info" },
  txt: { icon: ScrollText, className: "bg-sunken text-ink-2" },
  url: { icon: Globe, className: "bg-accent-soft text-accent" },
};

/** Плитка с форматом документа: PDF, DOCX, TXT или страница сайта. */
export function DocIcon({ kind, size = "md" }: { kind: DocKind; size?: "sm" | "md" }) {
  const { icon: Icon, className } = STYLES[kind];
  return (
    <span
      className={`grid shrink-0 place-items-center ${size === "sm" ? "size-7 rounded-lg" : "size-10 rounded-xl"} ${className}`}
    >
      <Icon className={size === "sm" ? "size-3.5" : "size-4.5"} />
    </span>
  );
}
