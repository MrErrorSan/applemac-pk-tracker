/* Mock engine for the redesign. Shared by every variant: same data, same
   information architecture, different skin and layout. Nothing here writes. */

const DATA = window.MOCK.products;
const META = window.MOCK.meta;
const HISTORY = window.MOCK.history;

const FAMILIES = [
  {v: "",            label: "Everything"},
  {v: "macbook_pro", label: "MacBook Pro"},
  {v: "macbook_air", label: "MacBook Air"},
  {v: "iphone",      label: "iPhone"},
];

const FACETS = [
  {key: "model", label: "Model",   get: p => p.model},
  {key: "chip",  label: "Chip",    get: p => p.chip},
  {key: "ram",   label: "Memory",  get: p => p.ram_gb,     fmt: gb},
  {key: "ssd",   label: "Storage", get: p => p.storage_gb, fmt: gb},
  {key: "color", label: "Colour",  get: p => p.color},
];

const VARIANTS = {
  e: {name: "Ledger + rail", layout: "table", filters: "rail",
      blurb: "The chosen direction: Counter's filter rail, Ledger's paper and serif figures."},
  a: {name: "Ledger",   layout: "table", filters: "dropdown",
      blurb: "The current identity, cleaned up. Numbers set in serif, paper ground."},
  b: {name: "Broadside", layout: "table", filters: "dropdown",
      blurb: "Dark, editorial, the gap set large. Fewer rows, more force."},
  c: {name: "Counter",  layout: "table", filters: "rail",
      blurb: "Dense and quiet. Filters live in a rail, not menus. Most rows per screen."},
  d: {name: "Shelf",    layout: "cards", filters: "dropdown",
      blurb: "No table. Each listing is a card, built for a phone first."},
};

let S = {
  variant: localStorage.getItem("mockVariant") || "e",
  family: "", sel: {model: [], chip: [], ram: [], ssd: [], color: []},
  term: "", sort: "diff", dir: -1, open: null, pop: null,
};

