const state = {
  data: null,
  filtered: [],
  filters: { yearStart: 0, yearEnd: 0, event: "All", vessel: "All", severity: "All" },
  tab: "overview",
  evidenceTheme: "All",
  selectedEvidence: null,
  selectedPattern: null,
  map: null,
  mapLayer: null,
};

const palette = {
  navy: "#123b47",
  teal: "#147d80",
  tealLight: "#6db5ad",
  coral: "#e56f4a",
  gold: "#d6a84b",
  red: "#b7433d",
  grey: "#aeb8b8",
  line: "#d9d8cf",
};

const themes = {
  All: [],
  "Human factors": ["fatigue", "lookout", "communication", "human", "crew", "passenger", "fell", "fall"],
  Navigation: ["collision", "ground", "navigation", "course", "bridge", "pilot", "contact"],
  Equipment: ["equipment", "machinery", "engine", "failure", "line", "mooring", "steering"],
  Fire: ["fire", "explosion", "smoke", "burn"],
};

const numberFormat = new Intl.NumberFormat("en-GB");
const pct = (value) => `${Math.round(value * 100)}%`;
const $ = (id) => document.getElementById(id);
const esc = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));

function countBy(records, field) {
  return records.reduce((acc, row) => {
    const key = row[field] || "Not recorded";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function topEntries(counter, limit = 7) {
  return Object.entries(counter).sort((a, b) => b[1] - a[1]).slice(0, limit);
}

function serious(record) {
  return record.severity === "Serious" || record.severity === "Very serious";
}

function populateSelect(element, values) {
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    element.appendChild(option);
  });
}

function setupFilters() {
  const records = state.data.records;
  const years = records.map((row) => row.year).filter(Boolean);
  state.filters.yearStart = Math.min(...years);
  state.filters.yearEnd = Math.max(...years);
  [$("yearStart"), $("yearEnd")].forEach((input) => {
    input.min = state.filters.yearStart;
    input.max = state.filters.yearEnd;
  });
  $("yearStart").value = state.filters.yearStart;
  $("yearEnd").value = state.filters.yearEnd;
  $("yearStartLabel").textContent = state.filters.yearStart;
  $("yearEndLabel").textContent = state.filters.yearEnd;

  populateSelect($("eventFilter"), Object.keys(countBy(records, "event")).sort());
  populateSelect($("vesselFilter"), Object.keys(countBy(records, "vessel_category")).sort());
  populateSelect($("severityFilter"), Object.keys(countBy(records, "severity")).sort());

  $("yearStart").addEventListener("input", () => {
    const start = Math.min(Number($("yearStart").value), Number($("yearEnd").value));
    state.filters.yearStart = start;
    $("yearStart").value = start;
    $("yearStartLabel").textContent = start;
    applyFilters();
  });
  $("yearEnd").addEventListener("input", () => {
    const end = Math.max(Number($("yearEnd").value), Number($("yearStart").value));
    state.filters.yearEnd = end;
    $("yearEnd").value = end;
    $("yearEndLabel").textContent = end;
    applyFilters();
  });
  [["eventFilter", "event"], ["vesselFilter", "vessel"], ["severityFilter", "severity"]].forEach(([id, key]) => {
    $(id).addEventListener("change", (event) => {
      state.filters[key] = event.target.value;
      applyFilters();
    });
  });
  $("resetFilters").addEventListener("click", resetFilters);
}

function resetFilters() {
  const { year_min, year_max } = state.data.meta;
  state.filters = { yearStart: year_min, yearEnd: year_max, event: "All", vessel: "All", severity: "All" };
  $("yearStart").value = year_min;
  $("yearEnd").value = year_max;
  $("yearStartLabel").textContent = year_min;
  $("yearEndLabel").textContent = year_max;
  $("eventFilter").value = "All";
  $("vesselFilter").value = "All";
  $("severityFilter").value = "All";
  state.selectedPattern = null;
  applyFilters();
}

function applyFilters() {
  const f = state.filters;
  state.filtered = state.data.records.filter((row) =>
    row.year >= f.yearStart && row.year <= f.yearEnd &&
    (f.event === "All" || row.event === f.event) &&
    (f.vessel === "All" || row.vessel_category === f.vessel) &&
    (f.severity === "All" || row.severity === f.severity)
  );
  $("scopeCount").textContent = numberFormat.format(state.filtered.length);
  renderOverview();
  renderPatterns();
  renderEvidence();
}

function svgWrap(content, viewBox = "0 0 700 260") {
  return `<svg viewBox="${viewBox}" role="img" aria-label="Data visualization" preserveAspectRatio="none">${content}</svg>`;
}

function renderLineChart(element, labels, values) {
  const width = 700, height = 260, left = 48, right = 18, top = 18, bottom = 34;
  const chartW = width - left - right, chartH = height - top - bottom;
  const max = Math.max(...values, 1);
  const x = (index) => left + (labels.length === 1 ? chartW / 2 : index * chartW / (labels.length - 1));
  const y = (value) => top + chartH - value / max * chartH;
  const points = values.map((value, index) => `${x(index)},${y(value)}`);
  const path = `M${points.join(" L")}`;
  const area = `${path} L${x(values.length - 1)},${top + chartH} L${x(0)},${top + chartH} Z`;
  const grid = [0, .25, .5, .75, 1].map((ratio) => {
    const gy = top + chartH - ratio * chartH;
    return `<line class="grid-line" x1="${left}" y1="${gy}" x2="${width - right}" y2="${gy}"/><text x="${left - 8}" y="${gy + 3}" text-anchor="end">${numberFormat.format(Math.round(max * ratio))}</text>`;
  }).join("");
  const labelsSvg = labels.map((label, index) => `<text x="${x(index)}" y="${height - 9}" text-anchor="middle">${label}</text>`).join("");
  const dots = values.map((value, index) => `<circle cx="${x(index)}" cy="${y(value)}" r="4" fill="${palette.coral}" stroke="#fff" stroke-width="2"><title>${labels[index]}: ${numberFormat.format(value)}</title></circle>`).join("");
  element.innerHTML = svgWrap(`${grid}<path class="line-area" d="${area}"/><path class="line-path" d="${path}"/>${dots}${labelsSvg}`, `0 0 ${width} ${height}`);
}

function renderHorizontalBars(element, entries) {
  const width = 700, height = 260, left = 190, right = 48, top = 8, rowH = 34;
  const max = Math.max(...entries.map(([, value]) => value), 1);
  const content = entries.map(([label, value], index) => {
    const y = top + index * rowH;
    const barW = value / max * (width - left - right);
    return `<text x="${left - 10}" y="${y + 18}" text-anchor="end">${esc(label.length > 28 ? label.slice(0, 27) + "…" : label)}</text><rect x="${left}" y="${y + 5}" width="${barW}" height="17" rx="2" fill="${index === entries.length - 1 ? palette.coral : "#8bb8b2"}"><title>${esc(label)}: ${numberFormat.format(value)}</title></rect><text class="chart-value" x="${left + barW + 7}" y="${y + 18}">${numberFormat.format(value)}</text>`;
  }).join("");
  element.innerHTML = svgWrap(content, `0 0 ${width} ${height}`);
}

function renderDonut(element, entries, colorMap) {
  const total = entries.reduce((sum, [, value]) => sum + value, 0) || 1;
  let offset = 0;
  const circumference = 2 * Math.PI * 70;
  const circles = entries.map(([label, value]) => {
    const length = value / total * circumference;
    const circle = `<circle cx="120" cy="110" r="70" fill="none" stroke="${colorMap[label] || palette.grey}" stroke-width="28" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 120 110)"><title>${esc(label)}: ${numberFormat.format(value)}</title></circle>`;
    offset += length;
    return circle;
  }).join("");
  element.innerHTML = svgWrap(`${circles}<circle cx="120" cy="110" r="49" fill="#fbfaf6"/><text x="120" y="105" text-anchor="middle" style="font-family:Georgia;font-size:23px;fill:#142a33">${numberFormat.format(total)}</text><text x="120" y="123" text-anchor="middle">reported</text>`, "0 0 240 220");
}

function renderGroupedBars(element, rows) {
  const width = 760, height = 250, left = 50, right = 20, top = 20, bottom = 58;
  const chartH = height - top - bottom, chartW = width - left - right;
  const max = Math.max(...rows.flatMap((row) => [row.injuries, row.fatalities]), 1);
  const groupW = chartW / rows.length, barW = Math.min(24, groupW * .25);
  const grid = [0, .25, .5, .75, 1].map((ratio) => { const gy = top + chartH - ratio * chartH; return `<line class="grid-line" x1="${left}" y1="${gy}" x2="${width - right}" y2="${gy}"/><text x="${left - 7}" y="${gy + 3}" text-anchor="end">${Math.round(max * ratio)}</text>`; }).join("");
  const bars = rows.map((row, index) => {
    const center = left + groupW * index + groupW / 2;
    const injuryH = row.injuries / max * chartH, fatalH = row.fatalities / max * chartH;
    const short = row.category.length > 16 ? row.category.slice(0, 15) + "…" : row.category;
    return `<rect x="${center - barW - 2}" y="${top + chartH - injuryH}" width="${barW}" height="${injuryH}" fill="${palette.gold}"><title>Injuries: ${row.injuries}</title></rect><rect x="${center + 2}" y="${top + chartH - fatalH}" width="${barW}" height="${fatalH}" fill="${palette.red}"><title>Fatalities: ${row.fatalities}</title></rect><text x="${center}" y="${height - 32}" text-anchor="middle">${esc(short)}</text>`;
  }).join("");
  element.innerHTML = svgWrap(`${grid}${bars}<rect x="${width - 155}" y="4" width="8" height="8" fill="${palette.gold}"/><text x="${width - 142}" y="12">Injuries</text><rect x="${width - 80}" y="4" width="8" height="8" fill="${palette.red}"/><text x="${width - 67}" y="12">Fatalities</text>`, `0 0 ${width} ${height}`);
}

function renderMissingBars(element, rows) {
  const width = 700, height = 250, left = 150, right = 45, top = 8, rowH = 36;
  const content = rows.map((row, index) => {
    const y = top + index * rowH, barW = row.rate / 100 * (width - left - right);
    return `<text x="${left - 10}" y="${y + 19}" text-anchor="end">${esc(row.field)}</text><rect x="${left}" y="${y + 5}" width="${width - left - right}" height="18" fill="#e4e6e0"/><rect x="${left}" y="${y + 5}" width="${barW}" height="18" fill="${row.rate > 50 ? palette.coral : palette.tealLight}"/><text class="chart-value" x="${width - 4}" y="${y + 19}" text-anchor="end">${row.rate.toFixed(1)}%</text>`;
  }).join("");
  element.innerHTML = svgWrap(content, `0 0 ${width} ${height}`);
}

function renderOverview() {
  const records = state.filtered;
  $("metricOccurrences").textContent = numberFormat.format(records.length);
  $("metricVessels").textContent = numberFormat.format(records.reduce((sum, row) => sum + row.vessel_count, 0));
  $("metricInjuries").textContent = numberFormat.format(records.reduce((sum, row) => sum + row.injuries, 0));
  $("metricFatalities").textContent = numberFormat.format(records.reduce((sum, row) => sum + row.fatalities, 0));
  $("metricOccurrencesNote").textContent = `${state.filters.yearStart}–${state.filters.yearEnd}${state.filters.yearEnd === state.data.meta.year_max ? ", latest year partial" : ""}`;

  const byYear = countBy(records, "year");
  const years = [];
  for (let year = state.filters.yearStart; year <= state.filters.yearEnd; year += 1) years.push(year);
  renderLineChart($("trendChart"), years, years.map((year) => byYear[year] || 0));

  const events = topEntries(countBy(records, "event"), 7).reverse();
  renderHorizontalBars($("eventChart"), events);

  const severityColors = { "Marine incident": palette.teal, "Less serious": palette.tealLight, "Marine casualty": palette.gold, Serious: palette.coral, "Very serious": palette.red, "Not recorded": palette.grey };
  const severityEntries = Object.entries(countBy(records, "severity")).sort((a, b) => b[1] - a[1]);
  renderDonut($("severityChart"), severityEntries, severityColors);
  $("severityLegend").innerHTML = severityEntries.map(([label, value]) => `<div><i style="background:${severityColors[label] || palette.grey}"></i><span>${esc(label)}</span><strong>${pct(value / Math.max(records.length, 1))}</strong></div>`).join("");
  renderMap();
}

function initializeMap() {
  state.map = L.map("map", { preferCanvas: true, zoomControl: false }).setView([54.4, -3.4], 4);
  L.control.zoom({ position: "bottomright" }).addTo(state.map);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 17, attribution: "© OpenStreetMap" }).addTo(state.map);
  state.mapLayer = L.layerGroup().addTo(state.map);
}

