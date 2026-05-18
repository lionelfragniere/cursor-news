const GCP_DATA_BASE_URL = "https://storage.googleapis.com/cursor-news-radio-20260517-audio/current";
const APP_TIME_ZONE = "Europe/Zurich";

const state = {
  articles: [],
  generatedAt: null,
  filters: {
    query: "",
    region: "all",
    source: "all",
    period: "all",
    sort: "newest",
  },
};

const els = {
  status: document.querySelector("#archive-status"),
  search: document.querySelector("#archive-search"),
  region: document.querySelector("#archive-region"),
  source: document.querySelector("#archive-source"),
  period: document.querySelector("#archive-period"),
  sort: document.querySelector("#archive-sort"),
  reset: document.querySelector("#archive-reset"),
  title: document.querySelector("#archive-title"),
  list: document.querySelector("#archive-list"),
};

function normalize(value) {
  return (value || "")
    .toString()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function formatDate(value) {
  if (!value) return "Date inconnue";
  return new Intl.DateTimeFormat("fr-CH", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function fillSelect(select, values, firstLabel) {
  select.replaceChildren(
    new Option(firstLabel, "all"),
    ...values.map((value) => new Option(value, value)),
  );
}

function setupFilters(payload) {
  fillSelect(els.region, payload.regions || [], "Toutes les régions");
  fillSelect(els.source, payload.sources || [], "Toutes les sources");
  [els.search, els.region, els.source, els.period, els.sort].forEach((el) => {
    el.addEventListener("input", updateFromControls);
    el.addEventListener("change", updateFromControls);
  });
  els.reset.addEventListener("click", resetFilters);
}

function updateFromControls() {
  state.filters = {
    query: els.search.value.trim(),
    region: els.region.value,
    source: els.source.value,
    period: els.period.value,
    sort: els.sort.value,
  };
  render();
}

function resetFilters() {
  els.search.value = "";
  els.region.value = "all";
  els.source.value = "all";
  els.period.value = "all";
  els.sort.value = "newest";
  updateFromControls();
}

function filteredArticles() {
  const query = normalize(state.filters.query);
  const filtered = state.articles.filter((article) => {
    if (state.filters.region !== "all" && article.region !== state.filters.region) return false;
    if (state.filters.source !== "all" && article.source_name !== state.filters.source) return false;
    if (!matchesPeriod(article)) return false;
    if (!query) return true;
    const haystack = normalize(`${article.title} ${article.summary} ${article.source_name} ${article.region}`);
    return haystack.includes(query);
  });

  return filtered.sort((a, b) => {
    if (state.filters.sort === "romand") {
      return b.priority - a.priority || dateValue(b) - dateValue(a);
    }
    if (state.filters.sort === "calm") {
      return a.tension - b.tension || b.calm - a.calm || dateValue(b) - dateValue(a);
    }
    if (state.filters.sort === "alert") {
      return b.tension - a.tension || dateValue(b) - dateValue(a);
    }
    return dateValue(b) - dateValue(a);
  });
}

function articleDate(article) {
  const value = article.published_at || article.scraped_at;
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateValue(article) {
  const date = articleDate(article);
  return date ? date.getTime() : 0;
}

function zonedDateKey(date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: APP_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function matchesPeriod(article) {
  if (state.filters.period === "all") return true;
  const date = articleDate(article);
  if (!date) return false;
  const now = new Date();
  if (state.filters.period === "today") {
    return zonedDateKey(date) === zonedDateKey(now);
  }
  if (state.filters.period === "24h") {
    return date.getTime() >= now.getTime() - 24 * 60 * 60 * 1000;
  }
  if (state.filters.period === "7d") {
    return date.getTime() >= now.getTime() - 7 * 24 * 60 * 60 * 1000;
  }
  return true;
}

function render() {
  const items = filteredArticles();
  els.title.textContent = `${items.length} article${items.length > 1 ? "s" : ""}`;
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Aucun article ne correspond à la recherche.";
    els.list.replaceChildren(empty);
    return;
  }
  els.list.replaceChildren(...items.slice(0, 200).map(renderArticle));
}

function renderArticle(article) {
  const item = document.createElement("article");
  item.className = "news-item";

  const title = document.createElement("a");
  title.className = "news-title";
  title.href = article.url;
  title.target = "_blank";
  title.rel = "noreferrer";
  title.textContent = article.title;

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${article.source_name} · ${formatDate(article.published_at || article.scraped_at)}`;

  const summary = document.createElement("p");
  summary.className = "summary";
  summary.textContent = article.summary || "Résumé indisponible.";

  const tags = document.createElement("div");
  tags.className = "tags";
  tags.append(tag(article.region), tag(`tension ${article.tension}/10`), tag(`focus ${article.priority}`));
  if (article.child_friendly) tags.append(tag("enfants"));
  if (article.status === "used") tags.append(tag("bulletin"));

  item.append(title, meta, summary, tags);
  return item;
}

function tag(text) {
  const span = document.createElement("span");
  span.className = "tag";
  span.textContent = text;
  return span;
}

async function init() {
  try {
    const response = await fetch(`${GCP_DATA_BASE_URL}/news.json?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const payload = await response.json();
    state.generatedAt = payload.generated_at || null;
    state.articles = payload.articles || [];
    els.status.textContent = `${state.articles.length} articles · ${formatDate(state.generatedAt)}`;
    setupFilters(payload);
    updateFromControls();
  } catch (error) {
    els.status.textContent = "Archives indisponibles";
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Impossible de charger les archives pour le moment.";
    els.list.replaceChildren(empty);
  }
}

init();