/* ------------------------------------------------------------- format */
function gb(n) {
  return n == null ? null : (n >= 1024 && n % 1024 === 0 ? (n / 1024) + " TB" : n + " GB");
}
const num = n => n == null ? null : n.toLocaleString("en-US");
const pkr = n => n == null ? null : "PKR " + num(n);
const ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
const esc = s => s == null ? "" : String(s).replace(/[&<>"']/g, c => ESC[c]);
const safe = u => typeof u === "string" && u.startsWith("https://applemac.pk/") ? esc(u) : null;
const link = (u, l) => {
  const h = safe(u);
  return h ? `<a href="${h}" target="_blank" rel="noopener">${esc(l)}</a>` : esc(l);
};
const stamp = iso => {
  const d = new Date(iso);
  return isNaN(d) ? String(iso) : d.toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", timeZone: "Asia/Karachi"}) + " PKT";
};
const day = iso => {
  const d = new Date(iso);
  return isNaN(d) ? "—" : d.toLocaleDateString("en-GB",
    {day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Karachi"});
};
const diffOf = p => p.benchmark == null ? null : p.price - p.benchmark;
const specLine = p =>
  [gb(p.ram_gb), gb(p.storage_gb)].filter(Boolean).join("  /  ") || "not stated";

/* ------------------------------------------------------------ filtering */
function pass(p, skip) {
  if (S.family && p.family !== S.family) return false;
  if (S.term) {
    const hay = [p.name, p.chip, p.color].filter(Boolean).join(" ").toLowerCase();
    if (!hay.includes(S.term)) return false;
  }
  for (const f of FACETS) {
    if (f.key === skip) continue;
    const sel = S.sel[f.key];
    if (sel.length && !sel.includes(String(f.get(p)))) return false;
  }
  return true;
}
const visible = () => DATA.filter(p => pass(p, null));
const anyFilter = () => S.term || FACETS.some(f => S.sel[f.key].length);

/* Counts are computed with this facet's own selection lifted, so ticking one
   value does not zero every other value in the same menu. */
function facetValues(f) {
  const pool = DATA.filter(p => pass(p, f.key));
  const counts = new Map();
  for (const p of pool) {
    const v = f.get(p);
    if (v != null) counts.set(String(v), (counts.get(String(v)) || 0) + 1);
  }
  const inFamily = DATA.filter(p => !S.family || p.family === S.family);
  const all = new Set(inFamily.map(p => f.get(p)).filter(v => v != null).map(String));
  const numeric = v => /^[\d.]+$/.test(v);
  return [...all].sort((a, b) =>
    numeric(a) && numeric(b) ? parseFloat(a) - parseFloat(b) : a.localeCompare(b)
  ).map(v => ({v, n: counts.get(v) || 0}));
}

const countText = () => {
  const n = visible().length;
  return n === DATA.length ? `All ${DATA.length} listings`
                           : `${n} of ${DATA.length} listings`;
};

/* --------------------------------------------------------------- chrome */
function renderSwitcher() {
  document.getElementById("switcher").innerHTML =
    `<span class="sw-label">Design</span>` +
    Object.entries(VARIANTS).map(([k, v]) =>
      `<button type="button" data-v="${k}" aria-pressed="${S.variant === k}"
        title="${esc(v.blurb)}">${esc(v.name)}</button>`).join("") +
    `<span class="sw-blurb">${esc(VARIANTS[S.variant].blurb)}</span>`;
  document.querySelectorAll("#switcher button").forEach(b => b.onclick = () => {
    S.variant = b.dataset.v;
    localStorage.setItem("mockVariant", S.variant);
    S.open = null; S.pop = null;
    render();
  });
}

function renderMeta() {
  document.getElementById("runmeta").innerHTML = `
    <div><dt>Last checked</dt><dd>${esc(stamp(META.generated_at))}</dd></div>
    <div><dt>Listings</dt><dd>${DATA.length}</dd></div>
    <div><dt>USD to PKR</dt><dd>${META.fx_rate.toFixed(2)}</dd></div>
    <div><dt>Duty assumed</dt><dd>${Math.round(META.duty_percent * 100)}%</dd></div>`;
}

function renderTabs() {
  const tabs = document.getElementById("tabs");
  tabs.innerHTML = FAMILIES.map(f => {
    const n = DATA.filter(p => !f.v || p.family === f.v).length;
    return `<button type="button" role="tab" data-f="${esc(f.v)}"
      aria-selected="${S.family === f.v}">${esc(f.label)}<span class="n">${n}</span></button>`;
  }).join("");
  tabs.querySelectorAll("button").forEach(b => b.onclick = () => {
    S.family = b.dataset.f;
    S.sel = {model: [], chip: [], ram: [], ssd: [], color: []};
    S.open = null; S.pop = null;
    render();
  });
}

/* Two filter treatments. Dropdowns keep the top light; the rail trades
   horizontal space for never hiding a value behind a menu. */
function renderFilters() {
  const mode = VARIANTS[S.variant].filters;
  document.body.dataset.filters = mode;
  const box = document.getElementById("filters");

  if (mode === "rail") {
    box.innerHTML = `<input class="search" id="search" type="search" value="${esc(S.term)}"
        placeholder="Search name, chip or colour" aria-label="Search listings">` +
      FACETS.map(f => {
        const vals = facetValues(f);
        if (vals.length < 2) return "";
        return `<div class="railgroup" data-key="${f.key}">
          <h4>${esc(f.label)}</h4>
          ${vals.map(o => `<label class="${o.n ? "" : "off"}">
            <input type="checkbox" data-v="${esc(o.v)}" ${S.sel[f.key].includes(o.v) ? "checked" : ""}>
            <span>${esc(f.fmt ? f.fmt(+o.v) : o.v)}</span>
            <span class="c">${o.n}</span></label>`).join("")}
        </div>`;
      }).join("");
    box.querySelectorAll(".railgroup").forEach(g => {
      g.querySelectorAll("input").forEach(cb => cb.onchange = () => toggleFacet(g.dataset.key, cb));
    });
  } else {
    box.innerHTML = FACETS.map(f => {
      const vals = facetValues(f), sel = S.sel[f.key];
      const dead = vals.length < 2;
      return `<div class="dd" data-key="${f.key}"${dead ? " data-dead" : ""}>
        <button type="button" aria-expanded="${S.pop === f.key}" ${dead ? "disabled" : ""}>
          ${esc(f.label)}${sel.length ? `<span class="cnt">${sel.length}</span>` : ""}
          <span class="car" aria-hidden="true">▾</span></button>
        ${S.pop === f.key ? `<div class="pop">${vals.map(o => `
          <label class="${o.n ? "" : "off"}"><input type="checkbox" data-v="${esc(o.v)}"
            ${sel.includes(o.v) ? "checked" : ""}><span>${esc(f.fmt ? f.fmt(+o.v) : o.v)}</span>
            <span class="c">${o.n}</span></label>`).join("")}</div>` : ""}
      </div>`;
    }).join("") +
      `<input class="search" id="search" type="search" value="${esc(S.term)}"
        placeholder="Search name, chip or colour" aria-label="Search listings">`;

    box.querySelectorAll(".dd").forEach(dd => {
      const key = dd.dataset.key;
      dd.querySelector("button").onclick = e => {
        e.stopPropagation();
        S.pop = S.pop === key ? null : key;
        renderFilters();
      };
      dd.querySelectorAll(".pop input").forEach(cb => cb.onchange = () => toggleFacet(key, cb));
      const pop = dd.querySelector(".pop");
      if (pop) pop.onclick = e => e.stopPropagation();
    });
  }

  const s = box.querySelector("#search");
  s.oninput = e => {
    S.term = e.target.value.trim().toLowerCase();
    S.open = null;
    renderApplied(); renderList();
  };
}

function toggleFacet(key, cb) {
  const v = cb.dataset.v, sel = S.sel[key];
  S.sel[key] = cb.checked ? [...sel, v] : sel.filter(x => x !== v);
  S.open = null;
  render();
}

document.addEventListener("click", () => {
  if (S.pop) { S.pop = null; renderFilters(); }
});

function renderApplied() {
  const chips = [];
  for (const f of FACETS)
    for (const v of S.sel[f.key])
      chips.push(`<span class="chip"><b>${esc(f.label)}</b> ${esc(f.fmt ? f.fmt(+v) : v)}
        <button type="button" data-k="${f.key}" data-v="${esc(v)}"
          aria-label="Remove ${esc(f.label)} ${esc(v)}">×</button></span>`);
  if (S.term)
    chips.push(`<span class="chip"><b>Search</b> ${esc(S.term)}
      <button type="button" data-k="term" aria-label="Clear the search">×</button></span>`);

  const box = document.getElementById("applied");
  box.innerHTML = `<span class="count">${countText()}</span>` + chips.join("") +
    (chips.length ? `<button class="clearall" type="button" id="clr">Clear all</button>` : "");
  box.querySelectorAll(".chip button").forEach(b => b.onclick = () => {
    if (b.dataset.k === "term") S.term = "";
    else S.sel[b.dataset.k] = S.sel[b.dataset.k].filter(x => x !== b.dataset.v);
    S.open = null;
    render();
  });
  const clr = box.querySelector("#clr");
  if (clr) clr.onclick = () => {
    S.sel = {model: [], chip: [], ram: [], ssd: [], color: []};
    S.term = ""; S.open = null;
    render();
  };
}

/* ---------------------------------------------------------------- table */
const COLS = [
  {k: "name",      label: "Product"},
  {k: "spec",      label: "Specification"},
  {k: "price",     label: "Price here",        num: 1},
  {k: "benchmark", label: "Est. Apple landed", num: 1},
  {k: "diff",      label: "Difference",        num: 1},
];
const val = (p, k) => k === "diff" ? diffOf(p) : k === "spec" ? (p.chip || "") : p[k];

function sorted() {
  return visible().sort((a, b) => {
    let x = val(a, S.sort), y = val(b, S.sort);
    if (x == null) return 1;
    if (y == null) return -1;
    /* "Descending" on Difference should mean the biggest saving first, which is
       the most negative number. Flip the sign so the arrow means what it looks
       like it means. */
    if (S.sort === "diff") { x = -x; y = -y; }
    return (x > y ? 1 : x < y ? -1 : 0) * S.dir;
  });
}

function diffCell(p) {
  const d = diffOf(p);
  if (d == null)
    return `<span class="nodata">no verified Apple price<br>for this specification</span>`;
  const pctOff = Math.abs(Math.round(d / p.benchmark * 100));
  return `<span class="diff ${d < 0 ? "below" : "above"}">${d < 0 ? "−" : "+"}${
    num(Math.abs(d))}<small>${pctOff}% ${d < 0 ? "cheaper than Apple" : "dearer than Apple"}</small></span>`;
}

function renderList() {
  const rows = sorted();
  const host = document.getElementById("listing");

  if (VARIANTS[S.variant].layout === "cards") {
    host.innerHTML = rows.length ? `<div class="cards">${rows.map(p => `
      <article class="pcard" data-slug="${esc(p.slug)}">
        <div class="pcard-main">
          <h3>${link(p.url, p.name)}</h3>
          <p class="pcard-spec">${esc(p.chip || "chip not stated")}
            <span>${esc(specLine(p))}</span></p>
          <p class="pcard-prices"><b>${esc(pkr(p.price))}</b>
            ${p.benchmark == null ? "" : `<span>Apple est. ${esc(pkr(p.benchmark))}</span>`}</p>
        </div>
        <div class="pcard-diff">${diffCell(p)}
          <button class="expander" type="button" aria-expanded="false"
            aria-label="Details for ${esc(p.name)}">Details</button></div>
      </article>`).join("")}</div>` : emptyHTML();
  } else {
    host.innerHTML = `<div class="tablewrap"><table>
      <thead><tr>${COLS.map(c => {
        const on = S.sort === c.k;
        return `<th class="${c.num ? "num" : ""}" data-k="${c.k}" scope="col"
          aria-sort="${on ? (S.dir < 0 ? "descending" : "ascending") : "none"}"
          >${esc(c.label)}${on ? `<span class="arrow">${S.dir < 0 ? "▼" : "▲"}</span>` : ""}</th>`;
      }).join("")}<th style="width:1%"></th></tr></thead>
      <tbody>${rows.map(p => `<tr data-slug="${esc(p.slug)}">
        <td><div class="pname">${link(p.url, p.name)}</div>
            <div class="psub">${esc(p.model)}${p.color ? " — " + esc(p.color) : ""}</div></td>
        <td><div class="spec">${esc(p.chip || "—")}<span>${esc(specLine(p))}</span></div></td>
        <td class="num money">${esc(pkr(p.price))}</td>
        <td class="num money est">${p.benchmark == null
          ? '<span class="nodata">—</span>' : esc(pkr(p.benchmark))}</td>
        <td class="num">${diffCell(p)}</td>
        <td class="num"><button class="expander" type="button" aria-expanded="false"
          aria-label="Details for ${esc(p.name)}">+</button></td></tr>`).join("")}
      </tbody></table>${rows.length ? "" : emptyHTML()}</div>`;

    host.querySelectorAll("th[data-k]").forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      S.dir = S.sort === k ? -S.dir : -1;
      S.sort = k; S.open = null;
      renderList();
    });
  }

  host.querySelectorAll("[data-slug]").forEach(el => {
    el.querySelector(".expander").onclick = () => toggle(el);
  });
  const clr = host.querySelector("#clearInEmpty");
  if (clr) clr.onclick = () => {
    S.sel = {model: [], chip: [], ram: [], ssd: [], color: []};
    S.term = ""; render();
  };
  if (S.open) {
    const el = host.querySelector(`[data-slug="${CSS.escape(S.open)}"]`);
    if (el) openRow(el); else S.open = null;
  }
}

const emptyHTML = () => `<div class="empty">
  <p>Nothing on the shelf matches these filters.</p>
  ${anyFilter() ? `<button class="clearall" type="button" id="clearInEmpty">Clear all filters</button>` : ""}
</div>`;

/* --------------------------------------------------------------- drawer */
function toggle(el) {
  const slug = el.dataset.slug, was = S.open === slug;
  document.querySelectorAll(".detail").forEach(d => d.remove());
  document.querySelectorAll(".is-open").forEach(r => {
    r.classList.remove("is-open");
    const b = r.querySelector(".expander");
    b.textContent = b.dataset.long ? "Details" : "+";
    b.setAttribute("aria-expanded", "false");
  });
  S.open = was ? null : slug;
  if (!was) openRow(el);
}

function sameSpec(p) {
  const twins = DATA.filter(x => x.config_key === p.config_key);
  if (twins.length < 2)
    return `<p class="quiet">Nothing else on the shelf has this exact chip, memory and
      storage, so there is nothing to compare it against.</p>`;
  const byPrice = [...twins].sort((a, b) => a.price - b.price);
  const low = byPrice[0].price;
  const gap = p.price - low;
  /* Several listings often share a specification at the identical price. Naming
     one of them "the cheapest" would be a distinction the prices do not support. */
  const head = gap > 0
    ? `<p><b>${esc(pkr(gap))} more</b> than the cheapest of the ${twins.length}
       listings with this exact specification.</p>`
    : byPrice.filter(t => t.price === low).length === twins.length
      ? `<p>All ${twins.length} listings with this exact specification are priced the
         same, at <b>${esc(pkr(low))}</b>.</p>`
      : `<p><b>Nothing with this exact specification is cheaper.</b> ${
         byPrice.filter(t => t.price === low).length > 1
           ? `It shares the lowest price with ${
              byPrice.filter(t => t.price === low).length - 1} other listing${
              byPrice.filter(t => t.price === low).length > 2 ? "s" : ""}.`
           : `The next one up is ${esc(pkr(byPrice.find(t => t.price > low).price))}.`}</p>`;
  return head + `<table class="ladder"><tbody>${byPrice.slice(0, 6).map(t => `
    <tr class="${t.slug === p.slug ? "self" : ""}">
      <td>${esc(t.color || t.name)}</td>
      <td class="r">${esc(pkr(t.price))}</td></tr>`).join("")}</tbody></table>`;
}

function markdown(p) {
  if (!(p.old_price && p.old_price > p.price))
    return `<p class="quiet">The shop shows no earlier price for this listing, so there
      is no markdown to report.</p>`;
  return `<p>Listed down from ${esc(pkr(p.old_price))} —
    <b>${esc(pkr(p.old_price - p.price))} off</b> the shop's own earlier price.</p>`;
}

/* The x-axis is real time, not run number. Six checks three hours apart must not
   draw the same picture as six checks six months apart. */
function series(pts) {
  const t = pts.map(x => new Date(x[0]).getTime()), v = pts.map(x => x[1]);
  const t0 = Math.min(...t), t1 = Math.max(...t);
  const lo = Math.min(...v), hi = Math.max(...v);
  const H = 46, pad = 4;
  const X = i => t1 === t0 ? 0 : ((t[i] - t0) / (t1 - t0)) * 100;
  const Y = i => hi === lo ? H / 2 : pad + (1 - (v[i] - lo) / (hi - lo)) * (H - pad * 2);
  const d = pts.map((_, i) => `${X(i).toFixed(2)},${Y(i).toFixed(2)}`).join(" L");
  return `<svg viewBox="0 0 100 ${H + 2}" preserveAspectRatio="none" role="img"
      aria-label="Price from ${esc(day(pts[0][0]))} to ${esc(day(pts.at(-1)[0]))}, low ${
      esc(pkr(lo))}, high ${esc(pkr(hi))}">
      <line class="axis" x1="0" y1="${H + 1}" x2="100" y2="${H + 1}"></line>
      <path d="M${d}" vector-effect="non-scaling-stroke"></path></svg>
    <div class="ends"><span>${esc(day(pts[0][0]))}</span>
      <span>low ${esc(pkr(lo))} — high ${esc(pkr(hi))}</span>
      <span>${esc(day(pts.at(-1)[0]))}</span></div>`;
}

function chart(p) {
  const pts = (HISTORY[p.slug] || []).filter(x => typeof x[1] === "number" && x[1] > 0);
  const t = pts.map(x => new Date(x[0]).getTime());
  const spanDays = t.length ? (Math.max(...t) - Math.min(...t)) / 86400000 : 0;

  const real = spanDays < 2
    ? `<p class="quiet">Tracking began ${esc(day(META.first_run))}. All ${pts.length}
       checks so far fall inside a single day, so there is no trend to draw. This
       becomes a real chart on its own as the daily run builds history.</p>`
    : series(pts);

  return `<div class="chart">${real}
    <div class="preview">
      <p class="tag">Invented data — here only to show what this chart becomes</p>
      ${series(FAKE)}
      <p class="quiet">Eight months of daily checks. The point is the shape: held high
        into March, stepped down in April, steady ever since.</p>
    </div></div>`;
}

function openRow(el) {
  const p = DATA.find(x => x.slug === el.dataset.slug);
  if (!p) return;
  el.classList.add("is-open");
  const b = el.querySelector(".expander");
  b.dataset.long = b.textContent.trim() === "Details" ? "1" : "";
  b.textContent = b.dataset.long ? "Close" : "−";
  b.setAttribute("aria-expanded", "true");

  const inner = `<div class="dgrid">
    <div>
      <h4>This listing</h4>
      <dl class="facts">
        <dt>Chip</dt><dd>${esc(p.chip || "not stated")}</dd>
        <dt>Memory</dt><dd>${p.ram_gb ? esc(gb(p.ram_gb)) : "not stated"}</dd>
        <dt>Storage</dt><dd>${p.storage_gb ? esc(gb(p.storage_gb)) : "not stated"}</dd>
        <dt>Screen</dt><dd>${p.screen_size ? esc(p.screen_size + " inch") : "not stated"}</dd>
        <dt>Colour</dt><dd>${esc(p.color || "not stated")}</dd>
        <dt>First tracked</dt><dd>${esc(day(p.first_seen))}</dd>
      </dl>
    </div>
    <div>
      <section class="cmp"><h4>Same specification on the shelf</h4>${sameSpec(p)}</section>
      <section class="cmp"><h4>The shop's own markdown</h4>${markdown(p)}</section>
      <section class="cmp"><h4>Price since tracking began</h4>${chart(p)}</section>
    </div>
  </div>`;

  if (el.tagName === "TR") {
    const tr = document.createElement("tr");
    tr.className = "detail";
    const td = document.createElement("td");
    td.colSpan = COLS.length + 1;
    td.innerHTML = inner;
    tr.appendChild(td);
    el.after(tr);
  } else {
    const box = document.createElement("div");
    box.className = "detail";
    box.innerHTML = inner;
    el.after(box);
  }
}

/* Fabricated, and labelled as such wherever it is drawn. It exists so the chart
   can be judged as a design before eight months of real runs exist. */
const FAKE = (() => {
  const out = [], start = new Date("2026-01-20").getTime();
  const wobble = [0, 0, 1, 0, 1, 0, 0, -1, 0, 1, 0, 0];
  for (let i = 0; i < 240; i++) {
    let v = i < 70 ? 869000 : i < 82 ? 869000 - (i - 70) * 5200 : 806000;
    v += wobble[i % 12] * 1800 + (i % 29 === 0 ? 4200 : 0);
    out.push([new Date(start + i * 86400000).toISOString(), Math.round(v)]);
  }
  return out;
})();

/* ----------------------------------------------------------------- boot */
function render() {
  document.documentElement.dataset.variant = S.variant;
  renderSwitcher();
  renderMeta();
  renderTabs();
  renderFilters();
  renderApplied();
  renderList();
}
render();