function markerColor(record) {
  if (serious(record)) return palette.red;
  if (record.severity.includes("casualty") || record.severity === "Less serious") return palette.gold;
  return palette.teal;
}

function renderMap() {
  if (!state.map) initializeMap();
  state.mapLayer.clearLayers();
  const valid = state.filtered.filter((row) => row.lat !== null && row.lon !== null);
  const step = Math.max(1, Math.ceil(valid.length / 1700));
  const plotted = valid.filter((_, index) => index % step === 0);
  plotted.forEach((row) => {
    L.circleMarker([row.lat, row.lon], { radius: 3.5, color: markerColor(row), fillColor: markerColor(row), fillOpacity: .62, weight: .6 })
      .bindPopup(`<strong>${esc(row.event)}</strong><span>${esc(row.date)} · ${esc(row.vessel_category)}</span><br><small>${esc(row.description.slice(0, 150))}</small>`)
      .addTo(state.mapLayer);
  });
  $("mapNote").textContent = `${numberFormat.format(valid.length)} coordinates${step > 1 ? ` · showing 1 in ${step}` : ""}`;
  if (valid.length && valid.length < 900) {
    const bounds = L.latLngBounds(valid.map((row) => [row.lat, row.lon]));
    if (bounds.isValid()) state.map.fitBounds(bounds.pad(.12), { maxZoom: 7 });
  } else {
    state.map.setView([54.4, -3.4], 4);
  }
}

