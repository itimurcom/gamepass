// app.js — Main Logic (Fixed: Theme Switcher Priority)

// Load Data from Global Variable
const DATA = window.GP_DATA || [];

// 1x1 Transparent GIF (to prevent broken image icon)
const TRANSPARENT_PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

const PAGE_SIZE = 50;
let CUR_PAGE = 1;
let FILTERED_LIST = DATA;
let SORT = { key: 'rating', asc: false };
// Default to light if not set
let CUR_THEME = localStorage.getItem("gp_theme") || "light"; 
let CUR_LANG = localStorage.getItem("gp_lang") || "uk";
let OPEN_GAME_ID = null;

const I18N = {
    uk: {
        title: "Каталог Game Pass", search: "ПОШУК", year: "РІК", genre: "ЖАНР", cat: "КАТЕГОРІЯ", rating: "РЕЙТИНГ", fav: "Обране", reset: "✕ Скинути", sort: "СОРТУВАННЯ",
        viewList: "☰ Список", viewTiles: "▦ Плитка", poster: "Постер", name: "Назва", info: "Інфо", time: "Час", actions: "Дії", details: "Деталі гри", read: "Читати", hours: "год."
    },
    en: {
        title: "Game Pass Catalog", search: "SEARCH", year: "YEAR", genre: "GENRE", cat: "CATEGORY", rating: "RATING", fav: "Favorites", reset: "✕ Reset", sort: "SORT BY",
        viewList: "☰ List", viewTiles: "▦ Tiles", poster: "Poster", name: "Name", info: "Info", time: "Time", actions: "Actions", details: "Game Details", read: "Read", hours: "h"
    }
};

function init() {
    // 1. Спершу ініціалізуємо UI (Тема та Мова), щоб вони працювали завжди
    setupThemeLogic();
    setupLangLogic();

    // 2. Перевіряємо наявність даних
    if(!DATA.length) { 
        const titleEl = document.getElementById("lblTitle");
        if(titleEl) titleEl.innerText = "Game Pass (0)";
        // Навіть якщо даних немає, не робимо return, щоб працював інтерфейс
    }
    
    // 3. Запускаємо фільтри та рендерінг
    applyLang(CUR_LANG);
    setupFilters();
    applyFilters();
}

function setupThemeLogic() {
    const themeToggle = document.getElementById("theme-toggle");
    
    // Функція застосування теми
    window.applyTheme = function(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        CUR_THEME = theme;
        localStorage.setItem("gp_theme", theme);
        
        // Синхронізуємо стан чекбокса, якщо функцію викликали програмно
        if(themeToggle && themeToggle.checked !== (theme === "dark")) {
            themeToggle.checked = (theme === "dark");
        }
    };

    // Слухач подій на чекбокс
    if(themeToggle) {
        // Встановлюємо початковий стан перемикача
        themeToggle.checked = (CUR_THEME === "dark");
        
        themeToggle.addEventListener('change', (e) => {
            const newTheme = e.target.checked ? "dark" : "light";
            window.applyTheme(newTheme);
        });
    }

    // Застосовуємо тему при старті
    window.applyTheme(CUR_THEME);
}

function setupLangLogic() {
    const btnLang = document.getElementById("btnLang");
    if (btnLang) {
        btnLang.onclick = () => applyLang(CUR_LANG === "uk" ? "en" : "uk");
    }
}

function applyLang(lang) {
    CUR_LANG = lang;
    localStorage.setItem("gp_lang", lang);
    const btn = document.getElementById("btnLang");
    if(btn) btn.innerText = (lang === 'uk' ? 'EN' : 'UK');
    
    const t = I18N[lang];
    document.querySelectorAll("[data-t]").forEach(el => {
        const k = el.getAttribute("data-t");
        if(t[k]) {
            if(el.tagName === 'INPUT') el.placeholder = t[k];
            else el.innerText = t[k];
        }
    });
    
    // Оновлюємо рендер, якщо є дані
    if(DATA.length) render(); 
    
    // Оновлюємо модалку, якщо відкрита
    if(document.getElementById("modalOverlay").classList.contains("open") && OPEN_GAME_ID) {
        const idx = FILTERED_LIST.findIndex(x => x.id === OPEN_GAME_ID);
        if(idx !== -1) openModal(idx);
    }
}

