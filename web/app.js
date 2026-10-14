/**
 * Price Alert Tool - Clean Light Theme Dashboard Logic
 */

(function () {
  const state = {
    alerts: [],
    cliOutput: "",
    instruments: {},
    rules: [],
    activeTicker: null,
    hoverIndex: null,
  };

  const canvas = document.getElementById("priceChart");
  const ctx = canvas.getContext("2d");
  const tooltip = document.getElementById("chartTooltip");

  // DOM Elements
  const tickerTabs = document.getElementById("instrument-tabs");
  const alertsTbody = document.getElementById("alerts-tbody");
  const cliOutputText = document.getElementById("cli-output-text");
  const rulesList = document.getElementById("rules-card-list");

  const tabCli = document.getElementById("tab-cli");
  const tabTable = document.getElementById("tab-table");
  const viewCli = document.getElementById("view-cli-container");
  const viewTable = document.getElementById("view-table-container");

  const btnCopyCli = document.getElementById("btn-copy-cli");
  const btnLoadSample = document.getElementById("btn-load-sample");
  const btnRunEvaluation = document.getElementById("btn-run-evaluation");
  const inputCsv = document.getElementById("input-csv");
  const inputJson = document.getElementById("input-json");
  const inputError = document.getElementById("input-error");

  // Load initial sample data
  async function loadInitialData() {
    try {
      const res = await fetch("/api/default");
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      // Populate textareas with current sample CSV & JSON
      populateInputFields(data);
      applyPayload(data);
    } catch (err) {
      console.error("Failed to load sample data:", err);
    }
  }

  function populateInputFields(data) {
    if (data.instruments) {
      const rows = ["date,instrument,close"];
      Object.keys(data.instruments).forEach((inst) => {
        const item = data.instruments[inst];
        item.dates.forEach((date, i) => {
          rows.push(`${date},${inst},${item.closes[i].toFixed(2)}`);
        });
      });
      inputCsv.value = rows.join("\n");
    }

    if (data.rules) {
      inputJson.value = JSON.stringify(data.rules, null, 2);
    }
  }

  function applyPayload(data) {
    state.alerts = data.alerts || [];
    state.cliOutput = data.cli_output || "";
    state.instruments = data.instruments || {};
    state.rules = data.rules || [];

    const tickers = Object.keys(state.instruments);
    if (!state.activeTicker || !state.instruments[state.activeTicker]) {
      state.activeTicker = tickers[0] || null;
    }

    renderTickerTabs();
    renderOutput();
    renderRules();
    drawChart();
  }

  function renderTickerTabs() {
    tickerTabs.innerHTML = "";
    const tickers = Object.keys(state.instruments);

    tickers.forEach((ticker) => {
      const btn = document.createElement("button");
      btn.id = `ticker-${ticker}`;
      btn.className = `ticker-tab-btn ${ticker === state.activeTicker ? "active" : ""}`;
      btn.textContent = ticker;
      btn.addEventListener("click", () => {
        state.activeTicker = ticker;
        renderTickerTabs();
        drawChart();
      });
      tickerTabs.appendChild(btn);
    });
  }

  function renderOutput() {
    // CLI Plaintext
    cliOutputText.textContent = state.cliOutput || "No alerts triggered.";

    // Table rows
    alertsTbody.innerHTML = "";
    if (state.alerts.length === 0) {
      alertsTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--text-light); padding: 24px;">No alerts triggered.</td></tr>`;
      return;
    }

    state.alerts.forEach((alert) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${alert.date}</td>
        <td><strong>${alert.rule_id}</strong></td>
        <td>${alert.instrument}</td>
        <td>${alert.rule_type}</td>
        <td>${alert.details}</td>
      `;
      alertsTbody.appendChild(tr);
    });
  }

  function renderRules() {
    rulesList.innerHTML = "";
    state.rules.forEach((r) => {
      const pill = document.createElement("div");
      pill.className = "rule-pill";
      let desc = "";
      if (r.type === "level") {
        desc = `level ${r.direction} ${r.level}`;
      } else if (r.type === "ma_cross") {
        desc = `SMA(${r.short}) cross ${r.direction} SMA(${r.long})`;
      }
      pill.innerHTML = `<strong>${r.id}</strong>: ${r.instrument} ${desc}`;
      rulesList.appendChild(pill);
    });
  }

  // View Tab Switcher (CLI vs Table)
  tabCli.addEventListener("click", () => {
    tabCli.classList.add("active");
    tabTable.classList.remove("active");
    viewCli.classList.remove("hidden");
    viewTable.classList.add("hidden");
  });

  tabTable.addEventListener("click", () => {
    tabTable.classList.add("active");
    tabCli.classList.remove("active");
    viewTable.classList.remove("hidden");
    viewCli.classList.add("hidden");
  });

  // Copy CLI lines
  btnCopyCli.addEventListener("click", () => {
    if (!state.cliOutput) return;
    navigator.clipboard.writeText(state.cliOutput).then(() => {
      btnCopyCli.textContent = "Copied";
      setTimeout(() => (btnCopyCli.textContent = "Copy"), 1500);
    });
  });

  // Reload default sample data
  btnLoadSample.addEventListener("click", () => {
    loadInitialData();
  });

  // Run Custom Evaluation
  btnRunEvaluation.addEventListener("click", async () => {
    const csvText = inputCsv.value.trim();
    const jsonText = inputJson.value.trim();

    if (!csvText || !jsonText) {
      inputError.textContent = "Please provide both CSV prices and JSON rules.";
      inputError.classList.remove("hidden");
      return;
    }

    try {
      const parsedJson = JSON.parse(jsonText);
      inputError.classList.add("hidden");

      const res = await fetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prices_csv: csvText,
          rules_json: parsedJson,
        }),
      });

      const data = await res.json();
      if (!data.success) {
        throw new Error(data.error || "Evaluation failed");
      }

      applyPayload(data);
    } catch (err) {
      inputError.textContent = err.message;
      inputError.classList.remove("hidden");
    }
  });

  // High-DPI Canvas Rendering (Light Theme)
  function setupDpi() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    return { width: rect.width, height: rect.height };
  }

  function drawChart() {
    if (!state.activeTicker || !state.instruments[state.activeTicker]) return;

    const { width, height } = setupDpi();
    const data = state.instruments[state.activeTicker];
    const dates = data.dates;
    const closes = data.closes;
    const smas = data.smas || {};
    const rules = data.rules || [];

    if (!dates || dates.length === 0) return;

    let vals = [...closes];
    Object.values(smas).forEach((arr) => {
      arr.forEach((v) => {
        if (v !== null) vals.push(v);
      });
    });
    rules.forEach((r) => {
      if (r.type === "level") vals.push(r.level);
    });

    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const pad = (max - min) * 0.1 || 5;
    const yMin = min - pad;
    const yMax = max + pad;

    const marginLeft = 60;
    const marginRight = 24;
    const marginTop = 20;
    const marginBottom = 34;
    const plotW = width - marginLeft - marginRight;
    const plotH = height - marginTop - marginBottom;

    function getX(i) {
      if (dates.length <= 1) return marginLeft + plotW / 2;
      return marginLeft + (i / (dates.length - 1)) * plotW;
    }

    function getY(v) {
      return marginTop + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    }

    // Clear background
    ctx.clearRect(0, 0, width, height);

    // Subtle horizontal grid lines
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#64748b";
    ctx.font = "11px 'SF Mono', Consolas, monospace";
    ctx.textAlign = "right";

    const steps = 4;
    for (let s = 0; s <= steps; s++) {
      const v = yMin + (s / steps) * (yMax - yMin);
      const y = getY(v);
      ctx.beginPath();
      ctx.moveTo(marginLeft, y);
      ctx.lineTo(width - marginRight, y);
      ctx.stroke();
      ctx.fillText(v.toFixed(1), marginLeft - 8, y + 4);
    }

    // X Axis Labels
    ctx.textAlign = "center";
    const xStep = Math.max(1, Math.floor(dates.length / 6));
    for (let i = 0; i < dates.length; i += xStep) {
      const x = getX(i);
      ctx.fillText(dates[i].slice(5), x, height - marginBottom + 18);
    }

    // Level Threshold
    rules.forEach((r) => {
      if (r.type === "level") {
        const ly = getY(r.level);
        ctx.strokeStyle = "#dc2626";
        ctx.lineWidth = 1.4;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(marginLeft, ly);
        ctx.lineTo(width - marginRight, ly);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = "#dc2626";
        ctx.textAlign = "left";
        ctx.fillText(`Level ${r.level}`, width - marginRight - 65, ly - 6);
      }
    });

    // Helper for series
    function plotLine(arr, color, width) {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < arr.length; i++) {
        const v = arr[i];
        if (v === null || v === undefined) {
          started = false;
          continue;
        }
        const x = getX(i);
        const y = getY(v);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    // Plot SMAs
    const smaKeys = Object.keys(smas);
    if (smaKeys.length > 0) {
      plotLine(smas[smaKeys[0]], "#d97706", 1.8); // Short MA
    }
    if (smaKeys.length > 1) {
      plotLine(smas[smaKeys[1]], "#7c3aed", 1.8); // Long MA
    }

    // Plot Close Price
    plotLine(closes, "#2563eb", 2);

    // Alert Markers
    const alertsForTicker = state.alerts.filter((a) => a.instrument === state.activeTicker);
    alertsForTicker.forEach((a) => {
      const idx = dates.indexOf(a.date);
      if (idx !== -1) {
        const ax = getX(idx);
        const ay = getY(closes[idx]);

        // Clean vertical guide line
        ctx.strokeStyle = "rgba(22, 163, 74, 0.4)";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(ax, marginTop);
        ctx.lineTo(ax, marginTop + plotH);
        ctx.stroke();

        // Marker Dot
        ctx.fillStyle = "#16a34a";
        ctx.beginPath();
        ctx.arc(ax, ay, 5, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    });

    // Hover Crosshair
    if (state.hoverIndex !== null && state.hoverIndex >= 0 && state.hoverIndex < dates.length) {
      const hx = getX(state.hoverIndex);
      const hy = getY(closes[state.hoverIndex]);

      ctx.strokeStyle = "rgba(100, 116, 139, 0.4)";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);

      ctx.beginPath();
      ctx.moveTo(hx, marginTop);
      ctx.lineTo(hx, marginTop + plotH);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = "#0f172a";
      ctx.beginPath();
      ctx.arc(hx, hy, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Hover Tooltip
  canvas.addEventListener("mousemove", (e) => {
    if (!state.activeTicker) return;
    const data = state.instruments[state.activeTicker];
    if (!data || !data.dates.length) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const marginLeft = 60;
    const marginRight = 24;
    const plotW = rect.width - marginLeft - marginRight;

    if (mouseX < marginLeft || mouseX > rect.width - marginRight) {
      tooltip.classList.add("hidden");
      state.hoverIndex = null;
      drawChart();
      return;
    }

    const ratio = (mouseX - marginLeft) / plotW;
    const idx = Math.min(
      data.dates.length - 1,
      Math.max(0, Math.round(ratio * (data.dates.length - 1)))
    );

    state.hoverIndex = idx;
    drawChart();

    const date = data.dates[idx];
    const close = data.closes[idx];
    const matches = state.alerts.filter(
      (a) => a.instrument === state.activeTicker && a.date === date
    );

    let html = `<div><strong>${date}</strong>: ${close.toFixed(2)}</div>`;
    Object.keys(data.smas || {}).forEach((k) => {
      const val = data.smas[k][idx];
      if (val !== null) {
        html += `<div style="color:var(--text-muted); font-size:10px;">${k.toUpperCase()}: ${val.toFixed(2)}</div>`;
      }
    });
    if (matches.length > 0) {
      matches.forEach((a) => {
        html += `<div style="color:#16a34a; margin-top:3px; font-weight:600;">• ${a.rule_id} ${a.details}</div>`;
      });
    }

    tooltip.innerHTML = html;
    tooltip.classList.remove("hidden");

    let tipX = mouseX + 14;
    if (tipX + 170 > rect.width) tipX = mouseX - 180;
    tooltip.style.left = `${tipX}px`;
    tooltip.style.top = `${Math.min(e.clientY - rect.top, rect.height - 75)}px`;
  });

  canvas.addEventListener("mouseleave", () => {
    tooltip.classList.add("hidden");
    state.hoverIndex = null;
    drawChart();
  });

  window.addEventListener("resize", drawChart);

  // Initial load
  loadInitialData();
})();