function renderPatterns() {
  const records = state.filtered;
  const categories = topEntries(countBy(records, "vessel_category"), 5).map(([label]) => label);
  const events = topEntries(countBy(records, "event"), 6).map(([label]) => label);
  const cells = categories.flatMap((category) => events.map((event) => ({ category, event, count: records.filter((row) => row.vessel_category === category && row.event === event).length })));
  const max = Math.max(...cells.map((cell) => cell.count), 1);
  const header = `<div class="heatmap-row heatmap-header"><div></div>${events.map((event) => `<div>${esc(event)}</div>`).join("")}</div>`;
  const rows = categories.map((category) => {
    const rowCells = events.map((event) => {
      const count = cells.find((cell) => cell.category === category && cell.event === event).count;
      const intensity = .08 + .82 * Math.sqrt(count / max);
      const selected = state.selectedPattern?.category === category && state.selectedPattern?.event === event ? " selected" : "";
      return `<button class="heat-cell${selected}" data-category="${esc(category)}" data-event="${esc(event)}" style="background:rgba(20,125,128,${intensity.toFixed(2)})" title="${esc(category)} · ${esc(event)}: ${count}">${numberFormat.format(count)}</button>`;
    }).join("");
    return `<div class="heatmap-row"><div class="heatmap-label">${esc(category)}</div>${rowCells}</div>`;
  }).join("");
  $("heatmap").innerHTML = header + rows;
  document.querySelectorAll(".heat-cell").forEach((button) => button.addEventListener("click", () => selectPattern(button.dataset.category, button.dataset.event)));

  const outcomeCategories = topEntries(countBy(records, "vessel_category"), 6).map(([label]) => label);
  const outcomes = outcomeCategories.map((category) => {
    const rowsForCategory = records.filter((row) => row.vessel_category === category);
    return { category, injuries: rowsForCategory.reduce((sum, row) => sum + row.injuries, 0), fatalities: rowsForCategory.reduce((sum, row) => sum + row.fatalities, 0) };
  });
  renderGroupedBars($("outcomeChart"), outcomes);
  if (state.selectedPattern) updatePatternDetail();
}