function esc(s){return (s||"").toString().replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
const getFavs=()=>{try{return new Set(JSON.parse(localStorage.getItem("gp_favs")||"[]"))}catch{return new Set()}};
const setFavs=s=>localStorage.setItem("gp_favs",JSON.stringify(Array.from(s)));

function openModal(idx) {
    const game = FILTERED_LIST[idx]; 
    OPEN_GAME_ID = game.id;
    const content = document.getElementById("modalContent");
    const t = I18N[CUR_LANG];
    const i18nData = game.i18n ? game.i18n[CUR_LANG] : { name: game.name, genre: game.genre, desc: "No data" };
    
    const imgClass = game.no_avatar ? "game-poster no-avatar" : "game-poster";
    const imgSrc = game.no_avatar ? TRANSPARENT_PIXEL : esc(game.image);

    let tagsHtml = "";
    (game.tags || []).forEach(tg => {
        if(tg.includes("Leaving")) tagsHtml += `<span class="tag tag-leaving">${tg}</span> `;
        else if(tg.includes("New")) tagsHtml += `<span class="tag tag-new">${tg}</span> `;
        else tagsHtml += `<span class="tag">${tg}</span> `;
    });

    content.innerHTML = `
        <div class="game-hero">
            <img src="${imgSrc}" class="${imgClass}">
            <div class="game-info">
                <div style="font-size:24px; font-weight:800; margin-bottom:10px; line-height:1.2;">${esc(i18nData.name)}</div>
                <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:15px;">
                    ${tagsHtml}
                    <span class="tag">${esc(game.year)}</span>
                    <span class="tag">${esc(game.publisher)}</span>
                    <span class="tag" style="background:${game.tier==='AAA'?'var(--accent)':'var(--bg)'}; color:${game.tier==='AAA'?'#fff':'inherit'}">${esc(game.tier)}</span>
                </div>
                <div style="font-size:20px; font-weight:700;">
                    <span style="color:${game.rating>=80?'#008a4b':(game.rating>=60?'#bf8600':'#666')}">★ ${game.rating||'-'}</span>
                    <span style="font-size:13px; color:var(--text-sec); font-weight:400; margin-left:6px;">(${esc(game.ratingSource)})</span>
                </div>
                <div style="margin-top:6px; color:var(--text-sec);">⏳ ${esc(game.hours)} ${t.hours}</div>
            </div>
        </div>
        <div class="desc-text">${i18nData.desc}</div>
    `;
    
    document.getElementById("modalOverlay").classList.add("open");
    document.body.style.overflow = "hidden";
}

function closeModal() { 
    document.getElementById("modalOverlay").classList.remove("open"); 
    document.body.style.overflow = ""; 
    OPEN_GAME_ID = null;
}
document.getElementById("modalOverlay").onclick = (e) => { if(e.target === document.getElementById("modalOverlay")) closeModal(); };

function renderPagination(total) {
    const container = document.getElementById("pagination");
    if(!container) return;
    container.innerHTML = "";
    if (total <= 1) return; 
    const createBtn = (label, page, isActive = false) => {
        const btn = document.createElement("button");
        btn.className = `pg-btn ${isActive ? "pg-active" : ""}`;
        btn.innerHTML = label;
        btn.onclick = () => { CUR_PAGE = page; render(); window.scrollTo({top:0, behavior:'smooth'}); };
        return btn;
    };
    container.appendChild(createBtn("←", Math.max(1, CUR_PAGE - 1)));
    let pages = [];
    if (total <= 7) { for (let i = 1; i <= total; i++) pages.push(i); } 
    else {
        if(CUR_PAGE < 5) pages = [1,2,3,4,5, '...', total];
        else if (CUR_PAGE > total - 4) pages = [1, '...', total-4, total-3, total-2, total-1, total];
        else pages = [1, '...', CUR_PAGE-1, CUR_PAGE, CUR_PAGE+1, '...', total];
    }
    pages.forEach(p => {
        if(p === '...') { const d=document.createElement("span"); d.style.color="var(--text-sec)"; d.innerText="..."; container.appendChild(d); } 
        else container.appendChild(createBtn(p, p, CUR_PAGE === p));
    });
    container.appendChild(createBtn("→", Math.min(total, CUR_PAGE + 1)));
}

function applyFilters() {
    if(!DATA.length) return; // Якщо даних немає, не фільтруємо

    const txtEl = document.getElementById("searchTxt");
    const txt = txtEl ? txtEl.value.toLowerCase() : "";
    
    const yearEl = document.getElementById("filterYear");
    const years = yearEl ? Array.from(yearEl.selectedOptions).map(o=>o.value) : [];
    
    const genreEl = document.getElementById("filterGenre");
    const genres = genreEl ? Array.from(genreEl.selectedOptions).map(o=>o.value) : [];
    
    const tagEl = document.getElementById("filterTag");
    const tags = tagEl ? Array.from(tagEl.selectedOptions).map(o=>o.value) : [];
    
    const tierEl = document.getElementById("filterTier");
    const tier = tierEl ? tierEl.value : "";
    
    const rEl = document.getElementById("filterRating");
    const r = rEl ? Number(rEl.value) : 0;
    
    const fEl = document.getElementById("filterFav");
    const f = fEl ? fEl.checked : false;
    
    const favs = getFavs();

    FILTERED_LIST = DATA.filter(x => {
        const name = (x.i18n && x.i18n[CUR_LANG] ? x.i18n[CUR_LANG].name : x.name).toLowerCase();
        if(txt && !name.includes(txt)) return false;
        if(years.length && !years.includes(x.year)) return false;
        
        const gStr = x.i18n?.uk?.genre || "";
        if(genres.length && !gStr.split(", ").some(g=>genres.includes(g))) return false;
        
        // Tags Filter
        if(tags.length) {
            const myTags = x.tags || [];
            if(!myTags.some(t => tags.includes(t))) return false;
        }

        if(tier && x.tier !== tier) return false;
        if(r && (x.rating || 0) < r) return false;
        if(f && !favs.has(x.id)) return false;
        return true;
    });
    
    CUR_PAGE = 1;
    render();
}

function render() {
    const t = I18N[CUR_LANG];
    
    // UPDATE COUNTER
    const titleEl = document.getElementById("lblTitle");
    if(titleEl) titleEl.innerText = `Game Pass (${FILTERED_LIST.length})`;

    // SYNC SORT DROPDOWN (Ensure UI matches state)
    const sortSel = document.getElementById("sortSelect");
    if(sortSel) {
        const val = `${SORT.key}_${SORT.asc?'asc':'desc'}`;
        sortSel.value = val;
    }

    FILTERED_LIST.sort((a, b) => {
        let valA = a[SORT.key], valB = b[SORT.key];
        if (SORT.key === 'name') {
             valA = (a.i18n && a.i18n[CUR_LANG] ? a.i18n[CUR_LANG].name : a.name).toLowerCase();
             valB = (b.i18n && b.i18n[CUR_LANG] ? b.i18n[CUR_LANG].name : b.name).toLowerCase();
        } else if (['rating', 'year', 'hours'].includes(SORT.key)) {
            valA = Number(valA) || 0; valB = Number(valB) || 0;
        }
        if (valA < valB) return SORT.asc ? -1 : 1;
        if (valA > valB) return SORT.asc ? 1 : -1;
        return 0;
    });

    document.querySelectorAll("th.sortable").forEach(th => {
        th.classList.remove("sort-asc", "sort-desc");
        const icon = th.querySelector(".sort-icon");
        if(icon) icon.textContent = "↕";
        if(th.dataset.key === SORT.key) {
            th.classList.add(SORT.asc ? "sort-asc" : "sort-desc");
            if(icon) icon.textContent = SORT.asc ? "▲" : "▼";
        }
    });

    const totalPages = Math.ceil(FILTERED_LIST.length / PAGE_SIZE) || 1;
    if (CUR_PAGE > totalPages) CUR_PAGE = totalPages;
    const start = (CUR_PAGE - 1) * PAGE_SIZE;
    const pageData = FILTERED_LIST.slice(start, start + PAGE_SIZE);
    
    const favs = getFavs();
    const isTiles = localStorage.getItem("gp_view") === "tiles";

    const tableV = document.getElementById("tableView");
    if(tableV) tableV.style.display = isTiles ? "none" : "block";
    
    const tilesV = document.getElementById("tilesView");
    if(tilesV) tilesV.style.display = isTiles ? "block" : "none";
    
    const btnTable = document.getElementById("btnTable");
    if(btnTable) btnTable.className = isTiles ? "btn" : "btn active";
    
    const btnTiles = document.getElementById("btnTiles");
    if(btnTiles) btnTiles.className = isTiles ? "btn active" : "btn";
    
    renderPagination(totalPages);

    const getRowData = (x) => {
        const d = x.i18n ? x.i18n[CUR_LANG] : {name: x.name, genre: x.genre};
        return { ...x, displayName: d.name, displayGenre: d.genre };
    };

    if(isTiles) {
        const tilesContainer = document.getElementById("tiles");
        if(tilesContainer) {
            tilesContainer.innerHTML = pageData.map((raw, i) => {
                const x = getRowData(raw);
                const globalIdx = start + i;
                const imgClass = x.no_avatar ? "no-avatar" : "";
                const imgSrc = x.no_avatar ? TRANSPARENT_PIXEL : esc(x.image);
                
                // Render Badges
                let tagsHtml = "";
                (x.tags || []).forEach(tg => {
                     if(tg === "Leaving Soon") tagsHtml += `<span class="tag-badge tag-leaving" style="font-size:10px; padding:2px 4px; border-radius:4px; margin-right:4px;">👋</span>`;
                     else if(tg === "New Added") tagsHtml += `<span class="tag-badge tag-new" style="font-size:10px; padding:2px 4px; border-radius:4px; margin-right:4px;">NEW</span>`;
                });

                return `
                <div class="tile" onclick="openModal(${globalIdx})">
                    <div style="position:relative">
                        <img src="${imgSrc}" loading="lazy" class="${imgClass}">
                        <div style="position:absolute; top:8px; left:8px; display:flex;">${tagsHtml}</div>
                        <button class="fav ${favs.has(x.id)?"on":""}" data-id="${x.id}" onclick="event.stopPropagation(); toggleFav(this)">★</button>
                    </div>
                    <div class="tile-title">${esc(x.displayName)}</div>
                    <div style="font-size:13px; color:var(--text-sec); display:flex; justify-content:space-between;">
                        <span>${esc(x.year)}</span>
                        <span style="font-weight:bold; color:${x.rating>=80?'#008a4b':(x.rating>=60?'#bf8600':'var(--text-sec)')}">★ ${x.rating||'-'}</span>
                    </div>
                </div>`
            }).join("");
        }
    } else {
        const tbody = document.getElementById("tbody");
        if(tbody) {
            tbody.innerHTML = pageData.map((raw, i) => {
                const x = getRowData(raw);
                const globalIdx = start + i;
                const imgClass = x.no_avatar ? "cover no-avatar" : "cover";
                const imgSrc = x.no_avatar ? TRANSPARENT_PIXEL : esc(x.image);
                
                let tagsHtml = "";
                (x.tags || []).forEach(tg => {
                     if(tg === "Leaving Soon") tagsHtml += `<span class="tier-badge tag-leaving">Leaving</span>`;
                     else if(tg === "New Added") tagsHtml += `<span class="tier-badge tag-new">New</span>`;
                     else if(tg !== "PC" && tg !== "Console" && tg !== "Ultimate") tagsHtml += `<span class="tier-badge tag-badge">${tg}</span>`;
                });

                return `
                <tr>
                    <td><img src="${imgSrc}" class="${imgClass}" loading="lazy" style="cursor:pointer" onclick="openModal(${globalIdx})"></td>
                    <td>
                        <div style="font-weight:700; font-size:16px; margin-bottom:4px;">${esc(x.displayName)}</div>
                        ${tagsHtml}
                        ${x.tier === "AAA" ? '<span class="tier-badge tier-AAA">AAA</span>' : '<span class="tier-badge tier-Indie">Indie/AA</span>'}
                        <div style="font-size:12px; color:var(--text-sec); margin-top:4px;">${esc(x.developer)}</div>
                    </td>
                    <td>${esc(x.displayGenre)}</td>
                    <td><button class="btn-read" onclick="openModal(${globalIdx})">${t.read}</button></td>
                    <td>
                        <div class="rating-val ${x.rating>=80?'rating-high':(x.rating>=60?'rating-mid':'rating-low')}">${esc(x.rating || '-')}</div>
                        <div style="font-size:10px; color:var(--text-sec);">${esc(x.ratingSource)}</div>
                    </td>
                    <td>${esc(x.year)}</td>
                    <td>${esc(x.hours)}</td>
                    <td>
                        <button class="fav ${favs.has(x.id)?"on":""}" data-id="${x.id}" onclick="toggleFav(this)">★</button>
                    </td>
                </tr>`
            }).join("");
        }
    }
}

function toggleFav(btn) {
    const id = btn.dataset.id;
    const s = getFavs();
    s.has(id) ? s.delete(id) : s.add(id);
    setFavs(s);
    btn.classList.toggle("on");
    const favCheck = document.getElementById("filterFav");
    if(favCheck && favCheck.checked) applyFilters();
}

function setupFilters() {
    if(!DATA.length) return;

    const years = [...new Set(DATA.map(x=>x.year).filter(Boolean))].sort().reverse();
    const genres = [...new Set(DATA.flatMap(x=> (x.i18n?.uk?.genre || "").split(", ")).filter(Boolean))].sort();
    const tags = [...new Set(DATA.flatMap(x => x.tags || []))].sort();

    const yEl = document.getElementById("filterYear");
    if(yEl) yEl.innerHTML = years.map(y=>`<option>${y}</option>`).join("");
    
    const gEl = document.getElementById("filterGenre");
    if(gEl) gEl.innerHTML = genres.map(g=>`<option>${g}</option>`).join("");
    
    const tEl = document.getElementById("filterTag");
    if(tEl) tEl.innerHTML = tags.map(t=>`<option>${t}</option>`).join("");
    
    document.querySelectorAll("select, input").forEach(e => e.onchange = applyFilters);
    const searchEl = document.getElementById("searchTxt");
    if(searchEl) searchEl.oninput = applyFilters;
    
    const btnReset = document.getElementById("btnReset");
    if(btnReset) btnReset.onclick = () => {
        document.querySelectorAll("select").forEach(s => Array.from(s.options).forEach(o => o.selected = false));
        document.querySelectorAll("input").forEach(i => {if(i.type==='checkbox')i.checked=false; else i.value=''});
        SORT = { key: 'rating', asc: false };
        applyFilters();
    };
    
    const btnTable = document.getElementById("btnTable");
    if(btnTable) btnTable.onclick = () => { localStorage.setItem("gp_view","table"); render(); };
    
    const btnTiles = document.getElementById("btnTiles");
    if(btnTiles) btnTiles.onclick = () => { localStorage.setItem("gp_view","tiles"); render(); };
    
    document.querySelectorAll("th.sortable").forEach(th => {
        th.onclick = () => {
            const key = th.dataset.key;
            if (SORT.key === key) SORT.asc = !SORT.asc;
            else {
                SORT.key = key;
                SORT.asc = ['rating','year'].includes(key) ? false : true;
            }
            render();
        };
    });

    // NEW SORT DROPDOWN LISTENER
    const sortSel = document.getElementById("sortSelect");
    if(sortSel) {
        sortSel.onchange = (e) => {
            const parts = e.target.value.split("_");
            SORT.key = parts[0];
            SORT.asc = (parts[1] === "asc");
            render();
        };
    }
}

// Запускаємо init
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}