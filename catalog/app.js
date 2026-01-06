(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const state = {
    lang: "EN",
    theme: "light",
    view: "table",
    q: "",
    sortKey: "name",
    sortDir: "asc",
    page: 1,
    pageSize: 48,
    listKey: "pcgaVTaz",
  };

  function safeText(v) {
    return (v === null || v === undefined) ? "" : String(v);
  }

  function getData() {
    return window.GAMEPASS_DATA || { products: { EN: {}, UA: {} }, lists: { EN: {}, UA: {} } };
  }

  function getProducts() {
    const d = getData();
    return (d.products && d.products[state.lang]) ? d.products[state.lang] : {};
  }

  function getLists() {
    const d = getData();
    return (d.lists && d.lists[state.lang]) ? d.lists[state.lang] : {};
  }

  function firstLocalized(product) {
    const lp = product && product.LocalizedProperties;
    if (Array.isArray(lp) && lp.length > 0 && typeof lp[0] === "object" && lp[0]) return lp[0];
    return null;
  }

  function getTitle(product, gameid) {
    const lp = firstLocalized(product);
    return safeText((lp && (lp.ProductTitle || lp.Title)) || product.ProductTitle || gameid);
  }

  function getPublisher(product) {
    return safeText(product.PublisherName || product.Publisher || "");
  }

  function getReleaseDateRaw(product) {
    const mp = product && product.MarketProperties;
    const d = (Array.isArray(mp) && mp[0] && mp[0].OriginalReleaseDate) ? mp[0].OriginalReleaseDate : (product.OriginalReleaseDate || "");
    return safeText(d || "");
  }

  function getReleaseYear(product) {
    const raw = getReleaseDateRaw(product);
    const m = raw.match(/^\d{4}/);
    return m ? m[0] : "";
  }

  function getDescription(product) {
    const lp = firstLocalized(product);
    return safeText((lp && (lp.ProductDescription || lp.Description)) || "");
  }

  function pickImageUrl(product) {
    const lp = firstLocalized(product);
    const imgs = lp && lp.Images;
    if (!Array.isArray(imgs)) return "";

    const preferredPurposes = [
      "Poster",
      "BoxArt",
      "BrandedKeyArt",
      "SuperHeroArt",
      "Hero",
      "FeaturePromotionalSquareArt",
      "Screenshot",
      "Icon",
      "Logo",
    ];

    for (const purpose of preferredPurposes) {
      const hit = imgs.find((x) => x && x.ImagePurpose === purpose && x.Uri);
      if (hit) return hit.Uri;
    }

    const any = imgs.find((x) => x && x.Uri);
    return any ? any.Uri : "";
  }

  function matchesQuery(title, publisher, q) {
    if (!q) return true;
    const s = (title + " " + publisher).toLowerCase();
    return s.includes(q.toLowerCase());
  }

  function setTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme === "dark" ? "dark" : "light");
    try { localStorage.setItem("gp_theme", theme); } catch (_) {}
  }

  function toggleTheme() {
    setTheme(state.theme === "dark" ? "light" : "dark");
  }

  function setLang(lang) {
    state.lang = lang;
    state.page = 1;
    $("btnLang").textContent = lang;
    try { localStorage.setItem("gp_lang", lang); } catch (_) {}
    populateLists();
    renderAll();
  }

  function toggleLang() {
    setLang(state.lang === "EN" ? "UA" : "EN");
  }

  function setView(view) {
    state.view = view;
    $("btnTable").classList.toggle("active", view === "table");
    $("btnTiles").classList.toggle("active", view === "tiles");
    $("tableView").style.display = (view === "table") ? "" : "none";
    $("tilesView").style.display = (view === "tiles") ? "" : "none";
    renderAll();
  }

  function setSort(key) {
    if (state.sortKey === key) {
      state.sortDir = (state.sortDir === "asc") ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDir = "asc";
    }
    renderAll();
  }

  function getSelectedIdsSet() {
    const lists = getLists();
    const lst = lists[state.listKey];
    const items = lst && Array.isArray(lst.items) ? lst.items : null;
    if (!items) return null;
    const set = new Set();
    for (const id of items) if (typeof id === "string" && id) set.add(id);
    return set;
  }

  function getEntriesFilteredSorted() {
    const prods = getProducts();
    const entries = Object.entries(prods);

    const idsSet = getSelectedIdsSet();
    const out = [];
    for (const [gameid, product] of entries) {
      if (idsSet && !idsSet.has(gameid)) continue;

      const title = getTitle(product, gameid);
      const pub = getPublisher(product);
      if (!matchesQuery(title, pub, state.q)) continue;

      out.push({
        gameid,
        product,
        title,
        pub,
        year: getReleaseYear(product),
      });
    }

    const dir = state.sortDir === "asc" ? 1 : -1;
    out.sort((a, b) => {
      if (state.sortKey === "publisher") return a.pub.localeCompare(b.pub) * dir;
      if (state.sortKey === "year") return (a.year.localeCompare(b.year) || a.title.localeCompare(b.title)) * dir;
      return a.title.localeCompare(b.title) * dir;
    });

    return out;
  }

  function paginate(items) {
    const total = items.length;
    const pages = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > pages) state.page = pages;

    const start = (state.page - 1) * state.pageSize;
    const end = start + state.pageSize;
    return { pageItems: items.slice(start, end), total, pages };
  }

  function renderPagination(pages) {
    const wrap = $("pagination");
    wrap.innerHTML = "";
    if (pages <= 1) return;

    const makeBtn = (label, page, active) => {
      const b = document.createElement("button");
      b.className = "pg-btn" + (active ? " pg-active" : "");
      b.textContent = label;
      b.addEventListener("click", () => { state.page = page; renderAll(); });
      return b;
    };

    const windowSize = 9;
    const half = Math.floor(windowSize / 2);
    let start = Math.max(1, state.page - half);
    let end = Math.min(pages, start + windowSize - 1);
    start = Math.max(1, end - windowSize + 1);

    wrap.appendChild(makeBtn("«", 1, false));
    wrap.appendChild(makeBtn("‹", Math.max(1, state.page - 1), false));

    for (let p = start; p <= end; p++) {
      wrap.appendChild(makeBtn(String(p), p, p === state.page));
    }

    wrap.appendChild(makeBtn("›", Math.min(pages, state.page + 1), false));
    wrap.appendChild(makeBtn("»", pages, false));
  }

  function renderTable(itemsPage) {
    const tbody = $("tbody");
    tbody.innerHTML = "";

    for (const it of itemsPage) {
      const tr = document.createElement("tr");

      const tdImg = document.createElement("td");
      const img = document.createElement("img");
      img.className = "cover";
      img.alt = it.title;
      const url = pickImageUrl(it.product);
      if (url) img.src = url;
      tdImg.appendChild(img);

      const tdName = document.createElement("td");
      tdName.textContent = it.title;

      const tdPub = document.createElement("td");
      tdPub.textContent = it.pub || "—";

      const tdYear = document.createElement("td");
      tdYear.textContent = it.year || "—";

      const tdAct = document.createElement("td");
      const btn = document.createElement("button");
      btn.className = "btn-read";
      btn.type = "button";
      btn.textContent = "Details";
      btn.addEventListener("click", (e) => { e.stopPropagation(); openModal(it.gameid); });
      tdAct.appendChild(btn);

      tr.appendChild(tdImg);
      tr.appendChild(tdName);
      tr.appendChild(tdPub);
      tr.appendChild(tdYear);
      tr.appendChild(tdAct);

      tr.addEventListener("click", () => openModal(it.gameid));
      tbody.appendChild(tr);
    }
  }

  function renderTiles(itemsPage) {
    const tiles = $("tiles");
    tiles.innerHTML = "";

    for (const it of itemsPage) {
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.tabIndex = 0;

      const img = document.createElement("img");
      const url = pickImageUrl(it.product);
      if (url) img.src = url;
      img.alt = it.title;

      const title = document.createElement("div");
      title.className = "tile-title";
      title.textContent = it.title;

      const sub = document.createElement("div");
      sub.className = "tile-sub";
      sub.textContent = [it.pub, it.year].filter(Boolean).join(" • ") || "—";

      tile.appendChild(img);
      tile.appendChild(title);
      tile.appendChild(sub);

      tile.addEventListener("click", () => openModal(it.gameid));
      tile.addEventListener("keypress", (e) => { if (e.key === "Enter" || e.key === " ") openModal(it.gameid); });

      tiles.appendChild(tile);
    }
  }

  function openModal(gameid) {
    const prods = getProducts();
    const product = prods[gameid];
    if (!product) return;

    const title = getTitle(product, gameid);
    const pub = getPublisher(product);
    const rawDate = getReleaseDateRaw(product);
    const desc = getDescription(product);
    const imgUrl = pickImageUrl(product);

    $("modalTitle").textContent = title;

    const body = document.createElement("div");

    const hero = document.createElement("div");
    hero.className = "game-hero";

    const poster = document.createElement("img");
    poster.className = "game-poster";
    poster.alt = title;
    if (imgUrl) poster.src = imgUrl;

    const info = document.createElement("div");
    info.className = "game-info";

    const t = document.createElement("div");
    t.className = "game-title";
    t.textContent = title;

    const sub = document.createElement("div");
    sub.className = "game-sub";
    sub.textContent = [pub, rawDate].filter(Boolean).join(" • ");

    const kv = document.createElement("div");
    kv.className = "kv";
    const mkTag = (txt) => {
      const s = document.createElement("span");
      s.className = "tag";
      s.textContent = txt;
      return s;
    };
    kv.appendChild(mkTag("Lang: " + state.lang));
    kv.appendChild(mkTag("ID: " + gameid));
    const yr = getReleaseYear(product);
    if (yr) kv.appendChild(mkTag("Year: " + yr));
    kv.appendChild(mkTag("List: " + state.listKey));

    const descEl = document.createElement("div");
    descEl.className = "desc-text";
    descEl.textContent = desc || "(No description in this locale)";

    info.appendChild(t);
    info.appendChild(sub);
    info.appendChild(kv);

    hero.appendChild(poster);
    hero.appendChild(info);

    body.appendChild(hero);
    body.appendChild(descEl);

    const modalContent = $("modalContent");
    modalContent.innerHTML = "";
    modalContent.appendChild(body);

    const overlay = $("modalOverlay");
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    $("modalClose").focus();
  }

  function closeModal() {
    const overlay = $("modalOverlay");
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
  }

  function populateLists() {
    const lists = getLists();
    const sel = $("listSel");
    if (!sel) return;

    const entries = Object.entries(lists).map(([key, obj]) => ({
      key,
      title: (obj && obj.title) ? obj.title : key,
      group: (obj && obj.group) ? obj.group : "Lists",
      count: (obj && Array.isArray(obj.items)) ? obj.items.length : 0,
    }));

    entries.sort((a, b) => (a.group.localeCompare(b.group) || a.title.localeCompare(b.title)));

    sel.innerHTML = "";
    const groups = new Map();
    for (const it of entries) {
      if (!groups.has(it.group)) groups.set(it.group, []);
      groups.get(it.group).push(it);
    }

    for (const [gname, arr] of groups.entries()) {
      const og = document.createElement("optgroup");
      og.label = gname;
      for (const it of arr) {
        const opt = document.createElement("option");
        opt.value = it.key;
        opt.textContent = `${it.title} (${it.count})`;
        og.appendChild(opt);
      }
      sel.appendChild(og);
    }

    if (!lists[state.listKey]) {
      state.listKey = entries.length ? entries[0].key : "pcgaVTaz";
    }
    sel.value = state.listKey;
  }

  function renderAll() {
    const all = getEntriesFilteredSorted();
    const { pageItems, total, pages } = paginate(all);

    $("countTxt").value = `${state.lang}: ${total} games`;

    if (state.view === "table") renderTable(pageItems);
    else renderTiles(pageItems);

    renderPagination(pages);
  }

  function initSortHandlers() {
    document.querySelectorAll("th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-key");
        if (key) setSort(key);
      });
    });
  }

  function initFab() {
    const fs = document.querySelector(".float-settings");
    $("fabMain").addEventListener("click", () => {
      fs.classList.toggle("open");
    });
    document.addEventListener("click", (e) => {
      if (!fs.contains(e.target)) fs.classList.remove("open");
    });
  }

  function initModalHandlers() {
    $("modalClose").addEventListener("click", closeModal);
    $("modalOverlay").addEventListener("click", (e) => {
      if (e.target === $("modalOverlay")) closeModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeModal();
    });
  }

  function init() {
    try {
      const th = localStorage.getItem("gp_theme");
      if (th === "dark" || th === "light") state.theme = th;
      const lg = localStorage.getItem("gp_lang");
      if (lg === "EN" || lg === "UA") state.lang = lg;
      const lk = localStorage.getItem("gp_list");
      if (lk) state.listKey = lk;
    } catch (_) {}

    setTheme(state.theme);
    $("btnLang").textContent = state.lang;

    $("btnTable").addEventListener("click", () => setView("table"));
    $("btnTiles").addEventListener("click", () => setView("tiles"));

    $("searchTxt").addEventListener("input", (e) => {
      state.q = e.target.value || "";
      state.page = 1;
      renderAll();
    });

    $("listSel").addEventListener("change", (e) => {
      state.listKey = e.target.value;
      state.page = 1;
      try { localStorage.setItem("gp_list", state.listKey); } catch (_) {}
      renderAll();
    });

    $("btnReset").addEventListener("click", () => {
      state.q = "";
      $("searchTxt").value = "";
      state.sortKey = "name";
      state.sortDir = "asc";
      state.page = 1;
      state.listKey = "pcgaVTaz";
      try { localStorage.setItem("gp_list", state.listKey); } catch (_) {}
      $("listSel").value = state.listKey;
      renderAll();
    });

    $("btnTheme").addEventListener("click", () => {
      toggleTheme();
      renderAll();
    });

    $("btnLang").addEventListener("click", toggleLang);

    initSortHandlers();
    initFab();
    initModalHandlers();

    populateLists();
    renderAll();
  }

  init();
})();