function renderSeverityMatrix(matrix) {
  const cells = matrix.cells;
  const maxShare = Math.max(...cells.filter((cell) => cell.n >= 10).map((cell) => cell.share), .01);
  const header = `<div class="severity-matrix-row severity-matrix-header"><div></div>${matrix.events.map((event) => `<div>${esc(event)}</div>`).join("")}</div>`;
  const rows = matrix.categories.map((category) => {
    const categoryCells = matrix.events.map((event) => cells.find((cell) => cell.category === category && cell.event === event));
    return `<div class="severity-matrix-row"><div class="severity-matrix-label">${esc(category)}</div>${categoryCells.map((cell) => {
      const lowSample = cell.n < 10;
      const intensity = lowSample ? .04 : .12 + .78 * Math.sqrt(cell.share / maxShare);
      const title = `${category} · ${cell.event}: ${pct(cell.share)} serious/very serious (${cell.serious}/${cell.n}); 95% CI ${pct(cell.ci_low)}–${pct(cell.ci_high)}`;
      return `<div class="severity-cell${lowSample ? " low-sample" : ""}" style="background:rgba(183,67,61,${intensity.toFixed(2)})" title="${esc(title)}"><strong>${cell.n ? pct(cell.share) : "—"}</strong><small>n=${numberFormat.format(cell.n)}</small></div>`;
    }).join("")}</div>`;
  }).join("");
  $("severityMatrix").innerHTML = header + rows;
}

