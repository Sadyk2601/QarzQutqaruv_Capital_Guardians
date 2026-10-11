// QarzQutqaruv front end. All user/server text goes through textContent (no innerHTML with data).
"use strict";

const state = { lang: "en", band: "all", sort: "risk", current: null };
const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") el.setAttribute("style", v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const fmt = (n) => (n === null || n === undefined ? "-" : Math.round(n).toLocaleString("en-US"));
const money = (n) => (Math.abs(n) >= 1e9 ? (n / 1e9).toFixed(2) + " bn" : Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(1) + "M" : fmt(n)) + " UZS";
const pct = (p, d = 0) => (p * 100).toFixed(d) + "%";
const BAND = { red: "High risk", yellow: "Watch", green: "Low risk" };
const PT = { cannot_pay: "Cannot pay", silent: "Silent", slipping: "Slipping" };

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail || res.statusText;
    if (Array.isArray(msg)) msg = msg.map((d) => (d.loc ? d.loc.slice(1).join(".") + ": " : "") + d.msg).join("\n");
    throw new Error(msg);
  }
  return data;
}

// ---------- tabs ----------
function show(tab) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("active", p.id === tab));
  if (tab === "quality") loadQuality();
  if (tab === "audit") loadAudit();
  window.scrollTo({ top: 0 });
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
$("lang").addEventListener("change", (e) => {
  state.lang = e.target.value;
  loadToday();
  if (state.current) openBorrower(state.current, false);
});

// ---------- Today ----------
async function loadToday() {
  const d = await api(`/api/portfolio?lang=${state.lang}&sort=${state.sort}&band=${state.band}`);
  const s = d.summary;
  $("kpis").replaceChildren(
    h("div", { class: "kpi red" }, h("div", { class: "v" }, s.red), h("div", { class: "l" }, "High risk (red)")),
    h("div", { class: "kpi yellow" }, h("div", { class: "v" }, s.yellow), h("div", { class: "l" }, "Watch (yellow)")),
    h("div", { class: "kpi green" }, h("div", { class: "v" }, s.green), h("div", { class: "l" }, "Low risk (green)")),
    h("div", { class: "kpi" }, h("div", { class: "v" }, money(s.money_at_risk)), h("div", { class: "l" }, "Expected money at risk"))
  );
  const items = d.borrowers.slice(0, 120).map((b) =>
    h("button", { class: "item", onclick: () => openBorrower(b.id) },
      h("span", { class: `bar ${b.band}` }),
      h("span", {},
        h("div", { class: "t" }, `${b.name} · ${b.id}`),
        h("div", { class: "s" }, `${b.business_type.replace("_", " ")} · ${b.segment.replace("_", " ")} · ${b.region}`),
        h("div", { class: "s" }, b.top_reason)),
      h("span", { class: "r" }, pct(b.prob), h("div", { class: "s" }, money(b.money_at_risk))))
  );
  if (d.borrowers.length > 120) items.push(h("p", { class: "muted" }, `Showing 120 of ${d.borrowers.length}. Use the filters above.`));
  $("list").replaceChildren(...items);
}
function chipGroup(id, key) {
  $(id).addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    $(id).querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c === b));
    state[key] = b.dataset[key];
    loadToday();
  });
}
chipGroup("bandChips", "band");
chipGroup("sortChips", "sort");

async function loadPlan() {
  const minutes = Math.max(0, Math.min(5000, parseInt($("minutes").value || "0", 10)));
  const pilot = $("pilot").checked;
  const d = await api(`/api/daily-plan?minutes=${minutes}&pilot=${pilot}&limit=12`);
  const parts = Object.entries(d.counts).sort((a, b) => b[1] - a[1]).map(([a, n]) => `${n} × ${a.replace("_", " ")}`);
  const rows = d.rows.map((r) =>
    h("tr", { style: "cursor:pointer", onclick: () => openBorrower(r.borrower_id) },
      h("td", {}, h("span", { class: `badge ${r.band}` }, r.band), " ", r.name),
      h("td", {}, PT[r.problem_type] || r.problem_type),
      h("td", {}, r.title),
      h("td", { class: "num" }, r.minutes ? r.minutes + " min" : "-"),
      h("td", { class: "num" }, money(r.expected_saved))));
  $("plan").replaceChildren(
    h("div", { class: "box best" },
      h("strong", {}, `${d.minutes_used} of ${d.minutes_budget} minutes → `, parts.join(", ")),
      h("div", {}, `Expected loss prevented today: ${money(d.expected_saved_total)} · direct cost ${money(d.cost_total)}`),
      d.pilot_mode ? h("div", { class: "muted" }, `Pilot mode: Thompson sampling; ${d.control_group} borrowers in the control group (no action) to measure real effects.`) : null),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Borrower"), h("th", {}, "Problem"), h("th", {}, "Best action"), h("th", { class: "num" }, "Time"), h("th", { class: "num" }, "Saves (exp.)"))),
      h("tbody", {}, rows))),
    h("p", { class: "muted" }, "Top 12 shown. Effects: published field experiments + named assumptions (see Model quality → Model 2).")
  );
}
$("planBtn").addEventListener("click", () => loadPlan().catch(showErr));

