// Вспомогательная функция для безопасного создания элементов (XSS-защита)
function el(tag, text = "", className = "") {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  return element;
}

document.addEventListener("DOMContentLoaded", () => {
  let currentLang = "en";
  let currentSort = "risk";
  let myChart = null;

  // Переключение вкладок
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.onclick = () => {
      document
        .querySelectorAll(".tab-btn")
        .forEach((b) => b.classList.remove("active"));
      document
        .querySelectorAll(".tab-pane")
        .forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.target).classList.add("active");
      if (btn.dataset.target === "tab-quality") loadQuality();
      if (btn.dataset.target === "tab-audit") loadAudit();
    };
  });

  document.getElementById("langSelect").addEventListener("change", (e) => {
    currentLang = e.target.value;
    loadToday();
  });

  document.getElementById("sortRiskBtn").onclick = () => {
    currentSort = "risk";
    loadToday();
  };
  document.getElementById("sortMoneyBtn").onclick = () => {
    currentSort = "money";
    loadToday();
  };

  // --- 1. Вкладка Today ---
  async function loadToday() {
    const res = await fetch(
      `/api/portfolio?lang=${currentLang}&sort=${currentSort}`
    );
    const data = await res.json();

    const summary = document.getElementById("summaryCards");
    summary.innerHTML = ""; // Очистка родителя безопасна, если мы создаем узлы вручную

    const cRed = el("div", "", "stat");
    cRed.appendChild(el("div", "🔴 RED"));
    cRed.appendChild(el("span", data.summary.red));
    const cYel = el("div", "", "stat");
    cYel.appendChild(el("div", "🟡 YEL"));
    cYel.appendChild(el("span", data.summary.yellow));
    const cGrn = el("div", "", "stat");
    cGrn.appendChild(el("div", "🟢 GRN"));
    cGrn.appendChild(el("span", data.summary.green));
    summary.append(cRed, cYel, cGrn);

    const list = document.getElementById("portfolioList");
    list.innerHTML = "";

    data.borrowers.forEach((b) => {
      const card = el("div", "", `card ${b.band}`);
      const title = el("h3", `${b.name} (${b.id})`);
      const info = el(
        "p",
        `Prob: ${(b.prob * 100).toFixed(
          1
        )}% | Risk: ${b.money_at_risk.toLocaleString()} UZS`
      );
      const reason = el("small", b.top_reason);
      card.append(title, info, reason);
      card.onclick = () => loadBorrower(b.id);
      list.appendChild(card);
    });
  }

  // --- 2. Вкладка Borrower ---
  async function loadBorrower(id) {
    document.querySelector('[data-target="tab-borrower"]').click();
    const content = document.getElementById("borrowerContent");
    content.innerHTML = "Loading...";

    const res = await fetch(`/api/borrower/${id}?lang=${currentLang}`);
    const data = await res.json();
    content.innerHTML = "";

    content.appendChild(el("h2", `${data.name} (${data.id})`));
    content.appendChild(
      el("p", `Type: ${data.business_type} | Region: ${data.region}`)
    );
    content.appendChild(
      el(
        "h3",
        `Risk Band: ${data.band.toUpperCase()} (${(data.prob * 100).toFixed(
          1
        )}%)`
      )
    );

    // Рисуем график
    const canvas = document.createElement("canvas");
    content.appendChild(canvas);
    if (myChart) myChart.destroy();
    myChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: ["M1", "M2", "M3", "M4", "M5", "M6"],
        datasets: [
          {
            label: "Due",
            data: data.history.slice(-6).map((h) => h.due),
            backgroundColor: "#ccc",
          },
          {
            label: "Paid",
            data: data.history.slice(-6).map((h) => h.paid),
            backgroundColor: "#007bff",
          },
        ],
      },
    });

    content.appendChild(el("h3", "Top Risk Factors"));
    const ul = document.createElement("ul");
    data.reasons.forEach((r) => ul.appendChild(el("li", r.text)));
    content.appendChild(ul);

    content.appendChild(el("h3", "Recommended Actions"));
    data.actions.forEach((a) => {
      const actCard = el("div", "", "card");
      actCard.appendChild(el("h4", `[${a.code}] ${a.title}`));
      actCard.appendChild(el("p", a.details));
      content.appendChild(actCard);
    });

    // Форма решения
    content.appendChild(el("h3", "Record Decision"));
    const officerInput = el("input");
    officerInput.placeholder = "Officer Name";
    const actionInput = el("input");
    actionInput.placeholder = "Action Code (e.g. A1)";
    const commentInput = el("input");
    commentInput.placeholder = "Comment";
    const saveBtn = el("button", "Save Decision", "btn");

    saveBtn.onclick = async () => {
      await fetch("/api/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          borrower_id: data.id,
          action_code: actionInput.value,
          officer: officerInput.value,
          comment: commentInput.value,
        }),
      });
      alert("Decision saved to Audit Log!");
    };
    content.append(officerInput, actionInput, commentInput, saveBtn);
  }

  // --- 3. Вкладка Check (Jury) ---
  const demoJson = {
    lang: "en",
    business_type: "tailoring",
    loan_amount: 60000000,
    annual_rate: 0.22,
    term_months: 36,
    months_elapsed: 14,
    outstanding: 41000000,
    history: [
      { due: 2290000, paid: 2290000, days_late: 0 },
      { due: 2290000, paid: 2290000, days_late: 0 },
      { due: 2290000, paid: 2290000, days_late: 0 },
      { due: 2290000, paid: 2290000, days_late: 0 },
      { due: 2290000, paid: 1500000, days_late: 10 },
      { due: 3080000, paid: 1000000, days_late: 45 },
    ],
    turnover: [9100000, 9100000, 8500000, 8500000, 5000000, 4000000],
  };
  document.getElementById("checkJson").value = JSON.stringify(
    demoJson,
    null,
    2
  );

  document.getElementById("scoreBtn").onclick = async () => {
    const resDiv = document.getElementById("checkResult");
    try {
      const bodyData = JSON.parse(document.getElementById("checkJson").value);
      const res = await fetch("/api/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyData),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(JSON.stringify(data));

      resDiv.innerHTML = "";
      resDiv.appendChild(
        el(
          "h3",
          `Result: ${data.band.toUpperCase()} (${(
            data.probability * 100
          ).toFixed(1)}%)`
        )
      );
      resDiv.appendChild(el("p", `Latency: ${data.latency_ms} ms`));
      data.reasons.forEach((r) => resDiv.appendChild(el("p", `• ${r.text}`)));
    } catch (e) {
      resDiv.innerHTML = "";
      resDiv.appendChild(el("p", `Error: ${e.message}`, "error"));
    }
  };

  // --- 4. & 5. Вкладки Quality и Audit ---
  async function loadQuality() {
    const res = await fetch("/api/model-card");
    const data = await res.json();
    const content = document.getElementById("qualityContent");
    content.innerHTML = "";
    content.appendChild(
      el("pre", JSON.stringify(data.metrics, null, 2), "card")
    );
  }

  async function loadAudit() {
    const res = await fetch("/api/audit");
    const data = await res.json();
    const list = document.getElementById("auditList");
    list.innerHTML = "";
    data.forEach((log) => {
      const card = el("div", "", "card");
      card.appendChild(el("p", `[${log.ts_utc}] ${log.event} by ${log.actor}`));
      card.appendChild(el("small", `Hash: ${log.hash.substring(0, 16)}...`));
      list.appendChild(card);
    });
  }

  document.getElementById("verifyAuditBtn").onclick = async () => {
    const res = await fetch("/api/audit/verify");
    const data = await res.json();
    const div = document.getElementById("verifyResult");
    div.textContent = data.ok
      ? `✅ Chain is valid! (${data.n} records)`
      : `❌ Chain broken at ID: ${data.first_bad_id}`;
    div.style.color = data.ok ? "green" : "red";
  };

  loadToday(); // Загрузка при старте
});