function renderForestPlot(model) {
  const min = Math.log(.25), max = Math.log(16);
  const position = (value) => 100 * (Math.log(Math.max(.25, Math.min(16, value))) - min) / (max - min);
  $("forestPlot").innerHTML = model.effects.map((effect) => {
    const left = position(effect.ci_low);
    const right = position(effect.ci_high);
    const point = position(effect.odds_ratio);
    const significant = effect.ci_low > 1 || effect.ci_high < 1;
    return `<div class="forest-row">
      <span class="forest-label">${esc(effect.label)}</span>
      <div class="forest-scale"><i class="forest-reference"></i><span class="forest-ci ${significant ? "significant" : ""}" style="left:${left}%;width:${Math.max(1, right - left)}%"></span><b style="left:${point}%"></b></div>
      <span class="forest-value">${effect.odds_ratio.toFixed(2)} <small>${effect.ci_low.toFixed(2)}–${effect.ci_high.toFixed(2)}</small></span>
    </div>`;
  }).join("");
}

function renderPersonFlow(flow) {
  const width = 1100, height = 500, nodeWidth = 13, padding = 11;
  const colors = [palette.teal, palette.gold, palette.coral];
  const totals = flow.columns.map((column, stage) => column.reduce((sum, name) => {
    const links = flow.links.filter((link) => stage === 0 ? link.stage === 0 && link.source === name : stage === 1 ? link.stage === 0 && link.target === name : link.stage === 1 && link.target === name);
    return sum + links.reduce((subtotal, link) => subtotal + link.value, 0);
  }, 0));
  const scale = Math.min(...flow.columns.map((column, stage) => (height - padding * (column.length - 1)) / Math.max(totals[stage], 1)));
  const xPositions = [245, 565, 885];
  const nodes = new Map();
  flow.columns.forEach((column, stage) => {
    const values = column.map((name) => flow.links.filter((link) => stage === 0 ? link.stage === 0 && link.source === name : stage === 1 ? link.stage === 0 && link.target === name : link.stage === 1 && link.target === name).reduce((sum, link) => sum + link.value, 0));
    const used = values.reduce((sum, value) => sum + value * scale, 0) + padding * (column.length - 1);
    let y = (height - used) / 2;
    column.forEach((name, index) => {
      const node = { name, stage, x: xPositions[stage], y, height: Math.max(2, values[index] * scale), incoming: 0, outgoing: 0, value: values[index] };
      nodes.set(`${stage}|${name}`, node);
      y += node.height + padding;
    });
  });
  const links = [...flow.links].sort((a, b) => b.value - a.value).map((link) => {
    const source = nodes.get(`${link.stage}|${link.source}`);
    const target = nodes.get(`${link.stage + 1}|${link.target}`);
    const thickness = Math.max(1, link.value * scale);
    const sourceY = source.y + source.outgoing + thickness / 2;
    const targetY = target.y + target.incoming + thickness / 2;
    source.outgoing += thickness;
    target.incoming += thickness;
    const startX = source.x + nodeWidth;
    const endX = target.x;
    const middle = (startX + endX) / 2;
    return `<path d="M${startX},${sourceY} C${middle},${sourceY} ${middle},${targetY} ${endX},${targetY}" fill="none" stroke="${colors[link.stage]}" stroke-opacity=".2" stroke-width="${thickness}"><title>${esc(link.source)} → ${esc(link.target)}: ${numberFormat.format(link.value)}</title></path>`;
  }).join("");
  const nodeMarkup = [...nodes.values()].map((node) => {
    const labelX = node.stage === 0 ? node.x - 8 : node.x + nodeWidth + 8;
    const anchor = node.stage === 0 ? "end" : "start";
    return `<rect x="${node.x}" y="${node.y}" width="${nodeWidth}" height="${node.height}" rx="2" fill="${colors[node.stage]}"><title>${esc(node.name)}: ${numberFormat.format(node.value)}</title></rect><text x="${labelX}" y="${node.y + node.height / 2 + 3}" text-anchor="${anchor}">${esc(node.name)} <tspan>${numberFormat.format(node.value)}</tspan></text>`;
  }).join("");
  const headings = ["OCCURRENCE EVENT", "PERSON TYPE", "RECORDED OUTCOME"].map((heading, index) => `<text class="flow-heading" x="${xPositions[index]}" y="12">${heading}</text>`).join("");
  $("personFlow").innerHTML = `<svg viewBox="0 0 ${width} ${height + 20}" role="img" aria-label="Affected-person record flows">${headings}${links}${nodeMarkup}</svg>`;
}