// ---------- Borrower card ----------
async function openBorrower(id, switchTab = true) {
  state.current = id;
  const d = await api(`/api/borrower/${encodeURIComponent(id)}?lang=${state.lang}`);
  $("card").replaceChildren(...renderCard(d, true));
  if (switchTab) show("borrower");
}

function gauge(prob, t) {
  return h("div", { class: "gauge" },
    h("div", { class: "fill", style: `width:${Math.min(100, prob * 100)}%;background:${prob >= t.red ? "var(--red)" : prob >= t.yellow ? "var(--amber)" : "var(--green)"};opacity:.85` }),
    h("div", { class: "tick", style: `left:${t.yellow * 100}%` }, h("span", {}, `watch ${pct(t.yellow)}`)),
    h("div", { class: "tick", style: `left:${t.red * 100}%` }, h("span", {}, `red ${pct(t.red)}`)));
}

function chart(d) {
  const hist = d.history, n = hist.length;
  const months = d.calendar_months || hist.map((_, i) => `M${i + 1}`);
  const max = Math.max(...hist.map((x) => Math.max(x.due, x.paid)), 1);
  const cols = hist.map((x, i) =>
    h("div", { class: "col" },
      h("div", { class: "late" }, x.days_late ? `${x.days_late}d` : ""),
      h("div", { class: "pair" },
        h("div", { class: "due", style: `height:${(x.due / max) * 100}%`, title: `Due ${fmt(x.due)}` }),
        h("div", { class: `paid ${x.paid < x.due ? "short" : ""}`, style: `height:${Math.max(1, (x.paid / max) * 100)}%`, title: `Paid ${fmt(x.paid)}` })),
      h("div", { class: "m" }, String(months[i]).slice(-5))));
  return [h("div", { class: "chart", style: `grid-template-columns:repeat(${n},minmax(0,1fr))` }, cols),
    h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:#c5d3dc" }), "Due"),
      h("span", {}, h("i", { style: "background:var(--navy)" }), "Paid"),
      h("span", {}, h("i", { style: "background:var(--red)" }), "Paid less than due"), h("span", {}, "Nd = days late"))];
}

