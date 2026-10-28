import { AdminShell } from "@/components/shell/AdminShell";

/** Админка клиники: боковое меню и верхняя панель. */
export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return <AdminShell>{children}</AdminShell>;
}