function renderProfileBars(element, rows) {
  const max = Math.max(...rows.map((row) => row.damage_share), .01);
  element.innerHTML = `<div class="profile-legend"><span><i></i>Any recorded damage</span><span><i></i>Material damage / vessel loss</span></div>${rows.map((row) => `
    <div class="profile-row">
      <span>${esc(row.band)}<small>n=${numberFormat.format(row.n)}</small></span>
      <div class="profile-track"><i style="width:${100 * row.damage_share / max}%"></i><b style="width:${100 * row.material_loss_share / max}%"></b></div>
      <strong>${pct(row.damage_share)}</strong>
    </div>`).join("")}`;
}

function renderConsequences() {
  const analysis = state.data.analysis;
  if (!analysis) return;
  const model = analysis.severity_model;
  $("modelSample").textContent = numberFormat.format(model.n);
  $("modelOutcomes").textContent = `${numberFormat.format(model.positive_outcomes)} · ${(100 * model.positive_rate).toFixed(1)}%`;
  $("modelAuc").textContent = model.auc.toFixed(3);
  renderSeverityMatrix(analysis.severity_matrix);
  renderForestPlot(model);
  renderPersonFlow(analysis.person_flow);
  renderProfileBars($("ageDamageChart"), analysis.vessel_profile.by_age);
  renderProfileBars($("tonnageDamageChart"), analysis.vessel_profile.by_tonnage);
}

function selectPattern(category, event) {
  state.selectedPattern = { category, event };
  renderPatterns();
}

function updatePatternDetail() {
  const { category, event } = state.selectedPattern;
  const rows = state.filtered.filter((row) => row.vessel_category === category && row.event === event);
  const seriousCount = rows.filter(serious).length;
  const affected = rows.reduce((sum, row) => sum + row.affected_people, 0);
  $("selectionTitle").textContent = `${category} · ${event}`;
  $("selectionDescription").textContent = `${numberFormat.format(rows.length)} reported records match this combination in the current filter scope.`;
  $("selectionCount").textContent = numberFormat.format(rows.length);
  $("selectionSerious").textContent = rows.length ? pct(seriousCount / rows.length) : "—";
  $("selectionPeople").textContent = numberFormat.format(affected);
}

function evidenceMatchesTheme(row, theme) {
  if (theme === "All") return true;
  const text = `${row.event} ${row.event_detail} ${row.description}`.toLowerCase();
  return themes[theme].some((keyword) => text.includes(keyword));
}