function renderCard(d, withDecision) {
  const out = [];
  const badges = [h("span", { class: `badge ${d.band}` }, BAND[d.band]),
    d.segment && h("span", { class: "badge soft" }, d.segment.replace("_", " ")),
    d.business_type && h("span", { class: "badge soft" }, d.business_type.replace("_", " ")),
    d.prior_loans_repaid > 0 && d.client_since_months && h("span", { class: "badge soft" }, `Loyal client: ${Math.round(d.client_since_months / 12)} yrs, ${d.prior_loans_repaid} loan(s) repaid`),
    d.synthetic && h("span", { class: "badge soft" }, "synthetic")];
  out.push(h("div", { class: "panel" },
    h("h2", {}, d.name, d.id !== "JURY" ? ` · ${d.id}` : ""),
    h("div", { class: "badges" }, badges),
    h("p", {}, h("strong", { style: "font-size:1.6rem" }, pct(d.prob, 0)), " chance of default next month · money at risk ", h("strong", {}, money(d.money_at_risk))),
    gauge(d.prob, d.thresholds),
    h("p", { class: "muted" }, `Outstanding ${money(d.outstanding)} · installment ${money(d.installment)} · ${d.term_months - d.months_elapsed} months left · rate ${(d.annual_rate * 100).toFixed(1)}%`,
      d.thresholds.segment_shift ? ` · segment threshold shift ${d.thresholds.segment_shift > 0 ? "+" : ""}${pct(d.thresholds.segment_shift)} (set by risk department)` : ""),
    ...chart(d)));

  // Step 1: WHO is in trouble and WHY (Model 1)
  const why = h("div", { class: "panel" }, h("h3", {}, h("span", { class: "step" }, "1"), "Who & why ", h("span", { class: "pill" }, "Model 1")),
    h("ul", { class: "clean" }, d.reasons.map((r) => h("li", {}, r.text))));
  if (d.own_norm_facts && d.own_norm_facts.length)
    why.append(h("div", { class: "box info" }, h("strong", {}, "Compared with this borrower's own norm"),
      h("ul", { class: "clean" }, d.own_norm_facts.map((s) => h("li", {}, s)))));
  if (d.early_signals && d.early_signals.length)
    why.append(h("div", { class: "box warn" }, h("strong", {}, "Early signals "), h("span", { class: "muted" }, "(card & app behaviour · rule-based in demo, learned in pilot)"),
      h("ul", { class: "clean" }, d.early_signals.map((s) => h("li", {}, s)))));
  out.push(why);

  // Step 2: WHAT to do (Model 2)
  const nb = d.next_best_action;
  if (nb && nb.best) {
    out.push(h("div", { class: "panel" },
      h("h3", {}, h("span", { class: "step" }, "2"), "What to do ", h("span", { class: "pill" }, "Model 2 · next best action")),
      h("p", { class: "muted" }, `Problem type: ${nb.problem_text}`),
      h("div", { class: "box best" }, h("strong", {}, nb.best.title),
        h("div", {}, `Prevents ≈ ${money(nb.best.expected_saved)} of expected loss · costs ${money(nb.best.cost)}${nb.best.minutes ? " · " + nb.best.minutes + " officer min" : ""}`),
        nb.note ? h("div", {}, nb.note) : null),
      h("details", {}, h("summary", {}, `Show all ${nb.options.length} allowed actions and why`),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, "Allowed action"), h("th", { class: "num" }, "Effect"), h("th", { class: "num" }, "Saves"), h("th", { class: "num" }, "Cost"), h("th", { class: "num" }, "Net value"))),
          h("tbody", {}, nb.options.map((o) => h("tr", { title: o.source },
            h("td", {}, o.title), h("td", { class: "num" }, `+${o.uplift_pp} pp`), h("td", { class: "num" }, money(o.expected_saved)),
            h("td", { class: "num" }, money(o.cost)), h("td", { class: "num" }, money(o.value))))))),
        h("p", { class: "muted" }, "Effect = extra chance to resolve within 30 days (published field experiments + named assumptions; learned in the pilot). Calling relatives or acquaintances is excluded (bank secrecy & personal data law): only the borrower and the contract's guarantor are contacted."))));
  }

  // Step 3: HOW to save the loan
  if (d.band !== "green") {
    const save = h("div", { class: "panel" }, h("h3", {}, h("span", { class: "step" }, "3"), "How to save the loan"));
    if (d.path_to_green)
      save.append(h("div", { class: `box ${d.path_to_green.possible ? "ok" : "bad"}` },
        h("strong", {}, "Path back to green: "), d.path_to_green.text, h("div", { class: "muted" }, d.path_to_green.note)));
    const rescue = d.actions.find((a) => a.code === "rescue_plan");
    if (rescue) {
      const box = h("div", { class: "box best" }, h("strong", {}, rescue.title), h("div", {}, rescue.details));
      if (rescue.plan && rescue.plan.feasible)
        box.append(h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, "Month"), h("th", { class: "num" }, "Expected income"), h("th", { class: "num" }, "Payment"), h("th", { class: "num" }, "Burden"))),
          h("tbody", {}, rescue.plan.table.map((r) => h("tr", {}, h("td", {}, r.month), h("td", { class: "num" }, fmt(r.expected_income)),
            h("td", { class: "num" }, fmt(r.payment)), h("td", { class: "num" }, r.burden_pct + "%")))))),
          h("p", { class: "muted" }, "Assumptions: payment ≤ 30% of income; income returns to its last-6-month level with the usual seasonality. Present value at the contract rate = outstanding, so the bank loses nothing."));
      save.append(box);
    }
    if (d.letter) save.append(h("details", {}, h("summary", {}, "Draft offer letter to the borrower (EN / RU / UZ)"),
      h("pre", { class: "letter" }, d.letter), h("p", { class: "muted" }, "Template-based, no invented legal references. Switch the language at the top.")));
    const others = d.actions.filter((a) => a.code !== "rescue_plan");
    save.append(h("details", {}, h("summary", {}, `Other options: action ladder (${others.length})`),
      others.map((a) => h("div", { class: "action" },
        h("div", {}, h("span", { class: `lvl ${a.level}` }, a.level), h("strong", {}, a.title), a.needs_committee ? h("span", { class: "muted" }, " · credit committee") : null),
        h("div", {}, a.details || "")))));
    out.push(save);
  }

  if (withDecision && d.id !== "JURY") out.push(decisionPanel(d));
  return out;
}

