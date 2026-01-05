// app.js — Main Logic (Clean DOM Manipulation)

const DATA = window.GP_DATA || [];
const TRANSPARENT_PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
const PAGE_SIZE = 50;
let CUR_PAGE = 1;
let FILTERED_LIST = DATA;
let SORT = { key: 'rating', asc: false };
let CUR_THEME = localStorage.getItem("gp_theme") || "light"; 
let CUR_LANG = localStorage.getItem("gp_lang") || "uk";
let OPEN_GAME_ID = null;

const I18N = {
    uk: {
        title: "Game Pass Games List", search: "ПОШУК", year: "РІК", genre: "ЖАНР", cat: "КАТЕГОРІЯ", rating: "РЕЙТИНГ", fav: "Обране", reset: "✕ Скинути", sort: "СОРТУВАННЯ",
        viewList: "☰ Список", viewTiles: "▦ Плитка", poster: "Постер", name: "Назва", info: "Інфо", time: "Час", details: "Деталі гри", read: "Читати", hours: "год."
    },
    en: {
        title: "Game Pass Games List", search: "SEARCH", year: "YEAR", genre: "GENRE", cat: "CATEGORY", rating: "RATING", fav: "Favorites", reset: "✕ Reset", sort: "SORT BY",
        viewList: "☰ List", viewTiles: "▦ Tiles", poster: "Poster", name: "Name", info: "Info", time: "Time", details: "Game Details", read: "Read", hours: "h"
    }
};

function init() {
    setupThemeLogic();
    setupLangLogic();
    if(!DATA.length) { 
        const titleEl = document.getElementById("lblTitle");
        if(titleEl) titleEl.innerText = "Game Pass Games List (0)";
    }
    applyLang(CUR_LANG);
    setupFilters();
    applyFilters();
}

