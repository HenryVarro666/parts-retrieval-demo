(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    data: null, baseline: null, run: null, file: null, filter: "all",
    mode: "preset", imageMode: "evidence", loadingData: false,
    live: { image: null, filename: "", record: null, catalog: null, loading: false, engine: "rapidocr", multiview: true, pipeline: "sqlite", verifyVisual: false, channel: "shape", timing: "", viewCache: new Map() },
  };
  const labels = { ocr: "OCR", identifier: "型号检索", text: "文字检索", image: "图像检索", fusion: "融合排序", sqlite: "SQLite 召回", sql: "SQLite 召回", sql_search: "SQLite 召回", retrieval: "候选检索", candidate_pool: "候选合并", shape: "形状估计与重排", vlm: "视觉核验", total: "总计" };
  const keywordKinds = { model: "型号线索", model_like: "型号线索", alias: "型号别名", manufacturer: "制造商", maker: "制造商", description: "描述文字", text: "普通文字", word: "普通文字", batch: "批次线索", noise: "批次 / 噪声", likely_noise: "批次 / 噪声", number: "数字线索", numeric: "数字线索" };
  const matchKinds = { exact: "精确匹配", folded: "容错别名", exact_alias: "精确别名", folded_alias: "容错别名", alias_exact: "精确别名", alias_folded: "容错别名", fuzzy: "模糊匹配", fts: "全文检索", manufacturer: "制造商匹配", maker: "制造商匹配", description: "描述匹配" };
  const fieldNames = { alias: "别名", aliases: "别名", name: "名称", manufacturer: "制造商", maker: "制造商", description: "描述" };
  const text = (id, value) => { $(id).textContent = value == null ? "" : String(value); };
  const show = (id, visible) => { $(id).toggleAttribute("hidden", !visible); };
  const announce = (message) => text("live-status", message);
  const node = (tag, className, value) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value != null) el.textContent = String(value);
    return el;
  };
  const finite = (value) => value != null && value !== "" && Number.isFinite(Number(value));
  const number = (value) => finite(value) ? Number(value) : null;
  const basename = (file) => String(file || "").split(/[\\/]/).pop();
  const runLabel = (run) => run ? String(run.label || run.name) : "—";
  const catalog = () => state.mode === "live" ? state.live.catalog || state.data?.catalog || {} : state.data?.catalog || {};
  const partName = (id, cat = catalog()) => cat[id]?.name || id || "无候选";
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
    if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join("；");
    if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${valueText(item)}`).join("；");
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
    if (/^center(?:_|$)/i.test(view.id || "") || (view.crop?.length === 4 && (Number(view.crop[0]) > 0 || Number(view.crop[1]) > 0))) bits.push("中心裁切");
    else bits.push("完整图像");
    if (Number(view.rotation)) bits.push(`逆时针 ${Number(view.rotation)}°`);
    return bits.join(" · ");
  };
  const sqliteRun = (run) => Boolean(run && (/^sqlite_/.test(run.name || "") || ["sql", "hybrid", "shape", "gated"].includes(run.channel)));
  const compositeTiming = (run) => Boolean(run && (sqliteRun(run) ? /stage.only|stage.sum|separate|projection|not end.to.end|sum of|合计|分阶段|估算/i.test(run.config?.timing || "") : /cached baseline|not end.to.end|model load excluded/i.test(run.config?.timing || "") || ["reranked", "ensemble"].includes(run.channel)));
  const compositeTimingNote = "原管线耗时 + 视觉核验耗时；分别计时，未含模型加载。";
  const timingNote = (run) => {
    if (sqliteRun(run)) {
      const timing = run.config?.timing || "";
      if (/gate projection/i.test(timing)) return "门控阶段估算：完整批次实际调用了视觉模型；此行按门控规则选取所需阶段的耗时合计，未实测端到端，未含模型加载。";
      if (/separately measured new.pool VLM/i.test(timing)) return "本次 OCR、数据库与形状阶段 + 单独测量的新候选视觉生成和准备耗时；未实测端到端，未含模型加载。";
      if (/measured fresh.*OCR.*SQLite.*shape stages/i.test(timing)) return "重新实测 OCR、SQLite、图像检索与形状阶段；先做一张不计时预热，未含模型加载。SQL-only 的召回指标仍仅统计数据库候选。";
      return timing || "以保存的阶段计时为准。";
    }
    return run?.channel === "ensemble" ? "冻结输出离线重放；各完整分支耗时串行合计估算，未实测端到端，未含模型加载。" : compositeTimingNote;
  };
  const timingScopeLabel = (run) => sqliteRun(run) && /projection|估算/i.test(run?.config?.timing || "") ? "门控估算" : run?.channel === "ensemble" ? "串行估算" : "分阶段合计";
  const metricTimingNote = (run) => sqliteRun(run) ? /gate projection/i.test(run.config?.timing || "") ? "门控所需阶段的合计估算；完整批次实际运行了 VLM。" : compositeTiming(run) ? "含单独计时的 VLM 阶段；非端到端，不含模型加载。" : "重新实测各阶段；预热后计时，不含模型加载。" : timingNote(run);
  const candidateOrigins = (record, id) => {
    if (activeChannel() === "sql" && record?.retrieval?.candidates?.some((item) => item.part_id === id)) return ["sqlite"];
    const poolItem = record?.retrieval?.pool?.find((item) => item.part_id === id);
    return Array.isArray(poolItem?.origins) ? poolItem.origins : [];
  };
  const originText = (origins) => origins.map((origin) => ({ sqlite: "SQLite 召回", appearance: "图像补充" })[origin] || String(origin)).join(" + ");
  const sqlCandidate = (record, id) => record?.retrieval?.candidates?.find((item) => item.part_id === id);
  const matchText = (match) => {
    const term = match.term || match.text || "";
    const field = fieldNames[match.field] || match.field || "目录";
    const kind = matchKinds[match.kind] || match.kind || "匹配";
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
    show("app-error", false);
    $("workbench").setAttribute("aria-busy", "true");
    announce("正在读取实验记录");
    try {
      const response = await fetch("/api/data", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || `读取失败（HTTP ${response.status}）`);
      if (!Array.isArray(data.runs) || !Array.isArray(data.samples) || !data.catalog) throw new Error("服务未返回完整的实验数据。");
      state.data = data;
      state.baseline = data.runs.find((run) => run.name === "easyocr_whole") || data.runs.find((run) => run.config?.baseline || /baseline|基线/i.test(`${run.name} ${run.label || ""}`)) || data.runs[0] || null;
      state.run = data.runs.find((run) => run.name === state.run?.name) || data.runs.filter(complete).reduce((best, run) => !best || (rate(run.summary, "top1") || 0) > (rate(best.summary, "top1") || 0) ? run : best, null) || state.baseline;
      if (!data.samples.some((item) => item.file === state.file)) state.file = data.samples[0]?.file || null;
      renderRunPicker();
      renderSamplePicker();
      renderAll();
      announce(`已读取 ${data.samples.length} 张实验照片与 ${data.runs.length} 个实测运行。`);
    } catch (error) {
      text("app-error-text", error.message || "请检查本地服务是否正常运行。");
      show("app-error", true);
      text("image-placeholder-title", "实验记录暂不可用");
      text("image-placeholder-description", "请重新读取，或检查本地服务");
      text("experiments-body", "");
      const row = node("tr"); const cell = node("td", "table-empty", "实验记录暂不可用"); cell.colSpan = 8; row.append(cell); $("experiments-body").append(row);
      announce("实验记录读取失败。");
    } finally {
      state.loadingData = false;
      $("workbench").setAttribute("aria-busy", "false");
    }
  }

  function renderRunPicker() {
    const select = $("run-select");
    select.replaceChildren();
    for (const run of state.data?.runs || []) {
      const option = node("option", "", `${runLabel(run)}${complete(run) ? "" : " · 未完成"}`);
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
      const option = node("option", "", `${String(index + 1).padStart(2, "0")} · ${item.gt || "样本"} · ${basename(item.file)}`);
      option.value = item.file;
      select.append(option);
    }
    if (!items.length) select.append(node("option", "", "没有符合条件的样本"));
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
    text("baseline-detail", baseline ? `${count(baseline, "top1")} 正确 · ${runLabel(state.baseline)}` : "暂无基线记录");
    const baselineExample = complete(state.baseline) && count(baseline, "top1") ? `本次为 ${count(baseline, "top1")} = ${percent(rate(baseline, "top1"))}。` : "";
    text("baseline-explanation", `基线是最初的 EasyOCR 方案。Top-1 是第一候选正确的比例。${baselineExample}这不是单张图片的置信度。`);
    const classes = Object.keys(state.data?.catalog || {}).length;
    text("scope-count", `${state.data?.samples?.length || 0} 张照片 / ${classes} 类`);
    const composite = state.mode === "preset" && compositeTiming(state.run);
    const showScope = state.mode === "preset" && (composite || sqliteRun(state.run));
    show("latency-scope-note", showScope);
    text("latency-scope-note", showScope ? metricTimingNote(state.run) : "");
    if (state.mode === "live") {
      text("selected-metric-label", "当前输入");
      text("selected-score", state.live.record ? "单张识别" : "待识别");
      text("selected-detail", "上传图片没有评估标签");
      text("latency-metric-label", "本次服务端计时");
      text("latency-score", duration(state.live.record?.ms?.total));
      text("latency-detail", state.live.loading ? "正在加载或推理…" : `当前图片 · ${state.live.pipeline === "sqlite" ? "SQLite + 形状" : "原多路检索"}${state.live.record?.vlm ? " + 视觉核验" : ""}`);
    } else {
      const summary = state.run?.summary;
      text("selected-metric-label", "当前实验 Top-1");
      text("selected-score", complete(state.run) ? percent(rate(summary, "top1")) : "未完成");
      text("selected-detail", summary ? `${count(summary, "top1")} 正确 · ${runLabel(state.run)}` : "暂无实验记录");
      text("latency-metric-label", composite ? `${timingScopeLabel(state.run)} · p50` : sqliteRun(state.run) ? "记录耗时 · p50" : "当前实验延迟 · p50");
      text("latency-score", complete(state.run) ? duration(summary?.latency_ms?.p50) : "—");
      text("latency-detail", complete(state.run) ? `p95 ${duration(summary?.latency_ms?.p95)}${composite || sqliteRun(state.run) ? "" : " · 预热后单图测量"}` : "运行未完成，不参与性能对照");
    }
    text("evaluation-note-text", `${state.data?.samples?.length || 0} 张照片、${classes} 类的开发评估。标签由模型生成，复核意见未经元件专家确认。完整运行可比较；未完成运行仅显示覆盖数。`);
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
    text("input-mode-tag", live ? "实时 OCR" : "实验回放");
    $("input-mode-tag").className = `tag ${live ? "tag-teal" : ""}`;
    text("evidence-mode-tag", live ? state.live.loading ? "运行中" : "实时" : "已保存");
    text("live-engine-name", `${state.live.engine === "rapidocr" ? "RapidOCR" : "EasyOCR"}${state.live.multiview ? " · 多视图" : " · 完整图像"}`);
    text("live-result-description", `当前上传图片 · ${state.live.pipeline === "sqlite" ? "SQLite 关键词 + 形状" : "原多路检索"}${state.live.record?.vlm ? " + 本地视觉核验" : ""}`);
    $("predict-button").disabled = !state.live.image || state.live.loading;
    $("pipeline-select").disabled = state.live.loading;
    $("engine-select").disabled = state.live.loading;
    $("multiview-input").disabled = state.live.loading;
    $("verify-visual-input").disabled = state.live.loading || $("pipeline-select").value !== "sqlite";
    show("verify-visual-note", $("pipeline-select").value !== "sqlite");
    $("verify-visual-input").closest("label").classList.toggle("is-disabled", $("pipeline-select").value !== "sqlite");
    text("live-pipeline-note", $("pipeline-select").value === "sqlite" ? `实时执行 OCR、SQLite 关键词召回与形状重排。${$("verify-visual-input").checked ? "证据不足时另运行本地视觉核验，首次加载模型可能较慢。" : "首次加载模型可能较慢。"}` : "实时执行原有 OCR 与多路检索。首次加载模型可能较慢。");
    $("upload-input").disabled = state.live.loading;
    text("predict-label", state.live.loading ? "正在识别…" : state.live.record ? "重新识别" : "开始识别");
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
      text("image-placeholder-title", "图片暂时无法显示"); text("image-placeholder-description", "可继续查看文字和候选记录");
    };
    show("query-image", Boolean(source));
    show("image-placeholder", !source);
    if (source && img.getAttribute("src") !== source) {
      text("image-dimensions", "");
      img.src = source;
    }
    if (!source) {
      img.removeAttribute("src");
      text("image-placeholder-title", live ? "上传一张元件照片" : "没有可显示的样本");
      text("image-placeholder-description", live ? "清晰的芯片丝印有助于提供型号线索" : "请选择其他样本范围");
      text("image-dimensions", "");
    }
    img.alt = live ? "上传的待识别电子元件照片" : `实验样本：${partName(item?.gt)}，评估标签 ${item?.gt || "未知"}`;
    $("view-evidence").disabled = !view || Boolean(liveView?.error);
    $("view-original").setAttribute("aria-pressed", String(!evidence));
    $("view-evidence").setAttribute("aria-pressed", String(evidence));
    const boxes = Array.isArray(view?.boxes) ? view.boxes : [];
    text("box-count", liveView?.pending ? "正在准备 OCR 视图" : liveView?.error ? "OCR 视图暂不可用" : view ? `${boxes.length} 个文字框` : record ? "此记录未保存文字框" : live ? "识别后显示文字框" : "等待记录");
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
        title.textContent = `${index + 1}. ${box.text || "文字框"}`; polygon.append(title); overlay.append(polygon);
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        label.setAttribute("x", String(points[0][0] + 2)); label.setAttribute("y", String(Math.max(14, points[0][1] - 6)));
        label.setAttribute("font-size", String(Math.max(12, Math.min(width, height) / 42)));
        label.setAttribute("class", "ocr-box-label"); label.textContent = String(index + 1); overlay.append(label);
      }
    }
    show("image-view-label", Boolean(source));
    text("image-view-label", evidence ? `OCR · ${viewDescription(view)}` : "ORIGINAL · 原始照片");
    text("image-filename", live ? state.live.filename || "上传图片" : basename(item?.file) || "—");
    const link = !live && safeLink(item?.page_url);
    show("source-link", Boolean(link)); if (link) $("source-link").href = link;
    const attribution = live ? "" : [item?.artist, item?.license].filter(Boolean).map((value) => String(value).replace(/<[^>]*>/g, "")).join(" · ");
    text("image-attribution", attribution); show("image-attribution", Boolean(attribution));
  }

  function renderEvidence(record) {
    const live = state.mode === "live";
    const view = selectedView(record);
    const observed = record?.ocr_text || record?.evidence?.text || "";
    text("ocr-text", observed || (record ? "未检测到可读文字" : live ? state.live.loading ? "正在读取图片中的文字…" : "上传图片并开始识别" : "当前实验没有该样本的记录"));
    $("ocr-text").classList.toggle("is-empty", !observed);
    text("ocr-view-detail", view ? `所选视图：${viewDescription(view)} · 框分数为引擎原始值，未校准` : record ? "此记录只有文字输出，没有视图几何记录。" : "");
    text("run-status", state.run ? complete(state.run) ? `${state.run.channel === "ensemble" ? "固定输出组合重放" : "完整运行"} · ${state.run.summary?.n || 0} 张 · 实验回放` : `未完成 · 已覆盖 ${state.run.summary?.n || 0} / ${state.data?.samples?.length || 0} 张，不参与性能对照` : "暂无实验记录");
    $("run-status").classList.toggle("is-partial", Boolean(state.run && !complete(state.run)));
    const hits = $("identifier-hits"); hits.replaceChildren();
    const idHits = Array.isArray(record?.id_hits) ? record.id_hits : [];
    for (const hit of idHits.slice(0, 4)) {
      const pid = Array.isArray(hit) ? hit[0] : hit.id || hit.pid || hit.part_id;
      const alias = Array.isArray(hit) ? hit[2] : hit.alias;
      const row = node("div", "identifier-hit"); row.append(node("code", "", alias || pid), node("span", "", pid)); hits.append(row);
    }
    if (!idHits.length) hits.append(node("p", "empty-note", record ? "未命中目录中的明确型号，继续使用文字与图像检索。" : "识别后显示型号命中依据"));
    const conflicts = record?.evidence?.conflicts;
    const conflictText = valueText(conflicts);
    const hasConflicts = Array.isArray(conflicts) ? conflicts.length > 0 : Boolean(conflicts && conflictText && conflictText !== "false");
    show("evidence-conflicts", hasConflicts);
    text("evidence-conflicts", hasConflicts ? `视图线索存在冲突：${conflictText}` : "");
    const combined = !live && record?.ensemble;
    show("ensemble-section", Boolean(combined));
    if (combined) {
      text("ensemble-status", combined.vlm_called ? "规则调用 VLM" : "OCR 直接接受");
      text("ensemble-reason", combined.reason || "");
      const votes = $("ensemble-votes"); votes.replaceChildren();
      for (const vote of combined.votes || []) {
        const expert = state.data.runs.find((run) => run.name === vote.expert);
        const row = node("div", "identifier-hit");
        row.append(node("span", "", runLabel(expert || {name: vote.expert})), node("code", "", vote.candidate || "弃权"));
        votes.append(row);
      }
    }
    const vlm = record?.vlm;
    show("vlm-section", Boolean(vlm));
    if (vlm) {
      const abstained = Boolean(vlm.abstained);
      text("vlm-status", abstained ? combined ? "弃权 · 未投票" : "保留原序" : vlm.selected_id || "已判断");
      $("vlm-status").className = `tag ${abstained ? "tag-warning" : "tag-teal"}`;
      text("vlm-reason", vlm.reason || (abstained ? "模型未给出可采纳的选择，保留原始候选顺序。" : "未保存判断说明。"));
      text("vlm-observed", vlm.observed_text ? `可见文字：${valueText(vlm.observed_text)}` : "");
      show("vlm-observed", Boolean(vlm.observed_text));
      text("vlm-scope-note", live ? "本次实时核验 · 仅使用本次生成的候选；本地模型首次加载可能较慢。" : combined ? "固定输出组合重放 · 此处为已保存的视觉分支判断。" : record?.retrieval ? "已保存实测 · 在本次 SQLite 与图像补充候选中判断。" : "已保存实测 · 在冻结的 Top-10 候选中判断。");
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
    text("sql-match-count", `${candidates.length} SQL 候选`);
    const keywordList = $("keyword-list"); keywordList.replaceChildren();
    for (const keyword of keywords) {
      const chip = node("span", `keyword-chip${/noise|batch/.test(keyword.kind || "") ? " is-noise" : ""}`);
      chip.append(node("code", "", keyword.text || keyword.normalized || ""), node("small", "", keywordKinds[keyword.kind] || keyword.kind || "文字线索"));
      if (keyword.normalized && keyword.normalized !== keyword.text) chip.title = `归一化：${keyword.normalized}`;
      keywordList.append(chip);
    }
    if (!keywords.length) keywordList.append(node("p", "empty-note", "没有可用于数据库检索的 OCR 关键词。"));
    const strong = Array.isArray(retrieval.strong_ids) ? retrieval.strong_ids : [];
    const supplemental = pool.filter((item) => Array.isArray(item.origins) && item.origins.includes("appearance")).length;
    text("retrieval-summary", `数据库召回 ${candidates.length} 个候选${pool.length ? `，完整流程合并池 ${pool.length} 个` : ""}${supplemental ? `，其中 ${supplemental} 个带图像补充依据` : ""}。${strong.length ? `强型号线索：${strong.join("、")}。` : "未形成强型号线索。"}${activeChannel() === "sql" ? "本阶段只使用 SQL 排序；图像与形状用于后续阶段对照。" : retrieval.fallback_used ? "已使用图像补充候选；这些命中不计为 SQL 召回。" : ""}`);
    const matches = $("sql-matches"); matches.replaceChildren();
    for (const [index, candidate] of candidates.entries()) {
      const receipt = node("div", "sql-receipt");
      const heading = node("div", "sql-receipt-heading");
      heading.append(node("strong", "", `${index + 1}. ${candidate.part_id}`));
      if (candidate.tier) heading.append(node("span", "", matchKinds[candidate.tier] || candidate.tier));
      receipt.append(heading);
      const entries = Array.isArray(candidate.matches) ? candidate.matches : [];
      for (const match of entries) receipt.append(node("p", "", matchText(match)));
      if (!entries.length) receipt.append(node("p", "empty-note", "未保存逐关键词命中说明。"));
      matches.append(receipt);
    }
    if (!candidates.length) matches.append(node("p", "empty-note", "数据库没有返回候选；图像补充的结果会单独标注。"));
  }

  function renderShape(record) {
    const shape = record?.shape;
    show("shape-section", Boolean(shape));
    if (!shape) return;
    const query = shape.query || {};
    text("shape-status", query.available ? "可用 · 启发式" : "不可用");
    $("shape-status").className = `tag ${query.available ? "tag-teal" : "tag-neutral"}`;
    const features = $("shape-features"); features.replaceChildren();
    const featureNames = { elongation: "长短轴比", solidity: "轮廓实心度", circularity: "圆度" };
    if (query.available) {
      for (const [key, label] of Object.entries(featureNames)) {
        const value = number(query.features?.[key]);
        if (value != null) features.append(node("dt", "", label), node("dd", "", value.toFixed(3)));
      }
      if (!features.childElementCount) features.append(node("dt", "", "特征"), node("dd", "", "未保存数值"));
    }
    show("shape-features", features.childElementCount > 0);
    const notes = valueText(query.quality_notes);
    text("shape-quality", [query.method ? `方法：${query.method}` : "", notes, !query.available ? "本次没有可用的形状估计，不提供形状分数。" : "由照片前景轮廓估计，受遮挡、背景与拍摄角度影响。", ["sql", "hybrid"].includes(activeChannel()) ? "本阶段仅展示对照，形状特征未参与排序。" : ""].filter(Boolean).join("；"));
  }

  function renderSelectedEvidence(record) {
    const id = rankings(record)[0];
    const visible = Boolean(record?.retrieval && id);
    show("selected-evidence-section", visible);
    if (!visible) return;
    text("selected-candidate-name", `${partName(id)} · ${id}`);
    const content = $("selected-candidate-evidence"); content.replaceChildren();
    const origins = candidateOrigins(record, id);
    content.append(node("p", "", origins.length ? `候选来源：${originText(origins)}` : "候选来源：未保存"));
    const candidate = sqlCandidate(record, id);
    const entries = Array.isArray(candidate?.matches) ? candidate.matches : [];
    for (const match of entries) content.append(node("p", "", matchText(match)));
    if (!candidate) content.append(node("p", "", "该候选未出现在 SQL 召回结果中。"));
    else if (!entries.length) content.append(node("p", "", "该候选未保存逐关键词命中说明。"));
    const shapeScore = number(record?.shape?.reference_scores?.[id]);
    content.append(node("p", "", shapeScore == null ? "形状：没有可用的查询图与参考图对比" : `参考图形状相似度：${shapeScore.toFixed(3)}（非概率${["sql", "hybrid"].includes(activeChannel()) ? "，本阶段未参与排序" : ""}）`));
    const decision = record.decision;
    show("candidate-decision", Boolean(decision));
    text("candidate-decision", decision ? `${decision.used_vlm ? "已使用视觉核验" : decision.accepted_sql_id ? `保留强 SQL 型号 ${decision.accepted_sql_id}` : "未使用视觉核验"}${decision.reason ? `：${decision.reason}` : ""}` : "");
  }

  function renderCandidates(record) {
    const list = $("candidate-list"); list.replaceChildren();
    const ids = rankings(record).slice(0, 3);
    if (!ids.length) {
      list.append(node("p", "empty-note", state.live.loading && state.mode === "live" ? "正在生成候选…" : record ? "本次记录没有返回候选元件。" : "识别记录就绪后显示前三候选及参考图。"));
      return;
    }
    for (const [index, id] of ids.entries()) {
      const part = catalog()[id] || {};
      const card = node("article", `candidate-card${index === 0 ? " is-first" : ""}`);
      const imageWrap = node("div", "candidate-image-wrap"); imageWrap.append(node("span", "candidate-rank", `0${index + 1}`));
      if (part.catalog_file) {
        const img = node("img"); img.alt = `${part.name || id} 的目录参考照片`; img.loading = "lazy"; img.src = imageURL(part.catalog_file);
        img.onerror = () => { img.hidden = true; imageWrap.append(node("span", "image-unavailable", "参考图暂不可用")); };
        imageWrap.append(img);
      } else imageWrap.append(node("span", "image-unavailable", "暂无参考图"));
      const info = node("div", "candidate-info"); const heading = node("h4");
      const url = safeLink(part.page_url);
      if (url) { const a = node("a", "", part.name || id); a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.title = "查看元件资料来源"; heading.append(a); }
      else heading.textContent = part.name || id;
      info.append(heading, node("code", "", id));
      const evidence = node("div", "candidate-evidence");
      const hit = record?.id_hits?.find((entry) => (Array.isArray(entry) ? entry[0] : entry.id || entry.pid || entry.part_id) === id);
      if (hit) { const tag = node("span", "identifier-tag", "型号命中"); tag.title = `命中别名：${Array.isArray(hit) ? hit[2] || id : hit.alias || id}`; evidence.append(tag); }
      for (const [channel, label] of [["text", "文字"], ["image", "图像"]]) {
        const rank = record?.rankings?.[channel]?.indexOf(id);
        if (rank != null && rank >= 0 && rank < 3) evidence.append(node("span", "", `${label} #${rank + 1}`));
      }
      for (const origin of candidateOrigins(record, id)) evidence.append(node("span", origin === "sqlite" ? "identifier-tag" : "", originText([origin])));
      if (record?.retrieval?.strong_ids?.includes(id)) evidence.append(node("span", "identifier-tag", "强型号线索"));
      const shapeRank = record?.shape?.ranked_ids?.indexOf(id);
      const shapeScore = number(record?.shape?.reference_scores?.[id]);
      if (!["sql", "hybrid"].includes(activeChannel()) && shapeScore != null && shapeRank != null && shapeRank >= 0 && shapeRank < 3) evidence.append(node("span", "", `形状阶段 #${shapeRank + 1}`));
      if (!evidence.childElementCount) evidence.append(node("span", "", state.mode !== "live" && state.run?.channel === "reranked" ? "重排候选" : "融合候选"));
      if (state.mode === "preset" && sample()?.gt === id) evidence.append(node("span", "truth-tag", "评估标签"));
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
    for (const [key, value] of times) content.append(node("dt", "", key === "total" && composite ? timingScopeLabel(state.run) : labels[key] || key), node("dd", "", duration(value)));
    const scope = state.mode === "live" ? state.live.timing ? /measured live end.to.end/i.test(state.live.timing) ? "本次实时端到端计时，包含本次请求所需的视觉进程与模型加载；强且无冲突的 SQL 线索可跳过视觉调用。" : state.live.timing : "" : composite || sqliteRun(state.run) ? timingNote(state.run) : "";
    show("timing-scope-note", Boolean(scope));
    text("timing-scope-note", scope);
  }

  function setMatchStatus(id, candidate, gt, hasRecord) {
    const el = $(id);
    const correct = Boolean(candidate && gt && candidate === gt);
    el.className = `result-status ${hasRecord && gt ? correct ? "is-correct" : "is-wrong" : ""}`;
    el.textContent = !hasRecord ? "暂无记录" : !candidate ? gt ? "未检索到候选 · 与评估标签不符" : "未检索到候选" : correct ? "✓ 与评估标签一致" : "与评估标签不同";
  }

  function renderSampleComparison(record) {
    const item = sample();
    text("ground-truth-name", item ? partName(item.gt, state.data.catalog) : "—");
    text("ground-truth-id", item?.gt || "");
    const baseRecord = recordFor(state.baseline);
    const base = baseRecord?.rankings?.fused?.[0];
    const current = rankings(record)[0];
    text("comparison-baseline-name", base ? partName(base, state.data?.catalog) : baseRecord ? "未检索到候选" : "—");
    text("comparison-current-name", current ? partName(current, state.data?.catalog) : record ? "未检索到候选" : "—");
    text("comparison-current-label", state.run?.channel === "ensemble" ? "组合 Top-1" : state.run?.channel === "gated" ? "门控方案 Top-1" : state.run?.channel === "reranked" ? "视觉重排 Top-1" : "当前实验 Top-1");
    setMatchStatus("comparison-baseline-status", base, item?.gt, Boolean(baseRecord));
    setMatchStatus("comparison-current-status", current, item?.gt, Boolean(record));
    let label = "等待记录"; let className = "tag tag-neutral";
    if (baseRecord && record) {
      if (!base && !current) label = "均未检索到候选";
      else if (base === current) label = "Top-1 未变";
      else if (item?.gt && current === item.gt && base !== item.gt) { label = "改善"; className = "tag tag-teal"; }
      else if (item?.gt && base === item.gt && current !== item.gt) { label = "退化"; className = "tag tag-warning"; }
      else label = "候选变化";
    }
    text("comparison-change", label); $("comparison-change").className = className;
    const review = state.mode === "preset" && item?.review;
    show("review-details", Boolean(review));
    const content = $("review-content"); content.replaceChildren();
    if (review) {
      const dl = node("dl");
      for (const [key, label] of [["observed_text", "照片中可见文字"], ["observed_part_number", "可能的元件型号"], ["legibility", "可读性"], ["label_comparison", "与评估标签比较"], ["quality_issues", "图像与证据问题"], ["suggested_action", "建议检查"]]) {
        const value = valueText(review[key]);
        if (value) { const row = node("div"); row.append(node("dt", "", label), node("dd", "", value)); dl.append(row); }
      }
      if (!dl.childElementCount) dl.append(node("dd", "", valueText(review)));
      content.append(dl, node("p", "review-provenance", "此笔记为模型辅助复核，可能受已有标签影响；未作为新的专家金标准或推理输入。"));
    }
  }

  function renderExperiments() {
    const tbody = $("experiments-body"); tbody.replaceChildren();
    for (const run of state.data?.runs || []) {
      const row = node("tr", `${state.mode === "preset" && state.run?.name === run.name ? "is-selected " : ""}${complete(run) ? "" : "is-partial"}`);
      const nameCell = node("td"); const nameWrap = node("div", "run-table-name");
      const button = node("button", "run-table-button", runLabel(run)); button.type = "button";
      button.setAttribute("aria-label", `查看 ${runLabel(run)} 的实验回放`);
      if (state.mode === "preset" && state.run?.name === run.name) button.setAttribute("aria-current", "true");
      button.addEventListener("click", () => selectRun(run.name));
      nameWrap.append(button);
      if (run.name === state.baseline?.name) nameWrap.append(node("span", "tag tag-neutral", "基线"));
      if (run.channel === "ensemble") nameWrap.append(node("span", "tag tag-neutral", `组合重放 · VLM ${run.summary?.vlm_calls ?? "—"}/${run.summary?.n || 0}`));
      if (sqliteRun(run) && ["reranked", "gated"].includes(run.channel) && finite(run.summary?.vlm_calls)) nameWrap.append(node("span", "tag tag-neutral", `VLM ${run.summary.vlm_calls}/${run.summary?.n || 0}`));
      if (!complete(run)) nameWrap.append(node("span", "tag tag-warning", "未完成"));
      nameCell.append(nameWrap); row.append(nameCell, node("td", "table-count", `${run.summary?.n || 0} / ${state.data?.samples?.length || 0}`));
      if (!complete(run)) {
        const cell = node("td", "partial-caption", "未纳入性能对照"); cell.colSpan = 6; row.append(cell);
      } else {
        for (const metric of ["top1", "top3", "recall5", "recall10"]) {
          const cell = node("td", "", percent(rate(run.summary, metric))); const values = count(run.summary, metric); if (values) cell.title = values; row.append(cell);
        }
        const latency = node("td", "", `${duration(run.summary?.latency_ms?.p50)} / ${duration(run.summary?.latency_ms?.p95)}`);
        if (compositeTiming(run) || sqliteRun(run)) {
          const scope = node("span", "table-time-scope", compositeTiming(run) ? timingScopeLabel(run) : "阶段记录");
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
    if (!tbody.childElementCount) { const row = node("tr"); const cell = node("td", "table-empty", "暂无实测运行。"); cell.colSpan = 8; row.append(cell); tbody.append(row); }
    const hasComposite = state.data?.runs.some(compositeTiming);
    const warmup = state.data?.runs.some((run) => /warmup/i.test(run.config?.timing || ""));
    const sqliteTiming = [...new Set((state.data?.runs || []).filter(sqliteRun).map(timingNote))];
    show("table-timing-note", hasComposite || warmup || sqliteTiming.length > 0);
    const hasEnsemble = state.data?.runs.some((run) => run.channel === "ensemble");
    const hasOldVLM = state.data?.runs.some((run) => !sqliteRun(run) && run.channel === "reranked");
    text("table-timing-note", [warmup ? "OCR 为预热后的单图测量，与原始整批二次运行的计时方法不同。" : "", hasOldVLM ? `原视觉重排：${compositeTimingNote}` : "", hasEnsemble ? "原组合策略为固定输出离线重放；时间为所需完整分支串行合计估算，未实测端到端。" : "", ...sqliteTiming.map((note) => `SQLite 流程：${note}`)].filter(Boolean).join(" "));
  }

  function renderAll() {
    renderMode(); renderMetrics();
    const record = currentRecord();
    renderImage(record); renderEvidence(record); renderSampleComparison(record); renderExperiments();
  }

  function selectRun(name) {
    state.run = state.data?.runs.find((run) => run.name === name) || state.run;
    state.mode = "preset"; $("run-select").value = state.run?.name || "";
    renderAll(); announce(`已切换到 ${runLabel(state.run)}，显示已保存的实验记录。`);
  }

  function navigateSample(step) {
    if (state.mode !== "preset") return;
    const items = filteredSamples(); const index = items.findIndex((item) => item.file === state.file);
    if (index + step < 0 || index + step >= items.length) return;
    state.file = items[index + step].file; renderSamplePicker(); renderAll();
    announce(`样本 ${index + step + 1} / ${items.length}，评估标签 ${partName(sample()?.gt)}。`);
  }

  function setMode(mode) {
    state.mode = mode; renderAll();
    announce(mode === "live" ? "实时 OCR 模式。上传图片后点击开始识别。" : "实验回放模式。显示已保存的推理记录。");
  }

  async function readUpload(file) {
    if (!file || state.live.loading) return;
    show("upload-error", false);
    if (file.size > 10 * 1024 * 1024) { uploadError("图片超过 10 MB，请选择较小的图片。"); return; }
    if (!(file.type.startsWith("image/") || /\.(jpe?g|png|webp|bmp|gif|tiff?)$/i.test(file.name))) { uploadError("请选择有效的图片文件。"); return; }
    try {
      const dataURL = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error("图片文件无法读取，请重新选择。")); reader.readAsDataURL(file);
      });
      state.live.image = dataURL; state.live.filename = file.name; state.live.record = null; state.live.catalog = null; state.live.channel = "shape"; state.live.timing = ""; state.live.viewCache = new Map(); state.mode = "live";
      text("upload-file-name", `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`);
      renderAll(); announce(`已选择 ${file.name}，点击开始识别以运行本地 OCR。`);
    } catch (error) { uploadError(error.message); }
  }

  function uploadError(message) { text("upload-error", message); show("upload-error", true); announce(message); }

  async function predict() {
    if (!state.live.image || state.live.loading) return;
    state.live.engine = $("engine-select").value; state.live.multiview = $("multiview-input").checked;
    state.live.pipeline = $("pipeline-select").value; state.live.verifyVisual = state.live.pipeline === "sqlite" && $("verify-visual-input").checked;
    state.live.channel = state.live.pipeline === "sqlite" ? state.live.verifyVisual ? "gated" : "shape" : "fused";
    state.live.loading = true; state.live.record = null; state.live.timing = ""; show("upload-error", false); renderAll();
    announce(`正在本地运行 OCR 与检索${state.live.verifyVisual ? "及按需视觉核验" : ""}。首次加载模型可能较慢。`);
    try {
      const response = await fetch("/api/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image: state.live.image, engine: state.live.engine, multiview: state.live.multiview, pipeline: state.live.pipeline, verify_visual: state.live.verifyVisual }) });
      const result = await response.json();
      if (!response.ok || result.error) throw new Error(result.error || `识别失败（HTTP ${response.status}）`);
      if (!result.record) throw new Error("服务没有返回识别结果。");
      state.live.record = result.record; state.live.catalog = result.catalog || state.data?.catalog || {};
      state.live.channel = result.channel || "fused"; state.live.timing = result.timing || "";
      announce(`识别完成。第一候选：${partName(rankings(result.record)[0], state.live.catalog)}。`);
    } catch (error) { uploadError(error.message || "本地识别失败，请重试。"); }
    finally { state.live.loading = false; renderAll(); }
  }

  $("retry-data").addEventListener("click", loadData);
  $("mode-preset").addEventListener("click", () => setMode("preset"));
  $("mode-live").addEventListener("click", () => setMode("live"));
  $("run-select").addEventListener("change", (event) => selectRun(event.target.value));
  $("sample-select").addEventListener("change", (event) => { state.file = event.target.value; renderSamplePicker(); renderAll(); announce(`已选择样本 ${basename(state.file)}。`); });
  $("previous-sample").addEventListener("click", () => navigateSample(-1));
  $("next-sample").addEventListener("click", () => navigateSample(1));
  for (const [id, filter] of [["filter-all", "all"], ["filter-errors", "errors"]]) $(id).addEventListener("click", () => { state.filter = filter; renderSamplePicker(); renderAll(); announce(`显示${filter === "all" ? "全部样本" : "基线错误样本"}，共 ${filteredSamples().length} 张。`); });
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
  loadData();
})();
