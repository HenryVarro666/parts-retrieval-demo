(() => {
  "use strict";

  const I = window.PartsI18n;
  const t = I.t;
  const $ = (id) => document.getElementById(id);
  const state = {
    data: null, baseline: null, run: null, file: null, filter: "all",
    mode: "preset", imageMode: "evidence", loadingData: false, dataError: null,
    live: { image: null, filename: "", record: null, catalog: null, loading: false, error: null, engine: "rapidocr", multiview: true, pipeline: "sqlite", verifyVisual: false, channel: "shape", timing: "", viewCache: new Map() },
  };
  const labels = { ocr: "OCR", identifier: "型号检索", text: "文字检索", image: "图像检索", fusion: "融合排序", sqlite: "SQLite 召回", sql: "SQLite 召回", sql_search: "SQLite 召回", retrieval: "候选检索", candidate_pool: "候选合并", shape: "形状估计与重排", vlm: "视觉核验", verification_prepare: "视觉输入准备", total: "总计" };
  const keywordKinds = { model: "型号线索", model_like: "型号线索", alias: "型号别名", manufacturer: "制造商", maker: "制造商", description: "描述文字", text: "普通文字", word: "普通文字", batch: "批次线索", noise: "批次 / 噪声", likely_noise: "批次 / 噪声", number: "数字线索", numeric: "数字线索" };
  const matchKinds = { exact: "精确匹配", folded: "容错别名", exact_alias: "精确别名", folded_alias: "容错别名", alias_exact: "精确别名", alias_folded: "容错别名", fuzzy: "模糊匹配", fts: "全文检索", manufacturer: "制造商匹配", maker: "制造商匹配", description: "描述匹配" };
  const fieldNames = { alias: "别名", aliases: "别名", name: "名称", manufacturer: "制造商", maker: "制造商", description: "描述" };
  const text = (id, value) => { $(id).textContent = value == null ? "" : String(value); };
  const show = (id, visible) => { $(id).toggleAttribute("hidden", !visible); };
  const announce = (message) => text("live-status", message);
  const uiError = (key, params = {}) => Object.assign(new Error(t(key, params)), { uiKey: key, params });
  const errorText = error => error?.uiKey ? t(error.uiKey, error.params) : I.localize(error?.message || error || "");
  const node = (tag, className, value) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value != null) el.textContent = String(value);
    return el;
  };
  const finite = (value) => value != null && value !== "" && Number.isFinite(Number(value));
  const number = (value) => finite(value) ? Number(value) : null;
  const basename = (file) => String(file || "").split(/[\\/]/).pop();
  const runLabel = (run) => run ? I.messages[`run.${run.name}`] ? t(`run.${run.name}`) : I.localize(run.label || run.name) : "—";
  const catalog = () => state.mode === "live" ? state.live.catalog || state.data?.catalog || {} : state.data?.catalog || {};
  const partName = (id, cat = catalog()) => I.messages[`part.${id}`] ? t(`part.${id}`) : cat[id]?.name || id || t("state.none");
  const sample = () => state.data?.samples?.find((item) => item.file === state.file) || null;
  const recordFor = (run, file = state.file) => {
    if (!run || !state.data) return null;
    const records = state.data.records?.[run.name];
    return Array.isArray(records) ? records.find((record) => record.file === file) || null : records?.[file] || null;
  };
  const currentRecord = () => state.mode === "live" ? state.live.record : recordFor(state.run);
  const activeChannel = (run = state.run) => state.mode === "live" ? state.live.channel : run?.channel || "fused";
  const rankings = (record, run = state.run) => {
    if (!record) return [];
    const channel = activeChannel(run);
    return record.rankings?.[channel] || record.rankings?.fused || [];
  };
  const selectedView = (record) => {
    const evidence = record?.evidence;
    return evidence?.views?.find((view) => view.id === evidence.selected_view) || evidence?.views?.[0] || null;
  };
  const complete = (run) => {
    if (!run) return false;
    const n = number(run.summary?.n) || 0;
    return (run.status === "complete" || (!run.status && n > 0)) && (!state.data?.samples?.length || n >= state.data.samples.length);
  };
  const rate = (summary, metric) => {
    const n = number(summary?.n);
    const k = number(summary?.[`${metric}_k`]);
    if (n && k != null) return k / n;
    const value = number(summary?.[metric]);
    return value == null ? null : value > 1 ? value / 100 : value;
  };
  const percent = (value) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
  const count = (summary, metric) => {
    const k = number(summary?.[`${metric}_k`]);
    const n = number(summary?.n);
    return k == null || n == null ? "" : `${k} / ${n}`;
  };
  const duration = (value) => {
    const ms = number(value);
    if (ms == null) return "—";
    return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms >= 10000 ? 1 : 2)} s`;
  };
  const valueText = (value) => {
    if (value == null) return "";
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(t("separator.semicolon"));
    if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${valueText(item)}`).join(t("separator.semicolon"));
    return String(value);
  };
  const safeLink = (value) => {
    try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : null; }
    catch { return null; }
  };
  const imageURL = (file, view) => {
    const params = new URLSearchParams({ file });
    if (view?.crop?.length === 4 && view.crop.every(finite)) params.set("crop", view.crop.map(Number).join(","));
    if ([90, 180, 270].includes(Number(view?.rotation))) params.set("rotation", String(Number(view.rotation)));
    return `/api/image?${params.toString()}`;
  };
  const viewDescription = (view) => {
    if (!view) return "";
    const bits = [];
    if (/^center(?:_|$)/i.test(view.id || "") || (view.crop?.length === 4 && (Number(view.crop[0]) > 0 || Number(view.crop[1]) > 0))) bits.push(t("view.center"));
    else bits.push(t("view.full"));
    if (Number(view.rotation)) bits.push(t("view.rotation", { angle: Number(view.rotation) }));
    return bits.join(" · ");
  };
  const sqliteRun = (run) => Boolean(run && (/^sqlite_/.test(run.name || "") || ["sql", "hybrid", "shape", "gated"].includes(run.channel)));
  const compositeTiming = (run) => Boolean(run && (sqliteRun(run) ? /stage.only|stage.sum|separate|projection|not end.to.end|sum of|合计|分阶段|估算/i.test(run.config?.timing || "") : /cached baseline|not end.to.end|model load excluded/i.test(run.config?.timing || "") || ["reranked", "ensemble"].includes(run.channel)));
  const compositeTimingNote = () => t("timing.old");
  const timingNote = (run) => {
    if (sqliteRun(run)) {
      const timing = run.config?.timing || "";
      if (/gate projection/i.test(timing)) return t("timing.gate");
      if (/separately measured new.pool VLM/i.test(timing)) return t("timing.newVisual");
      if (/measured fresh.*OCR.*SQLite.*shape stages/i.test(timing)) return t("timing.fresh");
      return timing || t("timing.recorded");
    }
    return run?.channel === "ensemble" ? t("timing.ensemble") : compositeTimingNote();
  };
  const timingScopeLabel = (run) => sqliteRun(run) && /projection|估算/i.test(run?.config?.timing || "") ? t("timing.gateLabel") : run?.channel === "ensemble" ? t("timing.serialLabel") : t("timing.sumLabel");
  const metricTimingNote = (run) => sqliteRun(run) ? /gate projection/i.test(run.config?.timing || "") ? t("timing.gateShort") : compositeTiming(run) ? t("timing.visualShort") : t("timing.freshShort") : timingNote(run);
  const candidateOrigins = (record, id) => {
    if (activeChannel() === "sql" && record?.retrieval?.candidates?.some((item) => item.part_id === id)) return ["sqlite"];
    const poolItem = record?.retrieval?.pool?.find((item) => item.part_id === id);
    return Array.isArray(poolItem?.origins) ? poolItem.origins : [];
  };
  const originText = (origins) => origins.map((origin) => ({ sqlite: t("origin.sqlite"), appearance: t("origin.appearance") })[origin] || String(origin)).join(" + ");
  const sqlCandidate = (record, id) => record?.retrieval?.candidates?.find((item) => item.part_id === id);
  const matchText = (match) => {
    const term = match.term || match.text || "";
    const field = I.localize(fieldNames[match.field] || match.field) || t("field.catalog");
    const kind = I.localize(matchKinds[match.kind] || match.kind) || t("match.match");
    return `${term ? `「${term}」→ ` : ""}${field}${match.alias ? `「${match.alias}」` : ""} · ${kind}`;
  };
  const viewKey = (view) => JSON.stringify([view.id, view.crop, view.rotation, view.width, view.height]);
  function prepareLiveView(view) {
    const key = viewKey(view);
    const cache = state.live.viewCache;
    if (cache.has(key) || !state.live.image) return;
    cache.set(key, { pending: true });
    const image = new Image();
    image.onload = () => {
      try {
        const crop = view.crop?.length === 4 ? view.crop.map(Number) : [0, 0, image.naturalWidth, image.naturalHeight];
        const [x0, y0, x1, y1] = crop;
        const width = x1 - x0; const height = y1 - y0;
        if (![...crop, width, height].every(Number.isFinite) || width <= 0 || height <= 0) throw new Error("Invalid view geometry");
        const rotation = [90, 180, 270].includes(Number(view.rotation)) ? Number(view.rotation) : 0;
        const rotated = rotation === 90 || rotation === 270;
        const canvas = document.createElement("canvas");
        canvas.width = rotated ? height : width; canvas.height = rotated ? width : height;
        const ctx = canvas.getContext("2d");
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(-rotation * Math.PI / 180);
        ctx.drawImage(image, x0, y0, width, height, -width / 2, -height / 2, width, height);
        cache.set(key, { url: canvas.toDataURL("image/png") });
      } catch { cache.set(key, { error: true }); }
      if (state.live.viewCache === cache && state.mode === "live") renderImage(state.live.record);
    };
    image.onerror = () => { cache.set(key, { error: true }); if (state.live.viewCache === cache && state.mode === "live") renderImage(state.live.record); };
    image.src = state.live.image;
  }
  const filteredSamples = () => (state.data?.samples || []).filter((item) => {
    if (state.filter === "all") return true;
    const baseline = recordFor(state.baseline, item.file);
    return baseline && (baseline.rankings?.fused?.[0] || null) !== item.gt;
  });

  async function loadData() {
    if (state.loadingData) return;
    state.loadingData = true;
    state.dataError = null;
    show("app-error", false);
    $("workbench").setAttribute("aria-busy", "true");
    announce(t("announce.loading"));
    try {
      const response = await fetch("/api/data", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok || data.error) throw data.error ? new Error(data.error) : uiError("error.loadHTTP", { status: response.status });
      if (!Array.isArray(data.runs) || !Array.isArray(data.samples) || !data.catalog) throw new Error(t("error.incompleteData"));
      state.data = data;
      state.baseline = data.runs.find((run) => run.name === "easyocr_whole") || data.runs.find((run) => run.config?.baseline || /baseline|基线/i.test(`${run.name} ${run.label || ""}`)) || data.runs[0] || null;
      state.run = data.runs.find((run) => run.name === state.run?.name) || data.runs.filter(complete).reduce((best, run) => !best || (rate(run.summary, "top1") || 0) > (rate(best.summary, "top1") || 0) ? run : best, null) || state.baseline;
      if (!data.samples.some((item) => item.file === state.file)) state.file = data.samples[0]?.file || null;
      renderRunPicker();
      renderSamplePicker();
      renderAll();
      announce(t("announce.loaded", { photos: data.samples.length, runs: data.runs.length }));
    } catch (error) {
      state.dataError = error;
      text("app-error-text", errorText(error) || t("error.checkService"));
      show("app-error", true);
      text("image-placeholder-title", t("error.recordsUnavailable"));
      text("image-placeholder-description", t("error.reloadService"));
      text("experiments-body", "");
      const row = node("tr"); const cell = node("td", "table-empty", t("error.recordsUnavailable")); cell.colSpan = 8; row.append(cell); $("experiments-body").append(row);
      announce(t("error.loadFailed"));
    } finally {
      state.loadingData = false;
      $("workbench").setAttribute("aria-busy", "false");
    }
  }

  function renderRunPicker() {
    const select = $("run-select");
    select.replaceChildren();
    for (const run of state.data?.runs || []) {
      const option = node("option", "", `${runLabel(run)}${complete(run) ? "" : t("state.incompleteSuffix")}`);
      option.value = run.name;
      select.append(option);
    }
    select.value = state.run?.name || "";
    select.disabled = !state.data?.runs?.length;
  }

  function renderSamplePicker() {
    const items = filteredSamples();
    if (!items.some((item) => item.file === state.file)) state.file = items[0]?.file || null;
    const select = $("sample-select");
    select.replaceChildren();
    for (const [index, item] of items.entries()) {
      const option = node("option", "", `${String(index + 1).padStart(2, "0")} · ${item.gt || t("state.sample")} · ${basename(item.file)}`);
      option.value = item.file;
      select.append(option);
    }
    if (!items.length) select.append(node("option", "", t("state.noSamples")));
    select.disabled = !items.length;
    select.value = state.file || "";
    const index = items.findIndex((item) => item.file === state.file);
    text("sample-position", `${index < 0 ? "00" : String(index + 1).padStart(2, "0")} / ${String(items.length).padStart(2, "0")}`);
    $("previous-sample").disabled = index <= 0;
    $("next-sample").disabled = index < 0 || index >= items.length - 1;
    const errorCount = (state.data?.samples || []).filter((item) => {
      const record = recordFor(state.baseline, item.file);
      return record && record.rankings?.fused?.[0] !== item.gt;
    }).length;
    text("error-count", errorCount || "");
    $("filter-all").setAttribute("aria-pressed", String(state.filter === "all"));
    $("filter-errors").setAttribute("aria-pressed", String(state.filter === "errors"));
  }

  function renderMetrics() {
    const baseline = state.baseline?.summary;
    text("baseline-score", complete(state.baseline) ? percent(rate(baseline, "top1")) : "—");
    text("baseline-detail", baseline ? t("metrics.correct", { count: count(baseline, "top1"), run: runLabel(state.baseline) }) : t("metrics.noBaseline"));
    const baselineExample = complete(state.baseline) && count(baseline, "top1") ? t("metrics.example", { count: count(baseline, "top1"), rate: percent(rate(baseline, "top1")) }) : "";
    text("baseline-explanation", t("metrics.explanation", { example: baselineExample }));
    const classes = Object.keys(state.data?.catalog || {}).length;
    text("scope-count", t("metrics.scope", { photos: state.data?.samples?.length || 0, classes }));
    const composite = state.mode === "preset" && compositeTiming(state.run);
    const showScope = state.mode === "preset" && (composite || sqliteRun(state.run));
    show("latency-scope-note", showScope);
    text("latency-scope-note", showScope ? metricTimingNote(state.run) : "");
    if (state.mode === "live") {
      text("selected-metric-label", t("metrics.input"));
      text("selected-score", state.live.record ? t("metrics.single") : t("metrics.pending"));
      text("selected-detail", t("metrics.noLabel"));
      text("latency-metric-label", t("metrics.serverTime"));
      text("latency-score", duration(state.live.record?.ms?.total));
      text("latency-detail", state.live.loading ? t("metrics.loadingInference") : t("metrics.currentImage", { pipeline: state.live.pipeline === "sqlite" ? t("pipeline.short") : t("pipeline.legacy"), visual: state.live.record?.vlm ? t("pipeline.visualSuffix") : "" }));
    } else {
      const summary = state.run?.summary;
      text("selected-metric-label", t("metrics.current"));
      text("selected-score", complete(state.run) ? percent(rate(summary, "top1")) : t("state.incomplete"));
      text("selected-detail", summary ? t("metrics.correct", { count: count(summary, "top1"), run: runLabel(state.run) }) : t("metrics.noExperiment"));
      text("latency-metric-label", composite ? `${timingScopeLabel(state.run)} · p50` : sqliteRun(state.run) ? t("metrics.recordedTime") : t("metrics.latency"));
      text("latency-score", complete(state.run) ? duration(summary?.latency_ms?.p50) : "—");
      text("latency-detail", complete(state.run) ? `p95 ${duration(summary?.latency_ms?.p95)}${composite || sqliteRun(state.run) ? "" : t("metrics.warmed")}` : t("metrics.incomplete"));
    }
    text("evaluation-note-text", t("metrics.limit", { photos: state.data?.samples?.length || 0, classes }));
  }

  function renderMode() {
    const live = state.mode === "live";
    $("mode-preset").setAttribute("aria-pressed", String(!live));
    $("mode-live").setAttribute("aria-pressed", String(live));
    show("preset-controls", !live);
    show("live-controls", live);
    show("run-picker", !live);
    show("live-evidence-heading", live);
    show("sample-comparison", !live);
    text("input-mode-tag", live ? t("state.liveOCR") : t("input.replay"));
    $("input-mode-tag").className = `tag ${live ? "tag-teal" : ""}`;
    text("evidence-mode-tag", live ? state.live.loading ? t("state.running") : t("state.live") : t("state.saved"));
    text("live-engine-name", `${state.live.engine === "rapidocr" ? "RapidOCR" : "EasyOCR"}${state.live.multiview ? t("view.multipleSuffix") : t("view.fullSuffix")}`);
    text("live-result-description", t("evidence.uploaded", { pipeline: state.live.pipeline === "sqlite" ? t("pipeline.sqlite") : t("pipeline.legacy"), visual: state.live.record?.vlm ? t("pipeline.localVisualSuffix") : "" }));
    $("predict-button").disabled = !state.live.image || state.live.loading;
    $("pipeline-select").disabled = state.live.loading;
    $("engine-select").disabled = state.live.loading;
    $("multiview-input").disabled = state.live.loading;
    $("verify-visual-input").disabled = state.live.loading || $("pipeline-select").value !== "sqlite";
    show("verify-visual-note", $("pipeline-select").value !== "sqlite");
    $("verify-visual-input").closest("label").classList.toggle("is-disabled", $("pipeline-select").value !== "sqlite");
    text("live-pipeline-note", $("pipeline-select").value === "sqlite" ? t("input.sqliteLiveNote") + ($("verify-visual-input").checked ? t("input.verifyLiveNote") : t("input.loadNote")) : t("input.legacyLiveNote"));
    $("upload-input").disabled = state.live.loading;
    text("predict-label", state.live.loading ? t("input.predicting") : state.live.record ? t("input.predictAgain") : t("input.predict"));
    show("inference-overlay", live && state.live.loading);
    $("workbench").setAttribute("aria-busy", String(live && state.live.loading));
  }

  function renderImage(record) {
    const live = state.mode === "live";
    const item = sample();
    const view = selectedView(record);
    if (live && view) prepareLiveView(view);
    const liveView = live && view ? state.live.viewCache.get(viewKey(view)) : null;
    const canShowEvidence = Boolean(view && (!live || liveView?.url));
    const evidence = state.imageMode === "evidence" && canShowEvidence;
    const file = live ? record?.file : item?.file;
    const source = evidence ? live ? liveView.url : imageURL(file, view) : live ? state.live.image : file ? imageURL(file) : null;
    const img = $("query-image");
    img.onload = () => {
      text("image-dimensions", `${img.naturalWidth} × ${img.naturalHeight} px`);
      show("image-placeholder", false);
    };
    img.onerror = () => {
      show("query-image", false); show("ocr-overlay", false); show("image-placeholder", true);
      text("image-placeholder-title", t("image.unavailable")); text("image-placeholder-description", t("image.keepEvidence"));
    };
    show("query-image", Boolean(source));
    show("image-placeholder", !source);
    if (source && img.getAttribute("src") !== source) {
      text("image-dimensions", "");
      img.src = source;
    }
    if (!source) {
      img.removeAttribute("src");
      text("image-placeholder-title", live ? t("image.uploadPrompt") : t("image.noSample"));
      text("image-placeholder-description", live ? t("image.clearMarkings") : t("image.otherFilter"));
      text("image-dimensions", "");
    }
    img.alt = live ? t("image.uploadedAlt") : t("image.sampleAlt", { part: partName(item?.gt), id: item?.gt || t("state.unknown") });
    $("view-evidence").disabled = !view || Boolean(liveView?.error);
    $("view-original").setAttribute("aria-pressed", String(!evidence));
    $("view-evidence").setAttribute("aria-pressed", String(evidence));
    const boxes = Array.isArray(view?.boxes) ? view.boxes : [];
    text("box-count", liveView?.pending ? t("image.preparing") : liveView?.error ? t("image.viewUnavailable") : view ? t("image.boxCount", { count: boxes.length }) : record ? t("image.noBoxes") : live ? t("image.afterInference") : t("state.waiting"));
    const overlay = $("ocr-overlay");
    overlay.replaceChildren();
    const width = number(view?.width); const height = number(view?.height);
    const draw = evidence && width > 0 && height > 0 && boxes.length > 0;
    show("ocr-overlay", draw);
    if (draw) {
      overlay.setAttribute("viewBox", `0 0 ${width} ${height}`);
      overlay.setAttribute("preserveAspectRatio", "xMidYMid meet");
      for (const [index, box] of boxes.entries()) {
        const points = Array.isArray(box.points) ? box.points.filter((point) => Array.isArray(point) && point.length >= 2 && finite(point[0]) && finite(point[1])).map((point) => [Number(point[0]), Number(point[1])]) : [];
        if (points.length < 3) continue;
        const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
        polygon.setAttribute("points", points.map((point) => point.join(",")).join(" "));
        polygon.setAttribute("class", "ocr-box");
        const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
        title.textContent = `${index + 1}. ${box.text || t("image.box")}`; polygon.append(title); overlay.append(polygon);
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        label.setAttribute("x", String(points[0][0] + 2)); label.setAttribute("y", String(Math.max(14, points[0][1] - 6)));
        label.setAttribute("font-size", String(Math.max(12, Math.min(width, height) / 42)));
        label.setAttribute("class", "ocr-box-label"); label.textContent = String(index + 1); overlay.append(label);
      }
    }
    show("image-view-label", Boolean(source));
    text("image-view-label", evidence ? `OCR · ${viewDescription(view)}` : t("image.originalLabel"));
    text("image-filename", live ? state.live.filename || t("input.upload") : basename(item?.file) || "—");
    const link = !live && safeLink(item?.page_url);
    show("source-link", Boolean(link)); if (link) $("source-link").href = link;
    const attribution = live ? "" : [item?.artist, item?.license].filter(Boolean).map((value) => String(value).replace(/<[^>]*>/g, "")).join(" · ");
    text("image-attribution", attribution); show("image-attribution", Boolean(attribution));
  }

  function renderEvidence(record) {
    const live = state.mode === "live";
    const view = selectedView(record);
    const observed = record?.ocr_text || record?.evidence?.text || "";
    text("ocr-text", observed || (record ? t("ocr.none") : live ? state.live.loading ? t("ocr.reading") : t("ocr.start") : t("ocr.noRecord")));
    $("ocr-text").classList.toggle("is-empty", !observed);
    text("ocr-view-detail", view ? t("ocr.view", { view: viewDescription(view) }) : record ? t("ocr.noGeometry") : "");
    text("run-status", state.run ? complete(state.run) ? t("experiments.status", { status: state.run.channel === "ensemble" ? t("ensemble.replay") : t("experiments.complete"), count: state.run.summary?.n || 0 }) : t("experiments.partial", { count: state.run.summary?.n || 0, total: state.data?.samples?.length || 0 }) : t("metrics.noExperiment"));
    $("run-status").classList.toggle("is-partial", Boolean(state.run && !complete(state.run)));
    const hits = $("identifier-hits"); hits.replaceChildren();
    const idHits = Array.isArray(record?.id_hits) ? record.id_hits : [];
    for (const hit of idHits.slice(0, 4)) {
      const pid = Array.isArray(hit) ? hit[0] : hit.id || hit.pid || hit.part_id;
      const alias = Array.isArray(hit) ? hit[2] : hit.alias;
      const row = node("div", "identifier-hit"); row.append(node("code", "", alias || pid), node("span", "", pid)); hits.append(row);
    }
    if (!idHits.length) hits.append(node("p", "empty-note", record ? t("identifier.none") : t("identifier.after")));
    const conflicts = record?.evidence?.conflicts;
    const conflictText = valueText(conflicts);
    const hasConflicts = Array.isArray(conflicts) ? conflicts.length > 0 : Boolean(conflicts && conflictText && conflictText !== "false");
    show("evidence-conflicts", hasConflicts);
    text("evidence-conflicts", hasConflicts ? t("identifier.conflicts", { text: conflictText }) : "");
    const combined = !live && record?.ensemble;
    show("ensemble-section", Boolean(combined));
    if (combined) {
      text("ensemble-status", combined.vlm_called ? t("ensemble.called") : t("ensemble.accepted"));
      text("ensemble-reason", I.localize(combined.reason || ""));
      const votes = $("ensemble-votes"); votes.replaceChildren();
      for (const vote of combined.votes || []) {
        const expert = state.data.runs.find((run) => run.name === vote.expert);
        const row = node("div", "identifier-hit");
        row.append(node("span", "", runLabel(expert || {name: vote.expert})), node("code", "", vote.candidate || t("vlm.abstain")));
        votes.append(row);
      }
    }
    const vlm = record?.vlm;
    show("vlm-section", Boolean(vlm));
    if (vlm) {
      const abstained = Boolean(vlm.abstained);
      text("vlm-status", abstained ? combined ? t("vlm.noVote") : t("vlm.keepOrder") : vlm.selected_id || t("vlm.decided"));
      $("vlm-status").className = `tag ${abstained ? "tag-warning" : "tag-teal"}`;
      text("vlm-reason", vlm.reason || (abstained ? t("vlm.fallback") : t("vlm.noReason")));
      text("vlm-observed", vlm.observed_text ? t("vlm.observed", { text: valueText(vlm.observed_text) }) : "");
      show("vlm-observed", Boolean(vlm.observed_text));
      text("vlm-scope-note", live ? t("vlm.liveScope") : combined ? t("vlm.ensembleScope") : record?.retrieval ? t("vlm.sqliteScope") : t("vlm.oldScope"));
    }
    renderRetrieval(record);
    renderShape(record);
    renderSelectedEvidence(record);
    renderCandidates(record);
    renderTiming(record);
  }

  function renderRetrieval(record) {
    const retrieval = record?.retrieval;
    show("retrieval-section", Boolean(retrieval));
    if (!retrieval) return;
    const keywords = Array.isArray(retrieval.keywords) ? retrieval.keywords : [];
    const candidates = Array.isArray(retrieval.candidates) ? retrieval.candidates : [];
    const pool = Array.isArray(retrieval.pool) ? retrieval.pool : [];
    text("sql-match-count", t("retrieval.count", { count: candidates.length }));
    const keywordList = $("keyword-list"); keywordList.replaceChildren();
    for (const keyword of keywords) {
      const chip = node("span", `keyword-chip${/noise|batch/.test(keyword.kind || "") ? " is-noise" : ""}`);
      chip.append(node("code", "", keyword.text || keyword.normalized || ""), node("small", "", I.localize(keywordKinds[keyword.kind] || keyword.kind) || t("keyword.clue")));
      if (keyword.normalized && keyword.normalized !== keyword.text) chip.title = t("retrieval.normalized", { text: keyword.normalized });
      keywordList.append(chip);
    }
    if (!keywords.length) keywordList.append(node("p", "empty-note", t("retrieval.noKeywords")));
    const strong = Array.isArray(retrieval.strong_ids) ? retrieval.strong_ids : [];
    const supplemental = pool.filter((item) => Array.isArray(item.origins) && item.origins.includes("appearance")).length;
    text("retrieval-summary", t("retrieval.summary", { count: candidates.length, pool: pool.length ? t("retrieval.pool", { count: pool.length }) : "", supplemental: supplemental ? t("retrieval.supplemental", { count: supplemental }) : "", strong: strong.length ? t("retrieval.strong", { ids: strong.join(t("separator.list")) }) : t("retrieval.noStrong"), fallback: activeChannel() === "sql" ? t("retrieval.sqlStage") : retrieval.fallback_used ? t("retrieval.fallback") : "" }));
    const matches = $("sql-matches"); matches.replaceChildren();
    for (const [index, candidate] of candidates.entries()) {
      const receipt = node("div", "sql-receipt");
      const heading = node("div", "sql-receipt-heading");
      heading.append(node("strong", "", `${index + 1}. ${candidate.part_id}`));
      if (candidate.tier) heading.append(node("span", "", I.localize(matchKinds[candidate.tier] || candidate.tier)));
      receipt.append(heading);
      const entries = Array.isArray(candidate.matches) ? candidate.matches : [];
      for (const match of entries) receipt.append(node("p", "", matchText(match)));
      if (!entries.length) receipt.append(node("p", "empty-note", t("retrieval.noReceipts")));
      matches.append(receipt);
    }
    if (!candidates.length) matches.append(node("p", "empty-note", t("retrieval.empty")));
  }

  function renderShape(record) {
    const shape = record?.shape;
    show("shape-section", Boolean(shape));
    if (!shape) return;
    const query = shape.query || {};
    text("shape-status", query.available ? t("shape.available") : t("shape.unavailable"));
    $("shape-status").className = `tag ${query.available ? "tag-teal" : "tag-neutral"}`;
    const features = $("shape-features"); features.replaceChildren();
    const featureNames = { elongation: t("shape.elongation"), solidity: t("shape.solidity"), circularity: t("shape.circularity") };
    if (query.available) {
      for (const [key, label] of Object.entries(featureNames)) {
        const value = number(query.features?.[key]);
        if (value != null) features.append(node("dt", "", label), node("dd", "", value.toFixed(3)));
      }
      if (!features.childElementCount) features.append(node("dt", "", t("shape.features")), node("dd", "", t("shape.noValues")));
    }
    show("shape-features", features.childElementCount > 0);
    const notes = (Array.isArray(query.quality_notes) ? query.quality_notes : [query.quality_notes]).filter(Boolean).map(value => I.localize(valueText(value))).join(t("separator.semicolon"));
    text("shape-quality", [query.method ? t("shape.method", { method: query.method }) : "", notes, !query.available ? t("shape.none") : t("shape.heuristic"), ["sql", "hybrid"].includes(activeChannel()) ? t("shape.notUsed") : ""].filter(Boolean).join(t("separator.semicolon")));
  }

  function renderSelectedEvidence(record) {
    const id = rankings(record)[0];
    const visible = Boolean(record?.retrieval && id);
    show("selected-evidence-section", visible);
    if (!visible) return;
    text("selected-candidate-name", `${partName(id)} · ${id}`);
    const content = $("selected-candidate-evidence"); content.replaceChildren();
    const origins = candidateOrigins(record, id);
    content.append(node("p", "", origins.length ? t("selected.origins", { origins: originText(origins) }) : t("selected.noOrigin")));
    const candidate = sqlCandidate(record, id);
    const entries = Array.isArray(candidate?.matches) ? candidate.matches : [];
    for (const match of entries) content.append(node("p", "", matchText(match)));
    if (!candidate) content.append(node("p", "", t("selected.notSQL")));
    else if (!entries.length) content.append(node("p", "", t("selected.noReceipts")));
    const shapeScore = number(record?.shape?.reference_scores?.[id]);
    content.append(node("p", "", shapeScore == null ? t("shape.noComparison") : t("shape.score", { score: shapeScore.toFixed(3), unused: ["sql", "hybrid"].includes(activeChannel()) ? t("shape.unused") : "" })));
    const decision = record.decision;
    show("candidate-decision", Boolean(decision));
    text("candidate-decision", decision ? `${decision.used_vlm ? t("selected.visual") : decision.accepted_sql_id ? t("selected.keepSQL", { id: decision.accepted_sql_id }) : t("selected.noVisual")}${decision.reason ? `: ${I.localize(decision.reason)}` : ""}` : "");
  }

  function renderCandidates(record) {
    const list = $("candidate-list"); list.replaceChildren();
    const ids = rankings(record).slice(0, 3);
    if (!ids.length) {
      list.append(node("p", "empty-note", state.live.loading && state.mode === "live" ? t("candidates.generating") : record ? t("candidates.empty") : t("candidates.ready")));
      return;
    }
    for (const [index, id] of ids.entries()) {
      const part = catalog()[id] || {};
      const card = node("article", `candidate-card${index === 0 ? " is-first" : ""}`);
      const imageWrap = node("div", "candidate-image-wrap"); imageWrap.append(node("span", "candidate-rank", `0${index + 1}`));
      if (part.catalog_file) {
        const img = node("img"); img.alt = t("candidates.referenceAlt", { part: partName(id) }); img.loading = "lazy"; img.src = imageURL(part.catalog_file);
        img.onerror = () => { img.hidden = true; imageWrap.append(node("span", "image-unavailable", t("candidates.referenceUnavailable"))); };
        imageWrap.append(img);
      } else imageWrap.append(node("span", "image-unavailable", t("candidates.noReference")));
      const info = node("div", "candidate-info"); const heading = node("h4");
      const url = safeLink(part.page_url);
      if (url) { const a = node("a", "", partName(id)); a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.title = t("candidates.source"); heading.append(a); }
      else heading.textContent = partName(id);
      info.append(heading, node("code", "", id));
      const evidence = node("div", "candidate-evidence");
      const hit = record?.id_hits?.find((entry) => (Array.isArray(entry) ? entry[0] : entry.id || entry.pid || entry.part_id) === id);
      if (hit) { const tag = node("span", "identifier-tag", t("identifier.hit")); tag.title = t("identifier.alias", { alias: Array.isArray(hit) ? hit[2] || id : hit.alias || id }); evidence.append(tag); }
      for (const [channel, label] of [["text", t("candidates.text")], ["image", t("candidates.image")]]) {
        const rank = record?.rankings?.[channel]?.indexOf(id);
        if (rank != null && rank >= 0 && rank < 3) evidence.append(node("span", "", `${label} #${rank + 1}`));
      }
      for (const origin of candidateOrigins(record, id)) evidence.append(node("span", origin === "sqlite" ? "identifier-tag" : "", originText([origin])));
      if (record?.retrieval?.strong_ids?.includes(id)) evidence.append(node("span", "identifier-tag", t("identifier.strong")));
      const shapeRank = record?.shape?.ranked_ids?.indexOf(id);
      const shapeScore = number(record?.shape?.reference_scores?.[id]);
      if (!["sql", "hybrid"].includes(activeChannel()) && shapeScore != null && shapeRank != null && shapeRank >= 0 && shapeRank < 3) evidence.append(node("span", "", t("shape.rank", { rank: shapeRank + 1 })));
      if (!evidence.childElementCount) evidence.append(node("span", "", state.mode !== "live" && state.run?.channel === "reranked" ? t("candidates.reranked") : t("candidates.fused")));
      if (state.mode === "preset" && sample()?.gt === id) evidence.append(node("span", "truth-tag", t("input.label")));
      info.append(evidence);
      const receipt = sqlCandidate(record, id)?.matches?.[0];
      if (receipt) info.append(node("p", "candidate-receipt", matchText(receipt)));
      card.append(imageWrap, info); list.append(card);
    }
  }

  function renderTiming(record) {
    const times = Object.entries(record?.ms || {}).filter(([, value]) => finite(value));
    show("timing-details", times.length > 0);
    text("timing-total", duration(record?.ms?.total));
    const content = $("timing-content"); content.replaceChildren();
    const composite = state.mode === "preset" && compositeTiming(state.run);
    for (const [key, value] of times) content.append(node("dt", "", key === "total" && composite ? timingScopeLabel(state.run) : I.localize(labels[key] || key)), node("dd", "", duration(value)));
    const scope = state.mode === "live" ? state.live.timing ? /measured live end.to.end/i.test(state.live.timing) ? t("timing.live") : state.live.timing : "" : composite || sqliteRun(state.run) ? timingNote(state.run) : "";
    show("timing-scope-note", Boolean(scope));
    text("timing-scope-note", scope);
  }

  function setMatchStatus(id, candidate, gt, hasRecord) {
    const el = $(id);
    const correct = Boolean(candidate && gt && candidate === gt);
    el.className = `result-status ${hasRecord && gt ? correct ? "is-correct" : "is-wrong" : ""}`;
    el.textContent = !hasRecord ? t("state.noRecord") : !candidate ? gt ? t("state.emptyWrong") : t("state.noCandidates") : correct ? t("state.correct") : t("state.wrong");
  }

  function renderSampleComparison(record) {
    const item = sample();
    text("ground-truth-name", item ? partName(item.gt, state.data.catalog) : "—");
    text("ground-truth-id", item?.gt || "");
    const baseRecord = recordFor(state.baseline);
    const base = baseRecord?.rankings?.fused?.[0];
    const current = rankings(record)[0];
    text("comparison-baseline-name", base ? partName(base, state.data?.catalog) : baseRecord ? t("state.noCandidates") : "—");
    text("comparison-current-name", current ? partName(current, state.data?.catalog) : record ? t("state.noCandidates") : "—");
    text("comparison-current-label", state.run?.channel === "ensemble" ? t("comparison.ensemble") : state.run?.channel === "gated" ? t("comparison.gated") : state.run?.channel === "reranked" ? t("comparison.visual") : t("metrics.current"));
    setMatchStatus("comparison-baseline-status", base, item?.gt, Boolean(baseRecord));
    setMatchStatus("comparison-current-status", current, item?.gt, Boolean(record));
    let label = t("state.waiting"); let className = "tag tag-neutral";
    if (baseRecord && record) {
      if (!base && !current) label = t("state.bothEmpty");
      else if (base === current) label = t("state.unchanged");
      else if (item?.gt && current === item.gt && base !== item.gt) { label = t("state.gain"); className = "tag tag-teal"; }
      else if (item?.gt && base === item.gt && current !== item.gt) { label = t("state.regression"); className = "tag tag-warning"; }
      else label = t("state.changed");
    }
    text("comparison-change", label); $("comparison-change").className = className;
    const review = state.mode === "preset" && item?.review;
    show("review-details", Boolean(review));
    const content = $("review-content"); content.replaceChildren();
    if (review) {
      const dl = node("dl");
      for (const [key, label] of [["observed_text", t("review.observed")], ["observed_part_number", t("review.part")], ["legibility", t("review.legibility")], ["label_comparison", t("review.comparison")], ["quality_issues", t("review.quality")], ["suggested_action", t("review.action")]]) {
        const value = valueText(review[key]);
        if (value) { const row = node("div"); row.append(node("dt", "", label), node("dd", "", value)); dl.append(row); }
      }
      if (!dl.childElementCount) dl.append(node("dd", "", valueText(review)));
      content.append(dl, node("p", "review-provenance", t("review.provenance")));
    }
  }

  function renderExperiments() {
    const tbody = $("experiments-body"); tbody.replaceChildren();
    for (const run of state.data?.runs || []) {
      const row = node("tr", `${state.mode === "preset" && state.run?.name === run.name ? "is-selected " : ""}${complete(run) ? "" : "is-partial"}`);
      const nameCell = node("td"); const nameWrap = node("div", "run-table-name");
      const button = node("button", "run-table-button", runLabel(run)); button.type = "button";
      button.setAttribute("aria-label", t("experiments.viewReplay", { run: runLabel(run) }));
      if (state.mode === "preset" && state.run?.name === run.name) button.setAttribute("aria-current", "true");
      button.addEventListener("click", () => selectRun(run.name));
      nameWrap.append(button);
      if (run.name === state.baseline?.name) nameWrap.append(node("span", "tag tag-neutral", t("experiments.baseline")));
      if (run.channel === "ensemble") nameWrap.append(node("span", "tag tag-neutral", t("ensemble.badge", { calls: run.summary?.vlm_calls ?? "—", count: run.summary?.n || 0 })));
      if (sqliteRun(run) && ["reranked", "gated"].includes(run.channel) && finite(run.summary?.vlm_calls)) nameWrap.append(node("span", "tag tag-neutral", `VLM ${run.summary.vlm_calls}/${run.summary?.n || 0}`));
      if (!complete(run)) nameWrap.append(node("span", "tag tag-warning", t("state.incomplete")));
      nameCell.append(nameWrap); row.append(nameCell, node("td", "table-count", `${run.summary?.n || 0} / ${state.data?.samples?.length || 0}`));
      if (!complete(run)) {
        const cell = node("td", "partial-caption", t("experiments.excluded")); cell.colSpan = 6; row.append(cell);
      } else {
        for (const metric of ["top1", "top3", "recall5", "recall10"]) {
          const cell = node("td", "", percent(rate(run.summary, metric))); const values = count(run.summary, metric); if (values) cell.title = values; row.append(cell);
        }
        const latency = node("td", "", `${duration(run.summary?.latency_ms?.p50)} / ${duration(run.summary?.latency_ms?.p95)}`);
        if (compositeTiming(run) || sqliteRun(run)) {
          const scope = node("span", "table-time-scope", compositeTiming(run) ? timingScopeLabel(run) : t("timing.stageLabel"));
          scope.title = timingNote(run); latency.append(scope);
        }
        row.append(latency);
        const changes = node("td");
        const wins = run.summary?.wins; const regressions = run.summary?.regressions;
        const changeNumber = (value) => Array.isArray(value) ? value.length : finite(value) ? Number(value) : null;
        if (changeNumber(wins) != null && changeNumber(regressions) != null) changes.append(node("span", "gain", `+${changeNumber(wins)}`), document.createTextNode(" / "), node("span", "regression", `−${changeNumber(regressions)}`));
        else changes.textContent = "—";
        row.append(changes);
      }
      tbody.append(row);
    }
    if (!tbody.childElementCount) { const row = node("tr"); const cell = node("td", "table-empty", t("experiments.none")); cell.colSpan = 8; row.append(cell); tbody.append(row); }
    const hasComposite = state.data?.runs.some(compositeTiming);
    const warmup = state.data?.runs.some((run) => /warmup/i.test(run.config?.timing || ""));
    const sqliteTiming = [...new Set((state.data?.runs || []).filter(sqliteRun).map(timingNote))];
    show("table-timing-note", hasComposite || warmup || sqliteTiming.length > 0);
    const hasEnsemble = state.data?.runs.some((run) => run.channel === "ensemble");
    const hasOldVLM = state.data?.runs.some((run) => !sqliteRun(run) && run.channel === "reranked");
    text("table-timing-note", [warmup ? t("timing.warmupNote") : "", hasOldVLM ? t("timing.oldPrefix", { note: compositeTimingNote() }) : "", hasEnsemble ? t("timing.oldEnsemble") : "", ...sqliteTiming.map(note => t("timing.sqlitePrefix", { note }))].filter(Boolean).join(" "));
  }

  function renderAll() {
    renderMode(); renderMetrics();
    const record = currentRecord();
    renderImage(record); renderEvidence(record); renderSampleComparison(record); renderExperiments();
  }

  function selectRun(name) {
    state.run = state.data?.runs.find((run) => run.name === name) || state.run;
    state.mode = "preset"; $("run-select").value = state.run?.name || "";
    renderAll(); announce(t("announce.run", { run: runLabel(state.run) }));
  }

  function navigateSample(step) {
    if (state.mode !== "preset") return;
    const items = filteredSamples(); const index = items.findIndex((item) => item.file === state.file);
    if (index + step < 0 || index + step >= items.length) return;
    state.file = items[index + step].file; renderSamplePicker(); renderAll();
    announce(t("announce.sample", { index: index + step + 1, total: items.length, part: partName(sample()?.gt) }));
  }

  function setMode(mode) {
    state.mode = mode; renderAll();
    announce(mode === "live" ? t("announce.live") : t("announce.replay"));
  }

  async function readUpload(file) {
    if (!file || state.live.loading) return;
    state.live.error = null;
    show("upload-error", false);
    if (file.size > 10 * 1024 * 1024) { uploadError(t("error.large")); return; }
    if (!(file.type.startsWith("image/") || /\.(jpe?g|png|webp|bmp|gif|tiff?)$/i.test(file.name))) { uploadError(t("error.invalidFile")); return; }
    try {
      const dataURL = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error(t("error.readFile"))); reader.readAsDataURL(file);
      });
      state.live.image = dataURL; state.live.filename = file.name; state.live.record = null; state.live.catalog = null; state.live.channel = "shape"; state.live.timing = ""; state.live.viewCache = new Map(); state.mode = "live";
      text("upload-file-name", `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`);
      renderAll(); announce(t("announce.file", { file: file.name }));
    } catch (error) { uploadError(error); }
  }

  function uploadError(error) { state.live.error = error; const message = errorText(error); text("upload-error", message); show("upload-error", true); announce(message); }

  async function predict() {
    if (!state.live.image || state.live.loading) return;
    state.live.engine = $("engine-select").value; state.live.multiview = $("multiview-input").checked;
    state.live.pipeline = $("pipeline-select").value; state.live.verifyVisual = state.live.pipeline === "sqlite" && $("verify-visual-input").checked;
    state.live.channel = state.live.pipeline === "sqlite" ? state.live.verifyVisual ? "gated" : "shape" : "fused";
    state.live.loading = true; state.live.record = null; state.live.timing = ""; state.live.error = null; show("upload-error", false); renderAll();
    announce(t("announce.running", { visual: state.live.verifyVisual ? t("announce.visualSuffix") : "" }));
    try {
      const response = await fetch("/api/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image: state.live.image, engine: state.live.engine, multiview: state.live.multiview, pipeline: state.live.pipeline, verify_visual: state.live.verifyVisual }) });
      const result = await response.json();
      if (!response.ok || result.error) throw result.error ? new Error(result.error) : uiError("error.predictHTTP", { status: response.status });
      if (!result.record) throw new Error(t("error.noResult"));
      state.live.record = result.record; state.live.catalog = result.catalog || state.data?.catalog || {};
      state.live.channel = result.channel || "fused"; state.live.timing = result.timing || "";
      announce(t("announce.done", { part: partName(rankings(result.record)[0], state.live.catalog) }));
    } catch (error) { uploadError(error || t("error.inference")); }
    finally { state.live.loading = false; renderAll(); }
  }

  $("language-select").addEventListener("change", (event) => {
    I.setLanguage(event.target.value);
    I.apply(document);
    if (state.data) { renderRunPicker(); renderSamplePicker(); }
    if (state.data || state.mode === "live") renderAll();
    if (state.dataError && state.mode === "preset") {
      text("image-placeholder-title", t("error.recordsUnavailable"));
      text("image-placeholder-description", t("error.reloadService"));
      text("experiments-body", "");
      const row = node("tr"); const cell = node("td", "table-empty", t("error.recordsUnavailable")); cell.colSpan = 8; row.append(cell); $("experiments-body").append(row);
    }
    if (state.dataError) text("app-error-text", errorText(state.dataError));
    if (state.live.error) text("upload-error", errorText(state.live.error));
    announce(t("language.changed"));
  });
  $("retry-data").addEventListener("click", loadData);
  $("mode-preset").addEventListener("click", () => setMode("preset"));
  $("mode-live").addEventListener("click", () => setMode("live"));
  $("run-select").addEventListener("change", (event) => selectRun(event.target.value));
  $("sample-select").addEventListener("change", (event) => { state.file = event.target.value; renderSamplePicker(); renderAll(); announce(t("announce.selectedSample", { file: basename(state.file) })); });
  $("previous-sample").addEventListener("click", () => navigateSample(-1));
  $("next-sample").addEventListener("click", () => navigateSample(1));
  for (const [id, filter] of [["filter-all", "all"], ["filter-errors", "errors"]]) $(id).addEventListener("click", () => { state.filter = filter; renderSamplePicker(); renderAll(); announce(t("announce.filter", { filter: filter === "all" ? t("filter.all") : t("filter.errors"), count: filteredSamples().length })); });
  for (const [id, mode] of [["view-original", "original"], ["view-evidence", "evidence"]]) $(id).addEventListener("click", () => { state.imageMode = mode; renderImage(currentRecord()); });
  $("upload-input").addEventListener("change", (event) => readUpload(event.target.files?.[0]));
  $("pipeline-select").addEventListener("change", () => { if ($("pipeline-select").value !== "sqlite") $("verify-visual-input").checked = false; renderMode(); });
  $("verify-visual-input").addEventListener("change", renderMode);
  $("predict-button").addEventListener("click", predict);
  const zone = $("upload-zone");
  for (const type of ["dragenter", "dragover"]) zone.addEventListener(type, (event) => { event.preventDefault(); if (!state.live.loading) zone.classList.add("is-dragging"); });
  for (const type of ["dragleave", "drop"]) zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.remove("is-dragging"); });
  zone.addEventListener("drop", (event) => readUpload(event.dataTransfer?.files?.[0]));
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
    if (["ArrowLeft", "ArrowRight"].includes(event.key) && state.mode === "preset") { event.preventDefault(); navigateSample(event.key === "ArrowLeft" ? -1 : 1); }
  });
  I.apply(document);
  loadData();
})();
