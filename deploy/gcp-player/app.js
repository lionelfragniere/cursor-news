const READ_STORAGE_KEY = "cursor-news-read-articles-v1";
const ACCESS_STORAGE_KEY = "cursor-news-accessibility-v1";
const GCP_DATA_BASE_URL = "https://storage.googleapis.com/cursor-news-radio-20260517-audio/current";
const APP_TIME_ZONE = "Europe/Zurich";

const state = {
  articles: [],
  generatedAt: null,
  readIds: new Set(),
  access: {
    largeText: false,
    highContrast: false,
  },
  filters: {
    query: "",
    region: "all",
    dateRange: "today",
    source: "all",
    sort: "newest",
    tension: 10,
    priority: 0,
    childOnly: false,
    hideSports: true,
    hideRead: true,
  },
};

const els = {
  status: document.querySelector("#data-status"),
  player: document.querySelector("#radio-player"),
  bulletinTitle: document.querySelector("#bulletin-title"),
  bulletinSummary: document.querySelector("#bulletin-summary"),
  bulletinTranscript: document.querySelector("#bulletin-transcript"),
  bulletinAudioLink: document.querySelector("#bulletin-audio-link"),
  textSize: document.querySelector("#text-size-toggle"),
  contrast: document.querySelector("#contrast-toggle"),
  search: document.querySelector("#search"),
  region: document.querySelector("#region-filter"),
  date: document.querySelector("#date-filter"),
  source: document.querySelector("#source-filter"),
  sort: document.querySelector("#sort-filter"),
  tension: document.querySelector("#tension-filter"),
  tensionValue: document.querySelector("#tension-value"),
  priority: document.querySelector("#priority-filter"),
  priorityValue: document.querySelector("#priority-value"),
  child: document.querySelector("#child-filter"),
  sports: document.querySelector("#sports-filter"),
  read: document.querySelector("#read-filter"),
  reset: document.querySelector("#reset-filters"),
  title: document.querySelector("#result-title"),
  list: document.querySelector("#news-list"),
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

function loadReadIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(READ_STORAGE_KEY) || "[]");
    return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
  } catch {
    return new Set();
  }
}

function saveReadIds() {
  localStorage.setItem(READ_STORAGE_KEY, JSON.stringify([...state.readIds]));
}

function loadAccess() {
  try {
    const parsed = JSON.parse(localStorage.getItem(ACCESS_STORAGE_KEY) || "{}");
    return {
      largeText: Boolean(parsed.largeText),
      highContrast: Boolean(parsed.highContrast),
    };
  } catch {
    return { largeText: false, highContrast: false };
  }
}

function saveAccess() {
  localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(state.access));
}

function applyAccess() {
  document.body.classList.toggle("large-text", state.access.largeText);
  document.body.classList.toggle("high-contrast", state.access.highContrast);
  els.textSize.setAttribute("aria-pressed", String(state.access.largeText));
  els.contrast.setAttribute("aria-pressed", String(state.access.highContrast));
}

function setupAccessControls() {
  state.access = loadAccess();
  applyAccess();
  els.textSize.addEventListener("click", () => {
    state.access.largeText = !state.access.largeText;
    applyAccess();
    saveAccess();
  });
  els.contrast.addEventListener("click", () => {
    state.access.highContrast = !state.access.highContrast;
    applyAccess();
    saveAccess();
  });
}

function isRead(article) {
  return state.readIds.has(String(article.id));
}

function setRead(article, read) {
  const id = String(article.id);
  if (read) state.readIds.add(id);
  else state.readIds.delete(id);
  saveReadIds();
  render();
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
  const listeners = [
    [els.search, "input"],
    [els.region, "change"],
    [els.date, "change"],
    [els.source, "change"],
    [els.sort, "change"],
    [els.tension, "input"],
    [els.priority, "input"],
    [els.child, "change"],
    [els.sports, "change"],
    [els.read, "change"],
  ];
  listeners.forEach(([el, event]) => el.addEventListener(event, updateFromControls));
  els.reset.addEventListener("click", resetFilters);
}

function updateFromControls() {
  state.filters = {
    query: els.search.value.trim(),
    region: els.region.value,
    dateRange: els.date.value,
    source: els.source.value,
    sort: els.sort.value,
    tension: Number(els.tension.value),
    priority: Number(els.priority.value),
    childOnly: els.child.checked,
    hideSports: els.sports.checked,
    hideRead: els.read.checked,
  };
  els.tensionValue.textContent = state.filters.tension;
  els.priorityValue.textContent = state.filters.priority;
  render();
}

function resetFilters() {
  els.search.value = "";
  els.region.value = "all";
  els.date.value = "today";
  els.source.value = "all";
  els.sort.value = "newest";
  els.tension.value = "10";
  els.priority.value = "0";
  els.child.checked = false;
  els.sports.checked = true;
  els.read.checked = true;
  updateFromControls();
}

