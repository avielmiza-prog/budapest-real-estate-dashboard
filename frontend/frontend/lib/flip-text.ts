"use client";

import { useEffect, useState } from "react";

/**
 * Texts for the simple deal view and the flip breakdown, in English and
 * Russian. Language: the same "lang"/"locale" choice the rest of the app
 * stores (if any), else the browser language. When merged into the main
 * i18n dictionary these keys can move there one-to-one.
 */
const TEXT = {
  en: {
    tabBuy: "Worth buying",
    tabConsider: "Buy or negotiate",
    tabAll: "All listings",
    verdictBuy: "Buy",
    verdictConsider: "Negotiate",
    verdictSkip: "Skip",
    offerUpTo: "Offer up to",
    noOffer: "Doesn't pay off at any price",
    askingAbove: "asking is {n}% above",
    askingBelow: "asking is {n}% below",
    netProfit: "Profit after tax",
    roi: "Return",
    perYear: "per year",
    months: "months",
    cashNeeded: "Total cash needed",
    sellFor: "Expected sale price",
    renovation: "Renovation",
    priceDrop: "Price dropped {n}%",
    stale: "Ad not seen for 3+ weeks",
    confidenceLow: "Rough estimate",
    confidenceMedium: "Estimate",
    showMore: "Show more ({n} more)",
    loading: "Loading...",
    wakingUp: "The server is waking up (free plan, ~30-50 seconds). Please wait...",
    lastScan: "Last scan",
    hoursAgo: "{n} h ago",
    daysAgo: "{n} days ago",
    justNow: "just now",
    staleData: "Data is more than 2 days old. The automatic scan may have stopped.",
    countOf: "{shown} of {total}",
    noDealsBuy: "No listing clears the 15% profit bar right now. Try the \"Buy or negotiate\" tab.",
    noDeals: "No listings match these filters.",
    moreFilters: "Filters",
    simpleView: "Simple",
    breakdownTitle: "Flip calculation (realistic)",
    purchase: "Purchase price",
    purchaseCosts: "Transfer tax 4% + lawyer 1.5%",
    reno: "Renovation ({scope})",
    contingency: "Reserve for surprises (15%)",
    holding: "Holding costs, {n} months",
    totalCash: "Total cash needed",
    salePrice: "Sale price after renovation",
    saleCosts: "Agent fee 3%",
    tax: "Income tax on the gain 15%",
    net: "Net profit",
    scopeFull: "full",
    scopeMedium: "medium",
    scopeRefresh: "refresh only",
    scopeNone: "none",
    whyLow: "Why it's an estimate:",
    exitBasis: "Sale price basis",
    maxOfferExplain: "Highest price that still leaves a 15% return after all costs and tax.",
    advanced: "Advanced analysis",
    reason_fallback_benchmark: "Sale price uses published 2026 district averages: fewer than 10 live renovated listings here yet",
    reason_no_condition: "The ad doesn't state the condition; average condition assumed",
    reason_no_building_type: "Building type (brick / panel) unknown",
    reason_above_renovated_market: "Asking price per m² is already above the renovated market price",
    myTake: "My assessment",
    takeBuy: "At the asking price this works as a flip: about {profit} profit after tax.",
    takeConsider: "Works only after negotiating: offer around {offer} (the asking price is {gap}% higher).",
    takeConsiderNoGap: "Borderline. Worth a viewing, but the margin is thin.",
    takeSkip: "Not a flip at this price. It would have to come down to about {offer} ({gap}% less).",
    takeSkipNever: "Not a flip: even at a much lower price the renovation doesn't pay back.",
    takeBlocker: "A legal or ownership issue in the ad. Check it with a lawyer before looking at any numbers.",
    takeData: "How reliable: {conf}.",
    confHigh: "good (enough live listings in this district)",
    confMedium: "medium",
    confLow: "low, treat as a rough estimate",
    priceAdj: "These flags lower the expected sale price by {n}%.",
    flag_basement: "Basement flat: sells well below the district price and is hard to resell",
    flag_ground_floor: "Ground floor: usually sells about 5% cheaper",
    flag_no_elevator_high_floor: "High floor without an elevator: smaller pool of buyers",
    flag_upper_floor_elevator: "Upper floor with an elevator",
    flag_usufruct: "Usufruct (haszonélvezet): someone has the right to live there",
    flag_municipal_rights: "Municipal flat or rental rights: not a normal purchase",
    flag_auction: "Auction / enforcement sale",
    flag_co_ownership: "Undivided co-ownership or a share of a property",
    flag_tenant_inside: "Sold with a tenant inside",
    flag_not_registered: "Something not registered / built without a permit",
    flag_loft_unbuilt: "Loft conversion potential mentioned: check if it's legal and permitted",
    flag_needs_structural: "Possible structural or damp issues mentioned",
    flag_ground_floor_text: "Described as ground floor",
    flag_semi_basement_text: "Described as (semi-)basement",
    flag_street_noise: "Busy road or tram noise mentioned",
    flag_panel_program: "Building went through the panel renovation program",
    flag_unencumbered: "Free of encumbrances (tehermentes)",
    reason_unusual_size: "Unusual size (under 18 or over 150 m²): probably a house or a whole building, check by hand",
  },
  ru: {
    tabBuy: "Стоит покупать",
    tabConsider: "Купить или торговаться",
    tabAll: "Все объявления",
    verdictBuy: "Покупать",
    verdictConsider: "Торговаться",
    verdictSkip: "Пропустить",
    offerUpTo: "Предлагать до",
    noOffer: "Не окупается ни по какой цене",
    askingAbove: "цена выше на {n}%",
    askingBelow: "цена ниже на {n}%",
    netProfit: "Прибыль после налога",
    roi: "Доходность",
    perYear: "в год",
    months: "мес.",
    cashNeeded: "Всего нужно денег",
    sellFor: "Ожидаемая цена продажи",
    renovation: "Ремонт",
    priceDrop: "Цена снижена на {n}%",
    stale: "Объявление не видно 3+ недели",
    confidenceLow: "Грубая оценка",
    confidenceMedium: "Оценка",
    showMore: "Показать ещё ({n})",
    loading: "Загрузка...",
    wakingUp: "Сервер просыпается (бесплатный тариф, ~30-50 секунд). Подождите...",
    lastScan: "Последнее сканирование",
    hoursAgo: "{n} ч назад",
    daysAgo: "{n} дн. назад",
    justNow: "только что",
    staleData: "Данные старше 2 дней. Возможно, автоматическое сканирование остановилось.",
    countOf: "{shown} из {total}",
    noDealsBuy: "Сейчас нет квартир с доходностью выше 15%. Посмотрите вкладку «Купить или торговаться».",
    noDeals: "Нет объявлений по этим фильтрам.",
    moreFilters: "Фильтры",
    simpleView: "Просто",
    breakdownTitle: "Расчёт флипа (реалистичный)",
    purchase: "Цена покупки",
    purchaseCosts: "Налог на покупку 4% + юрист 1,5%",
    reno: "Ремонт ({scope})",
    contingency: "Резерв на сюрпризы (15%)",
    holding: "Расходы на содержание, {n} мес.",
    totalCash: "Всего нужно денег",
    salePrice: "Цена продажи после ремонта",
    saleCosts: "Комиссия агенту 3%",
    tax: "Налог на доход 15%",
    net: "Чистая прибыль",
    scopeFull: "полный",
    scopeMedium: "средний",
    scopeRefresh: "косметика",
    scopeNone: "без ремонта",
    whyLow: "Почему это оценка:",
    exitBasis: "Основа цены продажи",
    maxOfferExplain: "Максимальная цена, при которой после всех расходов и налога остаётся 15% доходности.",
    advanced: "Подробный анализ",
    reason_fallback_benchmark: "Цена продажи по опубликованным средним за 2026 год: в районе пока меньше 10 живых объявлений с ремонтом",
    reason_no_condition: "В объявлении не указано состояние; принято среднее",
    reason_no_building_type: "Тип дома (кирпич / панель) неизвестен",
    reason_above_renovated_market: "Цена за м² уже выше, чем у квартир с ремонтом",
    myTake: "Моя оценка",
    takeBuy: "По запрашиваемой цене флип имеет смысл: около {profit} прибыли после налога.",
    takeConsider: "Имеет смысл только после торга: предлагать около {offer} (запрашиваемая цена выше на {gap}%).",
    takeConsiderNoGap: "На грани. Стоит посмотреть, но маржа небольшая.",
    takeSkip: "По этой цене не флип. Цена должна опуститься примерно до {offer} (на {gap}% меньше).",
    takeSkipNever: "Не флип: ремонт не окупается даже при намного более низкой цене.",
    takeBlocker: "В объявлении есть юридическая проблема или проблема с собственностью. Проверьте с юристом до любых расчётов.",
    takeData: "Надёжность: {conf}.",
    confHigh: "хорошая (в районе достаточно живых объявлений)",
    confMedium: "средняя",
    confLow: "низкая, это грубая оценка",
    priceAdj: "Эти факторы снижают ожидаемую цену продажи на {n}%.",
    flag_basement: "Квартира в подвале: продаётся заметно дешевле района и тяжело перепродаётся",
    flag_ground_floor: "Первый этаж: обычно дешевле примерно на 5%",
    flag_no_elevator_high_floor: "Высокий этаж без лифта: меньше покупателей",
    flag_upper_floor_elevator: "Верхний этаж с лифтом",
    flag_usufruct: "Право пожизненного проживания (haszonélvezet)",
    flag_municipal_rights: "Муниципальная квартира или право аренды: не обычная покупка",
    flag_auction: "Аукцион / принудительная продажа",
    flag_co_ownership: "Долевая собственность или продажа доли",
    flag_tenant_inside: "Продаётся с жильцом",
    flag_not_registered: "Что-то не зарегистрировано / построено без разрешения",
    flag_loft_unbuilt: "Упоминается мансарда под застройку: проверить законность и разрешения",
    flag_needs_structural: "Упоминаются возможные проблемы с конструкцией или сыростью",
    flag_ground_floor_text: "В описании указан первый этаж",
    flag_semi_basement_text: "В описании указан (полу)подвал",
    flag_street_noise: "Упоминается шумная улица или трамвай",
    flag_panel_program: "Дом прошёл программу реновации панельных домов",
    flag_unencumbered: "Без обременений (tehermentes)",
    reason_unusual_size: "Необычный размер (меньше 18 или больше 150 м²): вероятно, дом или целое здание, проверить вручную",
  },
} as const;

export type FlipTextKey = keyof (typeof TEXT)["en"];
export type FlipLang = keyof typeof TEXT;

function detectLang(): FlipLang {
  if (typeof window === "undefined") return "en";
  try {
    for (const key of ["lang", "locale", "language", "i18n-lang"]) {
      const v = window.localStorage.getItem(key);
      if (v) return v.toLowerCase().startsWith("ru") ? "ru" : "en";
    }
  } catch {
    /* storage unavailable */
  }
  const htmlLang = document.documentElement.lang;
  if (htmlLang) return htmlLang.toLowerCase().startsWith("ru") ? "ru" : "en";
  return navigator.language?.toLowerCase().startsWith("ru") ? "ru" : "en";
}

export function useFlipText() {
  const [lang, setLang] = useState<FlipLang>("en");
  useEffect(() => {
    setLang(detectLang());
    const onStorage = () => setLang(detectLang());
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return (key: FlipTextKey, vars: Record<string, string | number> = {}) => {
    let s: string = TEXT[lang][key];
    for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
    return s;
  };
}