function decisionPanel(d) {
  const codes = [...new Set([...(d.next_best_action?.options || []).map((o) => o.action), ...d.actions.map((a) => a.code)])];
  const sel = h("select", {}, codes.map((c) => h("option", { value: c }, c)));
  const officer = h("input", { maxlength: "60", placeholder: "Officer name", value: d.assigned_officer || "" });
  const comment = h("input", { maxlength: "500", placeholder: "Comment (optional)" });
  const msg = h("div", { class: "muted" });
  const nbaCodes = (d.next_best_action?.options || []).map((o) => o.action);
  const outSel = h("select", {}, nbaCodes.map((c) => h("option", { value: c }, c)));
  const outMsg = h("div", { class: "muted" });
  const send = async (resolved) => {
    try {
      const r = await api("/api/outcome", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ borrower_id: d.id, action_code: outSel.value, resolved }) });
      outMsg.textContent = `Recorded. Model 2 now estimates P(resolve | ${PT[r.problem_type]}, ${outSel.value}) = ${pct(r.p_resolve_now, 1)} from ${r.n_local} local outcome(s).`;
    } catch (e) { outMsg.textContent = "Error: " + e.message; }
  };
  return h("div", { class: "panel" },
    h("h3", {}, "Officer decision → audit log"),
    h("div", { class: "grid" }, h("label", {}, "Action", sel), h("label", {}, "Officer", officer), h("label", {}, "Comment", comment)),
    h("button", { class: "btn", onclick: async () => {
      try {
        const r = await api("/api/decision", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ borrower_id: d.id, action_code: sel.value, officer: officer.value.trim(), comment: comment.value }) });
        msg.textContent = `Saved as audit record #${r.id} · hash ${r.hash.slice(0, 16)}…`;
      } catch (e) { msg.textContent = "Error: " + e.message; }
    } }, "Record decision"), msg,
    nbaCodes.length ? h("div", { style: "margin-top:12px" },
      h("h3", {}, "30 days later: record the outcome (teaches Model 2)"),
      h("div", { class: "row" }, h("label", {}, "Action taken", outSel),
        h("button", { class: "btn", onclick: () => send(true) }, "Resolved ✓"),
        h("button", { class: "btn bad", onclick: () => send(false) }, "Not resolved ✗")), outMsg) : null);
}