function filteredArticles() {
  const query = normalize(state.filters.query);
  const filtered = state.articles.filter((article) => {
    if (state.filters.region !== "all" && article.region !== state.filters.region) return false;
    if (!matchesDateRange(article)) return false;
    if (state.filters.source !== "all" && article.source_name !== state.filters.source) return false;
    if (state.filters.hideSports && article.is_sports) return false;
    if (state.filters.hideRead && isRead(article)) return false;
    if (state.filters.childOnly && !article.child_friendly) return false;
    if (article.tension > state.filters.tension) return false;
    if (article.priority < state.filters.priority) return false;
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

function dateValue(article) {
  return new Date(article.published_at || article.scraped_at || 0).getTime();
}

function articleDate(article) {
  const value = article.published_at || article.scraped_at;
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function currentReferenceDate() {
  const date = state.generatedAt ? new Date(state.generatedAt) : new Date();
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function zonedDateKey(date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: APP_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function matchesDateRange(article) {
  if (state.filters.dateRange === "all") return true;
  const date = articleDate(article);
  if (!date) return false;
  const reference = currentReferenceDate();
  if (state.filters.dateRange === "today") {
    return zonedDateKey(date) === zonedDateKey(reference);
  }
  if (state.filters.dateRange === "24h") {
    return date.getTime() >= reference.getTime() - 24 * 60 * 60 * 1000;
  }
  if (state.filters.dateRange === "7d") {
    return date.getTime() >= reference.getTime() - 7 * 24 * 60 * 60 * 1000;
  }
  return true;
}

function render() {
  const items = filteredArticles();
  els.title.textContent = `${items.length} actualité${items.length > 1 ? "s" : ""} - ${dateRangeLabel()}`;
  updateStatus();
  if (!items.length) {
    els.list.replaceChildren(emptyState());
    return;
  }
  els.list.replaceChildren(...items.slice(0, 80).map(renderArticle));
}

function renderArticle(article) {
  const item = document.createElement("article");
  item.className = "news-item";
  if (isRead(article)) item.classList.add("read");

  const main = document.createElement("div");
  main.className = "news-main";

  const title = document.createElement("a");
  title.className = "news-title";
  title.href = article.url;
  title.target = "_blank";
  title.rel = "noreferrer";
  title.textContent = article.title;
  title.addEventListener("click", () => {
    setRead(article, true);
  });

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${article.source_name} · ${formatDate(article.published_at || article.scraped_at)}`;

  const summary = document.createElement("p");
  summary.className = "summary";
  summary.textContent = article.summary || "Résumé indisponible.";

  const tags = document.createElement("div");
  tags.className = "tags";
  tags.append(
    tag(article.region),
    tag(`tension ${article.tension}/10`, article.tension >= 4 ? "alert" : ""),
    tag(`focus ${article.priority}`),
  );
  if (article.child_friendly) tags.append(tag("enfants"));
  if (article.is_sports) tags.append(tag("sport", "alert"));
  if (article.status === "used") tags.append(tag("bulletin"));

  const readToggle = document.createElement("label");
  readToggle.className = "read-toggle";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = isRead(article);
  checkbox.addEventListener("change", () => setRead(article, checkbox.checked));
  const readLabel = document.createElement("span");
  readLabel.textContent = "Lu";
  readToggle.append(checkbox, readLabel);

  main.append(title, meta, summary, tags);
  item.append(main, readToggle);
  return item;
}

function tag(text, className = "") {
  const span = document.createElement("span");
  span.className = `tag ${className}`.trim();
  span.textContent = text;
  return span;
}

function emptyState() {
  const div = document.createElement("div");
  div.className = "empty";
  div.textContent = "Aucune actualité ne correspond aux filtres. Essaie une autre période ou allège les filtres.";
  return div;
}

function dateRangeLabel() {
  if (state.filters.dateRange === "today") return "aujourd'hui";
  if (state.filters.dateRange === "24h") return "24 dernières heures";
  if (state.filters.dateRange === "7d") return "7 derniers jours";
  return "tout l'historique";
}

function renderManifest(manifest) {
  const current = manifest?.current;
  if (!current) {
    els.bulletinTitle.textContent = "Aucun bulletin publié";
    els.bulletinSummary.textContent = "";
    els.bulletinTranscript.replaceChildren();
    return;
  }
  const audioUrl = `${current.audio_url}?v=${encodeURIComponent(manifest.generated_at || Date.now())}`;
  if (els.player.getAttribute("src") !== audioUrl) {
    els.player.src = audioUrl;
  }
  els.bulletinAudioLink.href = current.archive_audio_url || current.audio_url;
  els.bulletinTitle.textContent = `${current.title} · ${current.style}`;
  els.bulletinSummary.textContent = current.summary || "";
  const paragraphs = (current.transcript || "")
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  els.bulletinTranscript.replaceChildren(
    ...paragraphs.map((part) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = part;
      return paragraph;
    }),
  );
}

function updateStatus() {
  const total = state.articles.length;
  const readCount = state.articles.filter(isRead).length;
  const date = state.generatedAt ? ` · ${formatDate(state.generatedAt)}` : "";
  els.status.textContent = `${total} news · ${readCount} lue${readCount > 1 ? "s" : ""}${date}`;
}

async function init() {
  setupAccessControls();
  try {
    const [manifestResponse, response] = await Promise.all([
      fetch(`${GCP_DATA_BASE_URL}/manifest.json?v=${Date.now()}`, { cache: "no-store" }),
      fetch(`${GCP_DATA_BASE_URL}/news.json?v=${Date.now()}`, { cache: "no-store" }),
    ]);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    if (manifestResponse.ok) renderManifest(await manifestResponse.json());
    const payload = await response.json();
    state.generatedAt = payload.generated_at || null;
    state.readIds = loadReadIds();
    state.articles = payload.articles || [];
    setupFilters(payload);
    updateFromControls();
  } catch (error) {
    els.status.textContent = "News indisponibles";
    els.list.replaceChildren(emptyState());
  }
}

init();
