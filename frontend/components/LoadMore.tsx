"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";

/** Подгрузка длинного списка: конец списка показался на экране — просим следующую порцию.
 *  Кнопка — на случай, если прокрутки нет или наблюдение не сработало. */
export function LoadMore({
  hasMore,
  loading,
  onMore,
  label = "Показать ещё",
}: {
  hasMore: boolean;
  loading: boolean;
  onMore: () => void;
  label?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !hasMore || loading) return;
    const observer = new IntersectionObserver(([entry]) => entry.isIntersecting && onMore(), {
      rootMargin: "200px",
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loading, onMore]);

  if (!hasMore) return null;
  return (
    <div ref={ref} className="flex justify-center py-3">
      {loading ? (
        <span className="inline-flex items-center gap-1.5 text-xs text-ink-3">
          <Loader2 className="size-3.5 animate-spin" />
          Загружаю…
        </span>
      ) : (
        <button
          type="button"
          onClick={onMore}
          className="rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-2 hover:text-ink"
        >
          {label}
        </button>
      )}
    </div>
  );
}

/** Сколько элементов списка просим за раз — столько же отдаёт API по умолчанию */
export const LIST_PAGE = 30;