// ---------- Try it (jury input) ----------
const PRESETS = {
  dilnoza: { name: "Like Dilnoza", business_type: "tailoring", segment: "micro_business", outstanding: 41000000, rate: 22, term_months: 36, months_elapsed: 14, installment: 2290000, has_app: true, has_guarantor: true,
    rows: [[2290000, 2290000, 0, 9500000], [2290000, 2290000, 0, 8200000], [2290000, 2290000, 0, 5900000], [2290000, 1500000, 9, 4600000], [3080000, 1200000, 24, 3600000], [4170000, 920000, 35, 3300000]] },
  healthy: { name: "Healthy shop", business_type: "retail_shop", segment: "micro_business", outstanding: 30000000, rate: 20, term_months: 24, months_elapsed: 10, installment: 1900000, has_app: true, has_guarantor: false,
    rows: [[1900000, 1900000, 0, 7600000], [1900000, 1900000, 0, 7700000], [1900000, 1900000, 0, 7500000], [1900000, 1900000, 0, 7600000], [1900000, 1900000, 0, 7800000], [1900000, 1900000, 0, 7900000]] },
  silent: { name: "Silent borrower", business_type: "greenhouse", segment: "household", outstanding: 18000000, rate: 24, term_months: 24, months_elapsed: 9, installment: 1100000, has_app: false, has_guarantor: true,
    rows: [[1100000, 1100000, 0, 4800000], [1100000, 1100000, 0, 4400000], [1100000, 900000, 7, 3900000], [1300000, 600000, 22, 3000000], [1800000, 0, 52, 2100000], [2900000, 0, 82, 1800000]] },
};
const MONTH_LABELS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep"];
function fillPreset(name) {
  const p = PRESETS[name], f = $("tryForm");
  for (const k of ["name", "business_type", "segment", "outstanding", "rate", "term_months", "months_elapsed", "installment"]) f.elements[k].value = p[k];
  f.elements.has_app.checked = p.has_app; f.elements.has_guarantor.checked = p.has_guarantor;
  $("monthRows").replaceChildren(...p.rows.map((r, i) => h("tr", {},
    h("td", {}, MONTH_LABELS[i]),
    ...r.map((v, j) => h("td", {}, h("input", { type: "number", min: "0", max: j === 2 ? "365" : "10000000000", value: v, "data-col": j, "aria-label": ["due", "paid", "days late", "income"][j] }))))));
}
$("presets").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (b) fillPreset(b.dataset.preset); });
$("tryForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("tryError").textContent = "";
  const f = e.target, num = (k) => Number(f.elements[k].value);
  const rows = [...$("monthRows").querySelectorAll("tr")].map((tr) => [...tr.querySelectorAll("input")].map((i) => Number(i.value)));
  const body = {
    lang: state.lang, name: f.elements.name.value.trim() || "Jury borrower", business_type: f.elements.business_type.value,
    segment: f.elements.segment.value, annual_rate: num("rate") / 100, term_months: num("term_months"),
    months_elapsed: num("months_elapsed"), outstanding: num("outstanding"),
    installment: f.elements.installment.value ? num("installment") : null,
    history: rows.map((r) => ({ due: r[0], paid: r[1], days_late: r[2] })),
    turnover: rows.every((r) => r[3] > 0) ? rows.map((r) => r[3]) : null,
    has_app: f.elements.has_app.checked, has_guarantor: f.elements.has_guarantor.checked, prior_loans_repaid: 0,
  };
  try {
    const d = await api("/api/score", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("tryResult").replaceChildren(h("p", { class: "muted" }, `Scored live in ${d.latency_ms} ms · logged to the audit trail`), ...renderCard(d, false));
    $("tryResult").scrollIntoView({ behavior: "smooth" });
  } catch (err) { $("tryError").textContent = "Check the input: " + err.message; }
});

