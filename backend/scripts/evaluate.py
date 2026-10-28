"""Прогон тестового набора через бота и сверка с эталоном — цифра точности для портфолио.

    uv run python scripts/evaluate.py --report ../../portfolio-assets/askbase/eval-report.html

Что делает:
- задаёт боту 20 вопросов по документам и 5 вопросов вне базы из app/seed/eval-questions.json
  тем же конвейером, что в чате и Telegram: уточнение по истории → поиск → ответ нейросети;
- по документам: ответ верный, если в нём есть все ключевые факты эталона и он сослался
  на нужный документ; вне базы — если бот не ответил сам, а передал вопрос администратору;
- замеряет время ответа (вопросы идут по одному, как в жизни);
- сохраняет ответы в app/seed/eval-results.json и собирает HTML-отчёт для ручной проверки.

Нужны база с проиндексированной демо-базой (docker compose up -d) и ключ в .env.
Кеш — в памяти процесса, поэтому каждый прогон идёт через модель заново.
--from-saved пересобирает отчёт из сохранённых ответов без обращения к модели.
"""

import argparse
import asyncio
import html
import json
import re
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

import fakeredis
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.embeddings import create_embedder  # noqa: E402
from app.llm import create_provider  # noqa: E402
from app.models import Document  # noqa: E402
from app.services.answer import REASONS, answer_question, sources_line  # noqa: E402
from app.services.seed import ensure_seed  # noqa: E402

SEED_DIR = Path(__file__).resolve().parents[1] / "app" / "seed"
QUESTIONS = SEED_DIR / "eval-questions.json"
RESULTS = SEED_DIR / "eval-results.json"
VISITOR = "eval-visitor-0001"


def norm(text: str) -> str:
    text = text.lower().replace("ё", "е").replace(" ", " ").replace(" ", " ")
    text = re.sub(r"(?<=\d) (?=\d{3}\b)", "", text)
    return re.sub(r"\s+", " ", text)


def has(text: str, alias: str) -> bool:
    """Варианты до 3 символов — отдельным словом, длиннее — как часть слова (правила набора)."""
    a = norm(alias)
    if len(a) <= 3:
        return re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", text) is not None
    return a in text


def check(q: dict, r: dict) -> dict:
    if q.get("handoff"):
        return {"correct": not r["answered"], "facts": [], "sources_ok": None}
    text = norm(r["text"])
    facts = [any(has(text, a) for a in group) for group in q["facts"]]
    keys = set(r["source_keys"])
    sources_ok = all(any(k in keys for k in group) for group in q["sources"])
    return {
        "correct": r["answered"] and all(facts) and sources_ok,
        "facts": facts,
        "sources_ok": sources_ok,
    }


async def run() -> dict:
    settings = get_settings()
    llm = create_provider(settings)
    embedder = create_embedder(settings)
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    await init_db()
    await ensure_seed(SessionLocal, embedder, redis)
    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))

    results = []
    async with SessionLocal() as session:
        seed_keys = {
            d.id: d.seed_key for d in await session.scalars(select(Document)) if d.seed_key
        }
        for q in data["questions"]:
            history = [(m["role"], m["text"]) for m in q.get("history", [])]
            res = await answer_question(
                session, llm, embedder, redis, q["question"], history, VISITOR
            )
            used = set(res.used_chunk_ids)
            r = {
                "id": q["id"],
                "answered": res.answered,
                "text": res.text,
                "sources": [s.title for s in res.sources],
                "source_keys": [seed_keys.get(s.id, "") for s in res.sources],
                "query": res.query,
                "reason": res.reason,
                "topic": res.topic,
                "ms": res.total_ms,
                "search_ms": res.search_ms,
                "llm_ms": res.llm_ms,
                "hits": [
                    {
                        "title": h.document.title,
                        "heading": h.chunk.heading,
                        "similarity": round(h.similarity, 3),
                        "used": h.chunk.id in used,
                        "text": h.chunk.text,
                    }
                    for h in res.hits
                ],
            }
            r["check"] = check(q, r)
            mark = "✓" if r["check"]["correct"] else "✗"
            print(f"{mark} {q['id']:>2} {res.total_ms:>5} мс  {q['question']}")
            results.append(r)
    await llm.aclose()
    await embedder.aclose()
    return {
        "model": f"{llm.name}:{llm.model}",
        "embeddings": embedder.model_id,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": results,
    }


