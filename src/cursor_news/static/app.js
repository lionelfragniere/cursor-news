const player = document.querySelector("#player");
const currentTitle = document.querySelector("#current-title");
const currentSlot = document.querySelector("#current-slot");
const currentSummary = document.querySelector("#current-summary");
const currentTranscript = document.querySelector("#current-transcript");
const currentSources = document.querySelector("#current-sources");
const pipelineStatus = document.querySelector("#pipeline-status");
const playbackMode = document.querySelector("#playback-mode");
const liveButton = document.querySelector("#live-button");
const streamPanel = document.querySelector("#infomaniak-live");
const streamPlayer = document.querySelector("#stream-player");
const streamStatus = document.querySelector("#stream-status");
const streamLink = document.querySelector("#stream-link");
const historyEl = document.querySelector("#history");
const articleArchiveEl = document.querySelector("#article-archive");
const metricsEl = document.querySelector("#metrics");
const historyLimit = 5;
const articleArchiveLimit = 20;
let selectedBulletinId = null;
let manualSelection = false;
let hlsController = null;

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function formatDate(value) {
  if (!value) return "--:--";
  return new Intl.DateTimeFormat("fr-CH", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function renderStream(stream) {
  if (!stream?.enabled || !stream.url) {
    streamPanel.hidden = true;
    return;
  }

  streamPanel.hidden = false;
  streamLink.href = stream.url;

  if (hlsController) {
    hlsController.destroy();
    hlsController = null;
  }

  const canPlayHls = streamPlayer.canPlayType("application/vnd.apple.mpegurl");
  if (stream.type === "hls" && window.Hls && Hls.isSupported() && !canPlayHls) {
    hlsController = new Hls();
    hlsController.loadSource(stream.url);
    hlsController.attachMedia(streamPlayer);
    hlsController.on(Hls.Events.MANIFEST_PARSED, () => {
      streamStatus.textContent = "Direct Infomaniak pret.";
    });
    hlsController.on(Hls.Events.ERROR, (_event, data) => {
      if (data?.fatal) streamStatus.textContent = "Direct Infomaniak indisponible.";
    });
    return;
  }

  streamPlayer.src = stream.url;
  streamStatus.textContent = "Direct Infomaniak pret.";
}

async function loadStream() {
  try {
    renderStream(await fetchJson("/api/stream"));
  } catch (error) {
    streamPanel.hidden = true;
  }
}

function renderTranscript(text) {
  const paragraphs = (text || "")
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  currentTranscript.replaceChildren(
    ...paragraphs.map((part) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = part;
      if (part.startsWith("Sources utilisées pour cette édition:")) {
        paragraph.className = "source-credit";
      }
      return paragraph;
    }),
  );
}

function renderCurrent(item, options = {}) {
  if (!item.has_bulletin) {
    player.removeAttribute("src");
    return;
  }
  currentTitle.textContent = item.title;
  selectedBulletinId = item.id;
  manualSelection = Boolean(options.manual);
  playbackMode.textContent = manualSelection ? "Sélection" : "Direct";
  liveButton.hidden = !manualSelection;
  currentSlot.textContent = formatDate(item.slot_start);
  currentSummary.textContent = item.summary || "";
  renderTranscript(item.transcript || "");
  if (item.audio_url && player.getAttribute("src") !== item.audio_url) {
    player.src = item.audio_url;
  }
  currentSources.replaceChildren(
    ...(item.sources || []).map((source) => {
      const link = document.createElement("a");
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = source.source_name;
      link.title = source.title;
      return link;
    }),
  );
}

async function loadBulletin(id) {
  const item = await fetchJson(`/api/bulletins/${encodeURIComponent(id)}`);
  renderCurrent(item, { manual: true });
  await refresh(false);
}

async function returnToLive() {
  manualSelection = false;
  const item = await fetchJson("/api/current");
  renderCurrent(item, { manual: false });
  await refresh(false);
}

function renderHistory(items) {
  if (!items.length) {
    historyEl.textContent = "Aucun bulletin prêt.";
    return;
  }
  historyEl.replaceChildren(
    ...items.map((item) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "history-item";
      if (item.id === selectedBulletinId) row.classList.add("active");
      row.addEventListener("click", () => {
        loadBulletin(item.id).catch(() => {
          pipelineStatus.textContent = "Lecture impossible";
        });
      });
      const left = document.createElement("div");
      const title = document.createElement("div");
      title.className = "history-title";
      title.textContent = item.title;
      const meta = document.createElement("div");
      meta.className = "history-meta";
      meta.textContent = `${formatDate(item.slot_start)} - ${item.style}`;
      left.append(title, meta);
      const duration = document.createElement("div");
      duration.className = "history-meta";
      duration.textContent = item.duration_seconds ? `${Math.round(item.duration_seconds)} s` : "";
      row.append(left, duration);
      return row;
    }),
  );
}

function renderStatus(status) {
  const last = status.last_run;
  pipelineStatus.textContent = last ? `${last.kind}: ${last.status}` : "Prêt";
  const rows = [
    ["News archivées", status.archive?.total ?? 0],
    ["News éditoriales", status.archive?.editorial ?? 0],
    ["News sport exclues", status.archive?.sports ?? 0],
    ["Sources actives", status.enabled_sources ?? 0],
    ["Articles nouveaux", status.articles?.new ?? 0],
    ["Articles utilisés", status.articles?.used ?? 0],
    ["Bulletins prêts", status.bulletins?.ready ?? 0],
    ["Bulletins en erreur", status.bulletins?.error ?? 0],
  ];
  metricsEl.replaceChildren(
    ...rows.flatMap(([name, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = name;
      const dd = document.createElement("dd");
      dd.textContent = value;
      return [dt, dd];
    }),
  );
}

function renderArticleArchive(items) {
  if (!items.length) {
    articleArchiveEl.textContent = "Aucune news archivée.";
    return;
  }
  articleArchiveEl.replaceChildren(
    ...items.map((item) => {
      const row = document.createElement("a");
      row.className = "archive-item";
      row.href = item.url;
      row.target = "_blank";
      row.rel = "noreferrer";

      const title = document.createElement("div");
      title.className = "archive-title";
      title.textContent = item.title;

      const meta = document.createElement("div");
      meta.className = "history-meta";
      const kind = item.is_sports ? "sport exclu" : item.status;
      meta.textContent = `${item.source_name} · ${kind} · ${formatDate(item.published_at || item.scraped_at)}`;

      row.append(title, meta);
      return row;
    }),
  );
}

async function refresh(updateCurrent = true) {
  try {
    const requests = [
      fetchJson(`/api/history?limit=${historyLimit}`),
      fetchJson(`/api/articles?limit=${articleArchiveLimit}`),
      fetchJson("/api/status"),
    ];
    if (updateCurrent) requests.unshift(fetchJson("/api/current"));
    const results = await Promise.all(requests);
    const current = updateCurrent ? results[0] : null;
    const history = updateCurrent ? results[1] : results[0];
    const archive = updateCurrent ? results[2] : results[1];
    const status = updateCurrent ? results[3] : results[2];
    if (current && !manualSelection) renderCurrent(current, { manual: false });
    renderHistory(history);
    renderArticleArchive(archive);
    renderStatus(status);
  } catch (error) {
    pipelineStatus.textContent = "Hors ligne";
  }
}

liveButton.addEventListener("click", () => {
  returnToLive().catch(() => {
    pipelineStatus.textContent = "Direct indisponible";
  });
});

refresh();
loadStream();
setInterval(() => refresh(!manualSelection), 15000);
