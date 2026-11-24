(function () {
  "use strict";

  const REFRESH_MS = 30 * 60 * 1000;
  const FAV_KEY = "tvlistesi.favorites";
  const REMOTE_JSON = "https://raw.githubusercontent.com/ailantus/TeVe/refs/heads/main/data/channels.json";

  const el = {
    meta: document.getElementById("meta"),
    channels: document.getElementById("channels"),
    groups: document.getElementById("groups"),
    empty: document.getElementById("empty"),
    search: document.getElementById("search"),
    favoritesOnly: document.getElementById("favoritesOnly"),
    refresh: document.getElementById("refresh"),
    video: document.getElementById("video"),
    placeholder: document.getElementById("placeholder"),
    nowTitle: document.getElementById("nowTitle"),
    nowStatus: document.getElementById("nowStatus"),
    alternate: document.getElementById("alternate"),
    fullscreen: document.getElementById("fullscreen"),
    frame: document.querySelector(".player-frame"),
  };

  let data = window.TVLISTESI_DATA || null;
  let hls = null;
  let recoveryTimer = null;
  let failedSource = false;

  const state = {
    group: "Tümü",
    query: "",
    favoritesOnly: false,
    current: null,
    urls: [],
    index: 0,
  };

  function favorites() {
    try {
      return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || "[]"));
    } catch (_) {
      return new Set();
    }
  }

  function saveFavorites(set) {
    try {
      localStorage.setItem(FAV_KEY, JSON.stringify([...set]));
    } catch (_) { /* depolama kapalı olabilir */ }
  }

  function setStatus(text, kind) {
    el.nowStatus.textContent = text || "";
    el.nowStatus.className = "status" + (kind ? " " + kind : "");
  }

  function initials(name) {
    return name.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toLocaleUpperCase("tr");
  }

  function makeLogo(channel) {
    if (!channel.logo) {
      const badge = document.createElement("span");
      badge.className = "logo";
      badge.textContent = initials(channel.name);
      return badge;
    }
    const img = document.createElement("img");
    img.className = "logo";
    img.src = channel.logo;
    img.alt = "";
    img.loading = "lazy";
    img.onerror = function () {
      const badge = document.createElement("span");
      badge.className = "logo";
      badge.textContent = initials(channel.name);
      img.replaceWith(badge);
    };
    return img;
  }

  function renderMeta() {
    if (!data) return;
    const when = new Date(data.generated_at);
    const stamp = isNaN(when) ? data.generated_at : when.toLocaleString("tr-TR");
    el.meta.textContent = `${data.count} kanal · ${data.sources.length} canlı kaynak · Son güncelleme: ${stamp}`;
  }

  function renderGroups() {
    if (!data) return;
    const names = ["Tümü", ...new Set(data.channels.map((channel) => channel.group))];
    el.groups.replaceChildren();
    names.forEach((name) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "group" + (state.group === name ? " active" : "");
      button.textContent = name;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(state.group === name));
      button.addEventListener("click", () => {
        state.group = name;
        renderGroups();
        renderChannels();
      });
      el.groups.appendChild(button);
    });
  }

  function renderChannels() {
    if (!data) return;
    const favs = favorites();
    const query = state.query.toLocaleLowerCase("tr");
    const shown = data.channels.filter((channel) => {
      if (state.group !== "Tümü" && channel.group !== state.group) return false;
      if (state.favoritesOnly && !favs.has(channel.id)) return false;
      return !query || channel.name.toLocaleLowerCase("tr").includes(query);
    });

    el.channels.replaceChildren();
    el.empty.hidden = shown.length > 0;

    shown.forEach((channel) => {
      const card = document.createElement("div");
      card.className = "channel" + (state.current && state.current.id === channel.id ? " active" : "");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", channel.name + " kanalını oynat");

      card.appendChild(makeLogo(channel));

      const info = document.createElement("div");
      info.className = "channel-info";
      const name = document.createElement("span");
      name.className = "channel-name";
      name.textContent = channel.name;
      const group = document.createElement("span");
      group.className = "channel-group";
      const originNote = channel.origin === "fallback" ? " · yedek adres" : channel.origin === "pinned" ? " · sabit adres" : "";
      group.textContent = channel.group + originNote;
      info.append(name, group);
      card.appendChild(info);

      const star = document.createElement("button");
      star.type = "button";
      star.className = "star" + (favs.has(channel.id) ? " on" : "");
      star.textContent = "★";
      star.title = "Favorilere ekle/çıkar";
      star.addEventListener("click", (event) => {
        event.stopPropagation();
        const current = favorites();
        if (current.has(channel.id)) current.delete(channel.id);
        else current.add(channel.id);
        saveFavorites(current);
        renderChannels();
      });
      card.appendChild(star);

      card.addEventListener("click", () => play(channel));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          play(channel);
        }
      });
      el.channels.appendChild(card);
    });
  }

  function render() {
    renderMeta();
    renderGroups();
    renderChannels();
  }

  function stop() {
    clearTimeout(recoveryTimer);
    if (hls) {
      hls.destroy();
      hls = null;
    }
    video.pause();
    video.removeAttribute("src");
    video.load();
  }

  function nextSource(reason) {
    if (state.index + 1 < state.urls.length) {
      state.index += 1;
      setStatus(`${reason} · yedek kaynak ${state.index}/${state.urls.length}`, "error");
      loadSource();
      return true;
    }
    setStatus(reason || "Yayın açılamadı.", "error");
    return false;
  }

  function loadSource() {
    const url = state.urls[state.index];
    if (!url) return;
    failedSource = false;
    setStatus(`Bağlanıyor… (kaynak ${state.index + 1}/${state.urls.length})`);

    if (typeof Hls !== "undefined" && Hls.isSupported() && /\.m3u8(\?|$)/i.test(url)) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        maxBufferLength: 20,
        httpHeaders: state.current && state.current.headers ? state.current.headers : undefined,
      });
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, function () {
        setStatus("Yayın bağlı", "ok");
        video.play().catch(() => setStatus("Oynatmak için videoya dokunun."));
      });
      hls.on(Hls.Events.ERROR, function (_event, errorDetails) {
        if (!errorDetails.fatal || failedSource) return;
        failedSource = true;
        clearTimeout(recoveryTimer);
        recoveryTimer = setTimeout(() => nextSource("Yayın kesildi"), 900);
      });
    } else {
      video.src = url;
      video.play().catch(() => setStatus("Oynatmak için videoya dokunun."));
    }
  }

  function play(channel) {
    if (state.current && state.current.id === channel.id) return;
    state.current = channel;
    state.urls = [channel.url, ...(channel.alternates || [])];
    state.index = 0;
    el.placeholder.hidden = true;
    el.nowTitle.textContent = channel.name;
    el.alternate.disabled = state.urls.length < 2;
    stop();
    loadSource();
    renderChannels();
  }

  async function fetchList(url) {
    try {
      const response = await fetch(url + "?ts=" + Date.now(), { cache: "no-store" });
      if (!response.ok) return null;
      const json = await response.json();
      return json && json.generated_at && json.channels ? json : null;
    } catch (_) {
      return null;
    }
  }

  async function refresh(manual) {
    // Önce GitHub'daki güncel listeyi dene, yoksa yerel kopyayı kullan.
    const found = await Promise.all([
      fetchList(REMOTE_JSON),
      fetchList("data/channels.json"),
    ]).then((lists) => lists.filter(Boolean).sort(
      (a, b) => new Date(b.generated_at) - new Date(a.generated_at)
    ));
    const fresh = found[0];

    if (fresh) {
      if (!data || fresh.generated_at !== data.generated_at) {
        data = fresh;
        render();
      }
      if (manual) setStatus("Kanal listesi güncellendi.", "ok");
    } else if (manual) {
      setStatus("Liste alınamadı; yerel kopya kullanılıyor.", "error");
    }
  }

  el.search.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderChannels();
  });
  el.favoritesOnly.addEventListener("change", (event) => {
    state.favoritesOnly = event.target.checked;
    renderChannels();
  });
  el.refresh.addEventListener("click", () => refresh(true));
  el.alternate.addEventListener("click", () => nextSource("Farklı kaynak denendi"));
  el.fullscreen.addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (el.frame.requestFullscreen) el.frame.requestFullscreen();
  });
  video.addEventListener("error", () => {
    if (!failedSource && state.current) {
      failedSource = true;
      nextSource("Yayın açılamadı");
    }
  });
  el.channels.addEventListener("keydown", (event) => {
    const arrows = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 0, ArrowUp: 0 };
    if (!(event.key in arrows)) return;
    const cards = [...el.channels.querySelectorAll(".channel")];
    const index = cards.indexOf(document.activeElement);
    if (index < 0) return;
    const columns = getComputedStyle(el.channels).gridTemplateColumns.split(" ").length || 1;
    const step = event.key === "ArrowRight" || event.key === "ArrowLeft"
      ? arrows[event.key]
      : (event.key === "ArrowDown" ? columns : -columns);
    const target = cards[index + step];
    if (target) {
      event.preventDefault();
      target.focus();
    }
  });

  render();
  refresh(false);
  setInterval(() => refresh(false), REFRESH_MS);
})();