// ---------- Quality ----------
async function loadQuality() {
  const [mc, kn] = await Promise.all([api("/api/model-card"), api("/api/nba/knowledge")]);
  const m = mc.metrics, hd = m.hidden_defaulters, r2 = m.rule_vs_model.missed_2_months, r1 = m.rule_vs_model.missed_1_month;
  const stat = (v, l) => h("div", { class: "stat" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
  const tbl = (head, rows) => h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, head.map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, r.map((x, i) => h("td", { class: i ? "num" : "" }, x)))))));
  $("qualityBody").replaceChildren(
    h("div", { class: "panel" }, h("h2", {}, "Model 1: who will stop paying"),
      h("p", { class: "muted" }, `${m.data}. Untouched 20% hold-out (${fmt(m.n_test)} borrowers), evaluated once. Model ${m.model_version}.`),
      h("div", { class: "stat-grid" },
        stat(m.holdout_auc.toFixed(3), "ROC-AUC on the hold-out"),
        stat(pct(hd.share_of_defaulters_not_late_yet), "of next month's defaulters were still paying on time the month before: a 'missed payment' rule cannot see them"),
        stat(hd.top10_within_not_late_lift.toFixed(1) + "×", `more defaulters in our top-10% list among those not late yet (${pct(hd.top10_within_not_late_default_rate)} vs ${pct(hd.default_rate_not_late)} average)`),
        stat(pct(m.red.precision), `of borrowers we flag red really default (they are ${pct(m.red.flagged_share)} of the book)`),
        stat(m.latency_ms_per_score.toFixed(2) + " ms", "to score one borrower on a laptop CPU"),
        stat("≈0.3 UZS", "per score (assumption: $300/month server inside the bank, 400,000 loans scored daily)"))),
    h("div", { class: "panel" }, h("h3", {}, "Today's rule vs our model (same number of alerts)"),
      tbl(["Rule", "Alerts", "Rule precision", "Model precision", "Rule recall", "Model recall"], [
        ["Missed 2 months (what officers use)", fmt(r2.alerts), pct(r2.rule_precision), pct(r2.model_precision), pct(r2.rule_recall), pct(r2.model_recall)],
        ["Missed 1 month", fmt(r1.alerts), pct(r1.rule_precision), pct(r1.model_precision), pct(r1.rule_recall), pct(r1.model_recall)]]),
      h("p", { class: "muted" }, "A rule can only see people who are already late. The model also ranks the ones who are still paying on time.")),
    h("div", { class: "panel" }, h("h3", {}, "How early we see risk"),
      tbl(["Horizon", "ROC-AUC"], Object.entries(m.horizon_auc).map(([k, v]) => [k.replaceAll("_", " "), v.toFixed(3)])),
      h("p", { class: "muted" }, `CV AUC: LightGBM ${m.cv_auc_lightgbm.toFixed(3)} vs logistic regression baseline ${m.cv_auc_logreg.toFixed(3)}. Reference with absolute amounts (not transferable to MKBANK loans): ${m.reference_auc_with_absolute_columns.toFixed(3)}.`)),
    h("div", { class: "panel" }, h("h3", {}, "Fairness check (the model never sees sex or age)"),
      tbl(["Group", "n", "AUC", "Flagged red", "Default rate"], Object.entries(m.fairness).map(([g, v]) => [g.replaceAll("_", " "), fmt(v.n), v.auc.toFixed(3), pct(v.red_share, 1), pct(v.default_rate, 1)]))),
    h("div", { class: "panel" }, h("h2", {}, "Model 2: what we know about actions"),
      h("p", { class: "muted" }, "P(resolved within 30 days | problem type, action). Priors from published field experiments and named assumptions; n_local counts real outcomes recorded here. In the pilot, these numbers are learned from MKBANK's own outcomes with a 10% control group."),
      tbl(["Problem · action", "P(resolve)", "n local", "Source"], kn.rows.map((r) => [`${PT[r.problem_type]} · ${r.action.replace("_", " ")}`, pct(r.p_resolve, 0), fmt(r.n_local), r.source])),
      h("p", { class: "muted" }, `Loss given default ${pct(kn.lgd)} (Basel II foundation IRB, assumption). Costs: ${kn.cost_source}. Excluded: ${kn.excluded}`)),
    h("div", { class: "panel" }, h("h3", {}, "Known limitations (honest list)"),
      h("ul", { class: "clean" },
        h("li", {}, "Trained on credit-card borrowers in Taiwan (2005), not MKBANK micro-loans: only transferable own-norm behaviour features are used, and the pilot retrains inside the bank."),
        h("li", {}, "Sudden shocks (illness, fire) without earlier signals cannot be predicted."),
        h("li", {}, "New loans with less than 6 months of history are not scored."),
        h("li", {}, "Card and app early signals are rules in the demo (no public data); they become model features in the pilot."),
        h("li", {}, "Action effects outside the cited experiments are assumptions until the pilot measures them."),
        h("li", {}, "Demo portfolio is synthetic (scripts/make_demo_portfolio.py, seed 42); no real customer data is used."))));
}

// ---------- Audit ----------
async function loadAudit() {
  const rows = await api("/api/audit?limit=50");
  $("auditList").replaceChildren(...(rows.length ? rows.map((r) => h("div", { class: "panel", style: "margin:0" },
    h("div", {}, h("strong", {}, `#${r.id} ${r.event}`), ` · ${r.borrower_id} · by ${r.actor} · ${r.ts_utc}`),
    h("div", { class: "hash" }, `hash ${r.hash.slice(0, 32)}… ← prev ${r.prev_hash.slice(0, 16)}…`))) : [h("p", { class: "muted" }, "No records yet. Score a borrower or record a decision.")]));
}
$("verifyBtn").addEventListener("click", async () => {
  const d = await api("/api/audit/verify");
  $("verifyOut").textContent = d.ok ? `✅ Chain valid (${d.n} records)` : `❌ Chain broken at record #${d.first_bad_id}`;
  $("verifyOut").style.color = d.ok ? "var(--green)" : "var(--red)";
});

function showErr(e) { console.error(e); alert("Error: " + e.message); }

fillPreset("dilnoza");
loadToday().then(loadPlan).catch(showErr);