function renderEvidence() {
  const reportRows = state.filtered.filter((row) => row.report_url);
  const query = ($("evidenceSearch")?.value || "").trim().toLowerCase();
  const visible = reportRows.filter((row) => {
    const text = `${row.description} ${row.event} ${row.vessel_category} ${row.ship_type}`.toLowerCase();
    return (!query || text.includes(query)) && evidenceMatchesTheme(row, state.evidenceTheme);
  });
  $("reportCount").textContent = numberFormat.format(reportRows.length);
  $("activeTheme").textContent = state.evidenceTheme;
  $("evidenceList").innerHTML = visible.length ? visible.slice(0, 80).map((row) => `
    <button class="evidence-card ${state.selectedEvidence === row.id ? "active" : ""}" data-evidence-id="${esc(row.id)}">
      <div class="evidence-card-meta"><span>${esc(row.event)}</span><span>${esc(row.date || row.year)}</span></div>
      <strong>${esc(row.description || "Published investigation record")}</strong>
      <p>${esc(row.vessel_category)} · ${esc(row.severity)}${row.publication_no ? ` · ${esc(row.publication_no)}` : ""}</p>
    </button>`).join("") : `<div class="panel"><strong>No report-linked occurrences match the current filters.</strong><p>Try broadening the year, event, vessel or theme selection.</p></div>`;
  document.querySelectorAll("[data-evidence-id]").forEach((button) => button.addEventListener("click", () => showEvidence(button.dataset.evidenceId)));
  if (state.selectedEvidence && !visible.some((row) => row.id === state.selectedEvidence)) state.selectedEvidence = null;
  if (!state.selectedEvidence && visible.length) showEvidence(visible[0].id, false);
}

function showEvidence(id, rerenderList = true) {
  const row = state.data.records.find((record) => record.id === id);
  if (!row) return;
  state.selectedEvidence = id;
  $("evidenceDetail").innerHTML = `
    <span class="panel-kicker">Report-linked occurrence</span>
    <h2>${esc(row.event)}</h2>
    <p>${esc(row.description || "No public description was supplied in the occurrence table.")}</p>
    <div class="detail-grid">
      <div><span>Date</span><strong>${esc(row.date || String(row.year))}</strong></div>
      <div><span>Severity</span><strong>${esc(row.severity)}</strong></div>
      <div><span>Vessel category</span><strong>${esc(row.vessel_category)}</strong></div>
      <div><span>Location</span><strong>${esc(row.region)}</strong></div>
    </div>
    <div class="interpretation-box"><strong>Evidence status</strong><p>The source link is preserved from the official occurrence record. Page-level extraction has not yet been applied in this prototype.</p></div>
    <a class="report-link" href="${esc(row.report_url)}" target="_blank" rel="noreferrer">Open published report ↗</a>`;
  if (rerenderList) renderEvidence();
}

function setupEvidenceControls() {
  $("themePills").innerHTML = Object.keys(themes).map((theme) => `<button class="theme-pill ${theme === "All" ? "active" : ""}" data-theme="${esc(theme)}">${esc(theme)}</button>`).join("");
  document.querySelectorAll("[data-theme]").forEach((button) => button.addEventListener("click", () => {
    state.evidenceTheme = button.dataset.theme;
    document.querySelectorAll("[data-theme]").forEach((item) => item.classList.toggle("active", item.dataset.theme === state.evidenceTheme));
    state.selectedEvidence = null;
    renderEvidence();
  }));
  $("evidenceSearch").addEventListener("input", renderEvidence);
}