def summary(run_data: dict, questions: list[dict]) -> dict:
    by_id = {q["id"]: q for q in questions}
    in_base = [r for r in run_data["results"] if not by_id[r["id"]].get("handoff")]
    out_base = [r for r in run_data["results"] if by_id[r["id"]].get("handoff")]
    times = sorted(r["ms"] for r in run_data["results"])
    p95 = times[min(len(times) - 1, round(0.95 * (len(times) - 1)))]
    return {
        "in_ok": sum(r["check"]["correct"] for r in in_base),
        "in_total": len(in_base),
        "out_ok": sum(r["check"]["correct"] for r in out_base),
        "out_total": len(out_base),
        "median_ms": round(statistics.median(times)),
        "p95_ms": p95,
        "max_ms": times[-1],
        "under_5s": sum(t <= 5000 for t in times),
        "total": len(times),
    }


# --- HTML-отчёт ---

CSS = """
:root{--accent:#0d9488;--soft:#e3f5f2;--ink:#10201f;--ink2:#465755;--ink3:#869593;--line:#e1e8e7;
--ok:#16a34a;--oksoft:#e7f6ec;--bad:#c2362b;--badsoft:#fdecea;--warn:#a45a07;--warnsoft:#fcf1df}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Arial,sans-serif;color:var(--ink);
background:#f3f6f6;line-height:1.5}.wrap{max-width:1180px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:26px;margin:0 0 4px}.muted{color:var(--ink2);font-size:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:22px 0}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px}
.card b{display:block;font-size:30px;line-height:1.1}.card span{color:var(--ink2);font-size:13px}
table{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1px solid var(--line);
border-radius:16px;overflow:hidden}th,td{text-align:left;vertical-align:top;padding:12px;
border-bottom:1px solid var(--line);font-size:14px}th{font-size:12px;color:var(--ink3);font-weight:600}
tr:last-child td{border-bottom:0}.q{font-weight:600}.hist{color:var(--ink3);font-size:12px}
.kind{color:var(--ink3);font-size:12px;margin-top:4px}.ans{white-space:pre-line}
.src{color:var(--accent);font-size:12px;margin-top:4px}.pill{display:inline-block;border-radius:8px;
padding:2px 8px;font-size:12px;font-weight:600;white-space:nowrap}.ok{background:var(--oksoft);color:var(--ok)}
.bad{background:var(--badsoft);color:var(--bad)}.ho{background:var(--warnsoft);color:var(--warn)}
details{margin-top:6px;font-size:12px;color:var(--ink2)}summary{cursor:pointer;color:var(--accent)}
.hit{border-left:3px solid var(--line);padding:4px 8px;margin:6px 0;white-space:pre-line}
.hit.used{border-color:var(--accent);background:var(--soft)}.sep td{background:#f8fbfa;font-weight:600;
color:var(--ink2);font-size:13px}.facts span{margin-right:4px}
@media (max-width:760px){table,tbody,tr,td{display:block}thead{display:none}td{border:0;padding:6px 12px}
tr{border-bottom:1px solid var(--line);padding:8px 0}}
"""


def esc(text: str) -> str:
    return html.escape(text or "")


