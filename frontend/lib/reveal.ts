/** На телефоне форма вверху страницы, а результат — ниже экрана: подкручиваем к нему
 *  и прячем клавиатуру. На широком экране всё видно и так — страница не прыгает. */
export function revealOnMobile(el: Element | null) {
  if (!el || !window.matchMedia("(max-width: 1023px)").matches) return;
  (document.activeElement as HTMLElement | null)?.blur();
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}