function renderQuality() {
  const quality = state.data.quality;
  $("qualityOccurrences").textContent = numberFormat.format(quality.rows.occurrences);
  $("qualityVessels").textContent = numberFormat.format(quality.rows.vessels);
  $("qualityPeople").textContent = numberFormat.format(quality.rows.affected_people);
  const unmatched = quality.unmatched_vessels + quality.unmatched_people;
  $("qualityIntegrity").textContent = unmatched === 0 ? "100%" : `${numberFormat.format(unmatched)} unmatched`;
  renderMissingBars($("missingChart"), quality.missingness);
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  document.querySelectorAll("[data-tab-jump]").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tabJump)));
}

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `${tab}Panel`));
  const titles = { overview: "Reported occurrence overview", patterns: "Pattern explorer", consequences: "Severity & human consequences", evidence: "Investigation evidence", quality: "Data confidence" };
  $("pageTitle").textContent = titles[tab];
  if (tab === "overview") setTimeout(() => state.map?.invalidateSize(), 20);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function generateBrief() {
  const records = state.filtered;
  const topEvents = topEntries(countBy(records, "event"), 3);
  const topVessels = topEntries(countBy(records, "vessel_category"), 2);
  const seriousCount = records.filter(serious).length;
  const injuries = records.reduce((sum, row) => sum + row.injuries, 0);
  const fatalities = records.reduce((sum, row) => sum + row.fatalities, 0);
  const reportCount = records.filter((row) => row.report_url).length;
  $("briefContent").innerHTML = `
    <span class="brief-eyebrow">Auto-assembled evidence brief · prototype</span>
    <h2>Reported UK marine occurrence patterns</h2>
    <div class="brief-meta">Scope: ${state.filters.yearStart}–${state.filters.yearEnd} · Generated ${new Date().toLocaleDateString("en-GB")} · Source: UK MAIB public data</div>
    <div class="brief-kpis">
      <div><strong>${numberFormat.format(records.length)}</strong><span>Occurrences</span></div>
      <div><strong>${numberFormat.format(injuries)}</strong><span>Injuries</span></div>
      <div><strong>${numberFormat.format(fatalities)}</strong><span>Fatalities</span></div>
      <div><strong>${numberFormat.format(reportCount)}</strong><span>Report links</span></div>
    </div>
    <h3>Key descriptive findings</h3>
    <ul>
      <li>The most frequently recorded event categories in this scope are ${topEvents.map(([name, count]) => `${esc(name)} (${numberFormat.format(count)})`).join(", ")}.</li>
      <li>The leading vessel categories by occurrence count are ${topVessels.map(([name, count]) => `${esc(name)} (${numberFormat.format(count)})`).join(" and ")}.</li>
      <li>${numberFormat.format(seriousCount)} records (${records.length ? pct(seriousCount / records.length) : "0%"}) are classified as serious or very serious.</li>
    </ul>
    <h3>Interpretation</h3>
    <p>These results describe the composition of publicly reported occurrences in the selected scope. They do not estimate accident probability. Differences between vessel categories may reflect fleet size, operating exposure, reporting practice and other unobserved factors.</p>
    <h3>Evidence and limitations</h3>
    <p>${numberFormat.format(reportCount)} records in the selected scope include a published-report link. The current prototype preserves those links but does not yet extract or validate page-level evidence. The latest source year is incomplete, and raw counts should not be interpreted as risk rates.</p>
    <h3>Suggested next analytical step</h3>
    <p>Prioritise a report-level review of the leading event–vessel combinations, then test whether common contributing themes persist after accounting for reporting coverage and an appropriate exposure denominator.</p>`;
  $("briefModal").showModal();
}

function setupBrief() {
  $("briefButton").addEventListener("click", generateBrief);
  $("closeBrief").addEventListener("click", () => $("briefModal").close());
  $("printBrief").addEventListener("click", () => window.print());
  $("copyBrief").addEventListener("click", async () => {
    await navigator.clipboard.writeText($("briefContent").innerText);
    $("copyBrief").textContent = "Copied";
    setTimeout(() => { $("copyBrief").textContent = "Copy summary"; }, 1200);
  });
}

async function init() {
  try {
    const response = await fetch("data/dashboard.json");
    if (!response.ok) throw new Error(`Data request failed: ${response.status}`);
    state.data = await response.json();
    $("sourceLink").href = state.data.meta.source_url;
    $("dateStamp").textContent = `UK public occurrence data · ${state.data.meta.year_min}–${state.data.meta.year_max}`;
    $("footerUpdated").textContent = `Source updated ${state.data.meta.last_source_update || "not recorded"}`;
    setupFilters();
    setupTabs();
    setupEvidenceControls();
    setupBrief();
    renderConsequences();
    renderQuality();
    applyFilters();
    $("mobileMenu").addEventListener("click", () => $("sidebar").classList.toggle("open"));
    setTimeout(() => $("loadingScreen").classList.add("hidden"), 250);
  } catch (error) {
    console.error(error);
    $("loadingScreen").innerHTML = `<strong>Dashboard data could not be loaded.</strong><p>${esc(error.message)}</p>`;
  }
}

init();