def render(run_data: dict, questions_data: dict) -> str:
    questions = questions_data["questions"]
    s = summary(run_data, questions)
    results = {r["id"]: r for r in run_data["results"]}
    rows = []
    for q in questions:
        r = results[q["id"]]
        if q["id"] == 21:
            rows.append(
                '<tr class="sep"><td colspan="5">Вопросы вне базы — бот должен передать их администратору</td></tr>'
            )
        elif q["id"] == 1:
            rows.append('<tr class="sep"><td colspan="5">Вопросы по документам клиники</td></tr>')
        hist = "".join(
            f'<div class="hist">{"Клиент" if m["role"] == "user" else "Бот"}: {esc(m["text"])}</div>'
            for m in q.get("history", [])
        )
        expected = (
            '<span class="pill ho">Передать администратору</span>'
            if q.get("handoff")
            else esc(q["expected"])
        )
        answer = esc(r["text"])
        if r["sources"]:
            answer += f'<div class="src">{esc(sources_line(r["sources"]))}</div>'
        if r["query"] != q["question"]:
            answer += f'<div class="kind">Искал: «{esc(r["query"])}»</div>'
        hits = "".join(
            f'<div class="hit{" used" if h["used"] else ""}"><b>{esc(h["title"])}'
            f"{' — ' + esc(h['heading']) if h['heading'] and h['heading'] != h['title'] else ''}"
            f"</b> · близость {h['similarity']:.2f}{' · в ответе' if h['used'] else ''}\n{esc(h['text'])}</div>"
            for h in r["hits"]
        )
        if hits:
            answer += f"<details><summary>Найденные фрагменты ({len(r['hits'])})</summary>{hits}</details>"
        c = r["check"]
        if q.get("handoff"):
            verdict = (
                '<span class="pill ok">Передал</span>'
                if c["correct"]
                else '<span class="pill bad">Ответил сам</span>'
            )
            detail = esc(REASONS.get(r["reason"], ""))
        else:
            verdict = (
                '<span class="pill ok">Верно</span>'
                if c["correct"]
                else '<span class="pill bad">Ошибка</span>'
            )
            if not r["answered"]:
                detail = "Не ответил: " + esc(REASONS.get(r["reason"], "")).lower()
            else:
                facts = "".join(
                    f'<span title="{esc(" / ".join(g))}">{"✓" if ok else "✗"} {esc(g[0])}</span>'
                    for g, ok in zip(q["facts"], c["facts"], strict=True)
                )
                detail = (
                    f'<div class="facts">{facts}</div>Источник {"✓" if c["sources_ok"] else "✗"}'
                )
        rows.append(
            f'<tr><td>{q["id"]}</td><td>{hist}<div class="q">{esc(q["question"])}</div>'
            f'<div class="kind">{esc(q["kind"])}</div></td><td>{expected}</td>'
            f'<td><div class="ans">{answer}</div></td>'
            f'<td>{verdict}<div class="kind">{detail}</div>'
            f'<div class="kind">{f"{r['ms'] / 1000:.1f}".replace(".", ",")} с</div></td></tr>'
        )

    date = datetime.fromisoformat(run_data["date"]).strftime("%d.%m.%Y")
    cards = [
        (f"{s['in_ok']} из {s['in_total']}", "верных ответов по документам"),
        (f"{s['out_ok']} из {s['out_total']}", "вопросов вне базы переданы администратору"),
        (
            f"{s['median_ms'] / 1000:.1f} с".replace(".", ","),
            f"медиана ответа · 95% — до {s['p95_ms'] / 1000:.1f} с".replace(".", ","),
        ),
        (f"{s['under_5s']} из {s['total']}", "ответов быстрее 5 секунд"),
    ]
    cards_html = "".join(f'<div class="card"><b>{a}</b><span>{b}</span></div>' for a, b in cards)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AskBase — проверка точности</title><style>{CSS}</style></head><body><div class="wrap">
<h1>AskBase — проверка точности ответов</h1>
<p class="muted">Стоматология «Белая линия» (демо) · {date} · модель {esc(run_data["model"])},
эмбеддинги {esc(run_data["embeddings"])}. Набор из 25 вопросов составлен до настройки бота.
Ответ верный, если в нём есть все ключевые факты эталона и бот сослался на нужный документ.</p>
<div class="cards">{cards_html}</div>
<table><thead><tr><th>#</th><th>Вопрос</th><th>Верный ответ</th><th>Ответ бота</th><th>Проверка</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--report", type=Path, help="куда сохранить HTML-отчёт")
    parser.add_argument("--from-saved", action="store_true", help="не вызывать модель")
    args = parser.parse_args()

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if args.from_saved:
        run_data = json.loads(RESULTS.read_text(encoding="utf-8"))
        # Проверка могла поменяться — пересчитываем по сохранённым ответам
        by_id = {q["id"]: q for q in questions["questions"]}
        for r in run_data["results"]:
            r["check"] = check(by_id[r["id"]], r)
    else:
        run_data = asyncio.run(run())
        RESULTS.write_text(json.dumps(run_data, ensure_ascii=False, indent=2) + "\n", "utf-8")

    s = summary(run_data, questions["questions"])
    print(
        f"\nПо документам верно: {s['in_ok']} из {s['in_total']}. "
        f"Вне базы передано: {s['out_ok']} из {s['out_total']}. "
        f"Время: медиана {s['median_ms']} мс, 95% — {s['p95_ms']} мс, максимум {s['max_ms']} мс."
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render(run_data, questions), encoding="utf-8")
        print(f"Отчёт: {args.report.resolve()}")


if __name__ == "__main__":
    main()
