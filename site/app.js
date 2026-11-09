/* ShipBrief web page. Plain JS, no dependencies, no trackers.
 * Security: all data is rendered with textContent / setAttribute; links must be http(s). */
(function () {
  "use strict";

  var SECTIONS = [
    ["topStories", "Top stories"],
    ["modelsAndAgents", "New models and agents"],
    ["tools", "Tools worth trying"],
    ["openSource", "Open-source releases"],
    ["research", "Research highlights"]
  ];
  var ROLES = ["developer", "researcher", "product", "founder", "designer"];
  var STORE_KEY = "shipbrief.filters.v1";
  var THEME_KEY = "shipbrief.theme.v1";
  var STALE_HOURS = 48;

  // ------------------------------------------------------------ storage (never required)
  function load(key, fallback) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode etc. */ }
  }

  // ------------------------------------------------------------ helpers
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) n.setAttribute(k, attrs[k]);
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function safeUrl(u) { return typeof u === "string" && /^https?:\/\//i.test(u) ? u : null; }
  function link(url, text) {
    var u = safeUrl(url);
    if (!u) return el("span", null, text);
    return el("a", { href: u, rel: "noopener noreferrer", target: "_blank" }, text);
  }
  function timeAgo(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return "";
    var h = Math.round((Date.now() - t) / 3600000);
    if (h < 1) return "just now";
    if (h < 48) return h + "h ago";
    return Math.round(h / 24) + "d ago";
  }
  function genLabel(g) {
    if (!g) return "";
    if (g === "extractive") return "from source text";
    if (g === "template") return "template";
    return "AI-written (" + g + ")";
  }
  function fetchJson(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(path + ": HTTP " + r.status);
      return r.json();
    });
  }

  // ------------------------------------------------------------ theme
  function applyTheme(theme) {
    var root = document.documentElement;
    if (theme === "dark" || theme === "light") root.setAttribute("data-theme", theme);
    else root.removeAttribute("data-theme");
    var dark = theme === "dark" || (!theme && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
    var btn = $("theme-toggle");
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
    btn.textContent = dark ? "Light mode" : "Dark mode";
  }
  function initTheme() {
    applyTheme(load(THEME_KEY, null));
    $("theme-toggle").addEventListener("click", function () {
      var nowDark = $("theme-toggle").getAttribute("aria-pressed") === "true";
      var next = nowDark ? "light" : "dark";
      save(THEME_KEY, next);
      applyTheme(next);
    });
  }

  // ------------------------------------------------------------ filters
  var filters = load(STORE_KEY, { roles: [], tags: [] });
  if (!filters || !Array.isArray(filters.roles) || !Array.isArray(filters.tags)) filters = { roles: [], tags: [] };

  function matches(item) {
    var r = filters.roles, t = filters.tags;
    var roleOk = !r.length || (item.roles || []).some(function (x) { return x === "everyone" || r.indexOf(x) >= 0; });
    var tagOk = !t.length || (item.tags || []).some(function (x) { return t.indexOf(x) >= 0; });
    return roleOk && tagOk;
  }

  function chip(label, group, value) {
    var on = filters[group].indexOf(value) >= 0;
    var b = el("button", { type: "button", "class": "chip", "aria-pressed": on ? "true" : "false" }, label);
    b.addEventListener("click", function () {
      var arr = filters[group], i = arr.indexOf(value);
      if (i >= 0) arr.splice(i, 1); else arr.push(value);
      b.setAttribute("aria-pressed", i >= 0 ? "false" : "true");
      save(STORE_KEY, filters);
      renderSections();
    });
    return b;
  }

  function buildFilterChips(digest) {
    var rc = $("role-chips"), tc = $("tag-chips");
    rc.textContent = ""; tc.textContent = "";
    ROLES.forEach(function (r) { rc.appendChild(chip(r.charAt(0).toUpperCase() + r.slice(1), "roles", r)); });
    var counts = {};
    SECTIONS.forEach(function (s) {
      (digest.sections[s[0]] || []).forEach(function (it) { (it.tags || []).forEach(function (t) { counts[t] = (counts[t] || 0) + 1; }); });
    });
    filters.tags.forEach(function (t) { if (!counts[t]) counts[t] = 0; });
    Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); })
      .forEach(function (t) { tc.appendChild(chip(t, "tags", t)); });
    $("clear-filters").onclick = function () { filters = { roles: [], tags: [] }; save(STORE_KEY, filters); buildFilterChips(digest); renderSections(); };
  }

  // ------------------------------------------------------------ rendering
  var current = null;

  function itemCard(it, isTool) {
    var li = el("li");
    var card = el("article", { "class": "card" });
    var h = el("h3");
    h.appendChild(link(it.url, it.title));
    card.appendChild(h);

    var meta = el("p", { "class": "meta" });
    meta.appendChild(el("span", null, it.source));
    var ago = timeAgo(it.publishedAt);
    if (ago) meta.appendChild(el("time", { datetime: it.publishedAt }, ago));
    if (it.version) meta.appendChild(el("span", null, it.version));
    if (it.hnScore) meta.appendChild(el("span", null, it.hnScore + " HN points"));
    card.appendChild(meta);

    if (isTool && it.whatItDoes) {
      var dl = el("dl", { "class": "fields" });
      var d1 = el("div"); d1.appendChild(el("dt", null, "What it does:")); d1.appendChild(el("dd", null, it.whatItDoes)); dl.appendChild(d1);
      var d2 = el("div"); d2.appendChild(el("dt", null, "Who it's for:")); d2.appendChild(el("dd", null, it.whoItsFor)); dl.appendChild(d2);
      card.appendChild(dl);
    } else {
      card.appendChild(el("p", { "class": "summary" }, it.summary));
    }

    if (it.tags && it.tags.length) {
      var ul = el("ul", { "class": "tags", "aria-label": "Tags" });
      it.tags.slice(0, 6).forEach(function (t) { ul.appendChild(el("li", { "class": "tag" }, t)); });
      card.appendChild(ul);
    }

    var links = el("div", { "class": "links" });
    links.appendChild(link(it.url, "Source"));
    if (safeUrl(it.discussionUrl)) links.appendChild(link(it.discussionUrl, "Discussion"));
    (it.related || []).slice(0, 3).forEach(function (r) { links.appendChild(link(r.url, "Also: " + r.source)); });
    links.appendChild(el("span", { "class": "gen", title: "How this summary was written" }, genLabel(it.generatedBy)));
    card.appendChild(links);
    li.appendChild(card);
    return li;
  }

  function renderSections() {
    var host = $("sections");
    host.textContent = "";
    if (!current) return;
    var active = filters.roles.length + filters.tags.length;
    $("filter-count").textContent = active ? "(" + active + " active)" : "";
    SECTIONS.forEach(function (s) {
      var all = current.sections[s[0]] || [];
      if (!all.length) return;
      var shown = all.filter(matches);
      var sec = el("section", { "aria-labelledby": "sec-" + s[0] });
      var h2 = el("h2", { id: "sec-" + s[0] }, s[1]);
      h2.appendChild(el("span", { "class": "count" }, active ? shown.length + " of " + all.length : String(all.length)));
      sec.appendChild(h2);
      if (!shown.length) {
        sec.appendChild(el("p", { "class": "empty" }, "Nothing here matches your filters today."));
      } else {
        var ul = el("ul", { "class": "cards" });
        shown.forEach(function (it) { ul.appendChild(itemCard(it, s[0] === "tools")); });
        sec.appendChild(ul);
      }
      host.appendChild(sec);
    });
  }

  function renderExtras(d) {
    var p = d.promptOfTheDay, w = d.tryThisToday;
    if (p) {
      $("pod").hidden = false;
      $("pod-name").textContent = p.title;
      $("pod-text").textContent = p.prompt;
      $("pod-use").textContent = p.useCase + (p.roles ? " · For: " + p.roles.join(", ") : "");
      var a = $("pod-src"); a.textContent = p.basedOn.title;
      if (safeUrl(p.basedOn.url)) { a.href = p.basedOn.url; a.target = "_blank"; } else a.removeAttribute("href");
      $("pod-gen").textContent = genLabel(p.generatedBy);
    }
    if (w) {
      $("try").hidden = false;
      $("try-name").textContent = w.title;
      $("try-roles").textContent = "For: " + (w.roles || []).join(", ");
      var ol = $("try-steps"); ol.textContent = "";
      w.steps.forEach(function (s) { ol.appendChild(el("li", null, s)); });
      var b = $("try-src"); b.textContent = w.basedOn.title;
      if (safeUrl(w.basedOn.url)) { b.href = w.basedOn.url; b.target = "_blank"; } else b.removeAttribute("href");
      $("try-gen").textContent = genLabel(w.generatedBy);
    }
  }

  function copyPrompt() {
    var text = $("pod-text").textContent, status = $("copy-status");
    function done(ok) { status.textContent = ok ? "Copied!" : "Select the text and copy it manually."; setTimeout(function () { status.textContent = ""; }, 2500); }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallback()); });
    } else done(fallback());
    function fallback() {
      try {
        var ta = el("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "absolute"; ta.style.left = "-9999px";
        document.body.appendChild(ta); ta.select(); var ok = document.execCommand("copy"); document.body.removeChild(ta); return ok;
      } catch (e) { return false; }
    }
  }

  function renderDigest(d, isLatest) {
    current = d;
    var date = new Date(d.date + "T12:00:00Z");
    var nice = date.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
    $("day-title").textContent = (isLatest ? "Today's brief · " : "Brief for ") + nice;
    var modeText = d.summaryMode === "extractive" ? "summaries from source text" :
      d.summaryMode === "llm" ? "AI-written summaries" : "partly AI-written summaries";
    $("day-meta").textContent = d.stats.itemsPublished + " items from " + d.stats.sourcesOk + " sources · " + modeText;
    $("headline").textContent = d.headline || "";
    document.title = "ShipBrief · " + d.date;
    buildFilterChips(d);
    renderSections();
    renderExtras(d);
    var stale = $("stale");
    var age = (Date.now() - Date.parse(d.generatedAt)) / 3600000;
    if (isLatest && age > STALE_HOURS) {
      stale.hidden = false;
      stale.textContent = "Heads up: this brief is " + Math.round(age / 24) + " days old. The daily update may be paused.";
    } else stale.hidden = true;
  }

  function renderArchive(index, selected) {
    var ul = $("archive-list"); ul.textContent = "";
    (index.days || []).forEach(function (day) {
      var li = el("li");
      var a = el("a", { href: "?date=" + encodeURIComponent(day.date) });
      if (day.date === selected) a.setAttribute("aria-current", "page");
      a.appendChild(el("span", { "class": "d" }, day.date));
      a.appendChild(el("span", { "class": "h" }, day.headline || ""));
      li.appendChild(a);
      ul.appendChild(li);
    });
    if (!ul.children.length) ul.appendChild(el("li", { "class": "muted" }, "No archive yet."));
  }

  function showError(msg) {
    $("day-title").textContent = "Couldn't load the brief";
    $("day-meta").textContent = msg;
  }

  function init() {
    initTheme();
    $("copy-prompt").addEventListener("click", copyPrompt);
    var param = new URLSearchParams(location.search).get("date");
    var wanted = param && /^\d{4}-\d{2}-\d{2}$/.test(param) ? param : null;
    fetchJson("data/index.json").catch(function () { return { days: [] }; }).then(function (index) {
      var latest = index.latest;
      var path = wanted ? "data/" + wanted + ".json" : "data/latest.json";
      return fetchJson(path).then(function (d) {
        if (!d || typeof d.schemaVersion !== "string" || d.schemaVersion.split(".")[0] !== "1") {
          throw new Error("Unsupported data version.");
        }
        renderDigest(d, !wanted || wanted === latest);
        renderArchive(index, d.date);
      });
    }).catch(function (e) { showError(e.message || String(e)); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