function setupThemeLogic() {
    const themeToggle = document.getElementById("theme-toggle");
    window.applyTheme = function(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        CUR_THEME = theme;
        localStorage.setItem("gp_theme", theme);
        if(themeToggle && themeToggle.checked !== (theme === "dark")) {
            themeToggle.checked = (theme === "dark");
        }
    };
    if(themeToggle) {
        themeToggle.checked = (CUR_THEME === "dark");
        themeToggle.addEventListener('change', (e) => {
            const newTheme = e.target.checked ? "dark" : "light";
            window.applyTheme(newTheme);
        });
    }
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
    if(DATA.length) render(); 
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
    
    // Using string concat here ONLY for modal content simplicity, 
    // but main list is now strict DOM.
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
    if(!DATA.length) return;

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
    let f = fEl ? fEl.checked : false;
    
    const favs = getFavs();

    // AUTO-UNCHECK FAV IF EMPTY
    if (f && favs.size === 0) {
        if(fEl) fEl.checked = false;
        f = false;
    }

    FILTERED_LIST = DATA.filter(x => {
        const name = (x.i18n && x.i18n[CUR_LANG] ? x.i18n[CUR_LANG].name : x.name).toLowerCase();
        if(txt && !name.includes(txt)) return false;
        if(years.length && !years.includes(x.year)) return false;
        
        const gStr = x.i18n?.uk?.genre || "";
        if(genres.length && !gStr.split(", ").some(g=>genres.includes(g))) return false;
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

// === HELPER TO CREATE BADGES via DOM (No HTML strings) ===
function createBadge(text, type) {
    const span = document.createElement("span");
    span.textContent = text;
    if (type === 'leaving') {
        span.className = "tag-badge tag-leaving";
        span.style.cssText = "font-size:10px; padding:2px 4px; border-radius:4px; margin-right:4px;";
    } else if (type === 'new') {
        span.className = "tag-badge tag-new";
        span.style.cssText = "font-size:10px; padding:2px 4px; border-radius:4px; margin-right:4px;";
    } else if (type === 'tier') {
        span.className = text === 'AAA' ? "tier-badge tier-AAA" : "tier-badge tier-Indie";
    } else {
        span.className = "tier-badge tag-badge";
    }
    return span;
}

function render() {
    const t = I18N[CUR_LANG];
    const titleEl = document.getElementById("lblTitle");
    if(titleEl) titleEl.innerText = `${t.title} (${FILTERED_LIST.length})`;

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
    const tbody = document.getElementById("tbody");
    if(tbody) tbody.innerHTML = ""; // Clear via innerHTML only for reset

    const tilesV = document.getElementById("tilesView");
    if(tilesV) tilesV.style.display = isTiles ? "block" : "none";
    const tilesContainer = document.getElementById("tiles");
    if(tilesContainer) tilesContainer.innerHTML = "";

    const btnTable = document.getElementById("btnTable");
    if(btnTable) btnTable.className = isTiles ? "btn" : "btn active";
    
    const btnTiles = document.getElementById("btnTiles");
    if(btnTiles) btnTiles.className = isTiles ? "btn active" : "btn";
    
    renderPagination(totalPages);

    const getRowData = (x) => {
        const d = x.i18n ? x.i18n[CUR_LANG] : {name: x.name, genre: x.genre};
        return { ...x, displayName: d.name, displayGenre: d.genre };
    };

    // === TEMPLATE BASED RENDERING ===
    
    // Templates
    const tmplRow = document.getElementById("tmpl-row");
    const tmplTile = document.getElementById("tmpl-tile");

    pageData.forEach((raw, i) => {
        const x = getRowData(raw);
        const globalIdx = start + i;
        const imgClass = x.no_avatar ? "no-avatar" : "";
        const imgSrc = x.no_avatar ? TRANSPARENT_PIXEL : x.image;
        const isFav = favs.has(x.id);

        if (isTiles && tmplTile) {
            const clone = tmplTile.content.cloneNode(true);
            
            // Image
            const img = clone.querySelector(".img-src");
            img.src = imgSrc;
            if(x.no_avatar) img.classList.add("no-avatar");
            
            // Onclick
            clone.querySelector(".tile").onclick = () => openModal(globalIdx);

            // Tags
            const tagsCont = clone.querySelector(".tags-container");
            (x.tags || []).forEach(tg => {
                if(tg === "Leaving Soon") tagsCont.appendChild(createBadge("👋", 'leaving'));
                else if(tg === "New Added") tagsCont.appendChild(createBadge("NEW", 'new'));
            });

            // Fav
            const favBtn = clone.querySelector(".btn-fav");
            if(isFav) favBtn.classList.add("on");
            favBtn.dataset.id = x.id;
            favBtn.onclick = (e) => { e.stopPropagation(); toggleFav(favBtn); };

            // Text
            clone.querySelector(".txt-name").textContent = x.displayName;
            clone.querySelector(".txt-year").textContent = x.year;
            
            const rateEl = clone.querySelector(".txt-rating");
            rateEl.textContent = `★ ${x.rating || '-'}`;
            rateEl.style.color = x.rating>=80?'#008a4b':(x.rating>=60?'#bf8600':'var(--text-sec)');

            tilesContainer.appendChild(clone);

        } else if (!isTiles && tmplRow) {
            const clone = tmplRow.content.cloneNode(true);
            
            // Image
            const img = clone.querySelector(".img-src");
            img.src = imgSrc;
            img.classList.add(x.no_avatar ? "no-avatar" : "cover"); // Ensure base class + modifier
            img.onclick = () => openModal(globalIdx);

            // Fav
            const favBtn = clone.querySelector(".btn-fav");
            if(isFav) favBtn.classList.add("on");
            favBtn.dataset.id = x.id;
            favBtn.onclick = () => toggleFav(favBtn);

            // Text info
            clone.querySelector(".txt-name").textContent = x.displayName;
            clone.querySelector(".txt-dev").textContent = x.developer;
            
            // Tags (badges)
            const tagsCont = clone.querySelector(".tags-container");
            (x.tags || []).forEach(tg => {
                if(tg === "Leaving Soon") tagsCont.appendChild(createBadge("Leaving", 'leaving'));
                else if(tg === "New Added") tagsCont.appendChild(createBadge("New", 'new'));
                else if(!["PC","Console","Ultimate"].includes(tg)) tagsCont.appendChild(createBadge(tg, 'other'));
            });
            tagsCont.appendChild(createBadge(x.tier === "AAA" ? "AAA" : "Indie/AA", 'tier'));

            // Other cols
            clone.querySelector(".txt-genre").textContent = x.displayGenre;
            
            const rateVal = clone.querySelector(".txt-rating");
            rateVal.textContent = x.rating || '-';
            rateVal.className = `rating-val ${x.rating>=80?'rating-high':(x.rating>=60?'rating-mid':'rating-low')}`;
            
            clone.querySelector(".txt-rating-src").textContent = x.ratingSource;
            clone.querySelector(".txt-year").textContent = x.year;
            clone.querySelector(".txt-hours").textContent = x.hours;

            tbody.appendChild(clone);
        }
    });
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

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}