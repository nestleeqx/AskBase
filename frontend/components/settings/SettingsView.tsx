"use client";

import { Info, RotateCcw, Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { BotSettings, BotSettingsValues, Tone } from "@/lib/types";
import { useToast } from "../Toast";
import { Button, Panel } from "../ui";

const TONE_HINTS: Record<Tone, string> = {
  neutral: "Вежливо и по делу",
  friendly: "Тепло, можно эмодзи",
  formal: "Сдержанно, без разговорных слов",
  brief: "Одно-два предложения",
};

const FIELD =
  "w-full rounded-xl border border-line bg-surface px-3.5 text-sm outline-none placeholder:text-ink-3 focus:border-accent/40 focus:ring-4 focus:ring-accent-soft";

function pick(s: BotSettings): BotSettingsValues {
  return { greeting: s.greeting, tone: s.tone, phone: s.phone, hours: s.hours };
}

function Preview({ values }: { values: BotSettingsValues }) {
  const bubble = "rounded-2xl rounded-tl-md bg-surface px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-line";
  return (
    <div className="space-y-2 rounded-2xl bg-[#d9e7e4] p-3.5" aria-label="Как это выглядит в Telegram">
      <p className={bubble}>{values.greeting || "…"}</p>
      <p className="ml-auto w-fit rounded-2xl rounded-tr-md bg-[#e1f6cb] px-3.5 py-2 text-[13px]">
        👤 Связаться с администратором
      </p>
      <p className={bubble}>
        Передал ваш запрос администратору — он ответит прямо в этом чате. Администратор на связи {values.hours}.{"\n\n"}
        Если вопрос срочный — позвоните: {values.phone}.
      </p>
    </div>
  );
}

function SettingsForm({ initial, onSaved }: { initial: BotSettings; onSaved: (s: BotSettings) => void }) {
  const toast = useToast();
  const [values, setValues] = useState<BotSettingsValues>(pick(initial));
  const [busy, setBusy] = useState<"save" | "reset" | null>(null);
  const dirty = JSON.stringify(values) !== JSON.stringify(pick(initial));

  function set<K extends keyof BotSettingsValues>(key: K, value: BotSettingsValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy("save");
    try {
      const saved = await api.saveSettings(values);
      onSaved(saved);
      setValues(pick(saved));
      toast.ok("Настройки сохранены — бот уже отвечает по-новому");
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    setBusy("reset");
    try {
      const saved = await api.resetSettings();
      onSaved(saved);
      setValues(pick(saved));
      toast.ok("Вернули настройки по умолчанию");
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <form onSubmit={save} className="mt-5 grid gap-4 xl:grid-cols-[1fr_340px]">
      <Panel className="space-y-5 p-4 sm:p-5">
        <label className="block">
          <span className="text-sm font-medium text-ink">Приветствие</span>
          <span className="mt-0.5 block text-xs text-ink-3">Первое сообщение бота в Telegram и в тестовом чате</span>
          <textarea
            value={values.greeting}
            onChange={(e) => set("greeting", e.target.value)}
            rows={5}
            minLength={10}
            maxLength={1000}
            required
            className={`mt-2 resize-y py-2.5 leading-relaxed ${FIELD}`}
          />
        </label>

        <fieldset>
          <legend className="text-sm font-medium text-ink">Тон ответов</legend>
          <span className="mt-0.5 block text-xs text-ink-3">
            Меняется только подача — факты бот по-прежнему берёт из документов
          </span>
          <div className="mt-2 grid grid-cols-2 gap-2 2xl:grid-cols-4">
            {(Object.keys(TONE_HINTS) as Tone[]).map((tone) => (
              <button
                key={tone}
                type="button"
                aria-pressed={values.tone === tone}
                onClick={() => set("tone", tone)}
                className={`rounded-xl border px-3 py-2.5 text-left transition-colors ${
                  values.tone === tone
                    ? "border-accent/50 bg-accent-soft ring-2 ring-accent/20"
                    : "border-line hover:bg-sunken"
                }`}
              >
                <span className="block text-sm font-medium text-ink">{initial.tones[tone]}</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-ink-3">{TONE_HINTS[tone]}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-ink">Телефон для срочных вопросов</span>
            <input
              value={values.phone}
              onChange={(e) => set("phone", e.target.value)}
              minLength={5}
              maxLength={40}
              required
              className={`mt-2 h-10 ${FIELD}`}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-ink">Когда администратор на связи</span>
            <input
              value={values.hours}
              onChange={(e) => set("hours", e.target.value)}
              minLength={3}
              maxLength={120}
              required
              className={`mt-2 h-10 ${FIELD}`}
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          {initial.custom && (
            <Button
              type="button"
              variant="ghost"
              loading={busy === "reset"}
              disabled={!!busy}
              onClick={reset}
              icon={<RotateCcw className="size-4" />}
            >
              Как было по умолчанию
            </Button>
          )}
          <Button
            type="submit"
            variant="primary"
            className="ml-auto"
            loading={busy === "save"}
            disabled={!dirty || !!busy}
            icon={<Save className="size-4" />}
          >
            Сохранить
          </Button>
        </div>
      </Panel>

      <div className="space-y-3">
        <p className="text-xs font-medium text-ink-2">Как это увидит клиент</p>
        <Preview values={values} />
      </div>
    </form>
  );
}

export function SettingsView() {
  const { data, mutate } = useSWR("settings", api.settings);

  return (
    <div className="mx-auto max-w-5xl px-4 py-5 sm:px-6 sm:py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Настройки бота</h1>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-2">
        Приветствие, тон ответов и контакты, которые бот называет, когда передаёт вопрос администратору.
      </p>
      <p className="mt-3 flex max-w-2xl items-start gap-2 rounded-xl bg-info-soft px-3.5 py-2.5 text-xs leading-relaxed text-ink-2">
        <Info className="mt-px size-3.5 shrink-0 text-info" />
        Это демо: ваши настройки действуют только в вашем тестовом чате и в вашем Telegram-чате, подключённом к админке.
        Другие посетители видят бота как прежде.
      </p>
      {!data ? (
        <div className="skeleton mt-5 h-96 rounded-2xl" />
      ) : (
        // key: после сброса форма начинается с новых значений
        <SettingsForm
          key={JSON.stringify(pick(data))}
          initial={data}
          onSaved={(s) => mutate(s, { revalidate: false })}
        />
      )}
    </div>
  );
}
