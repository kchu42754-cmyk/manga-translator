const state = {
  files: [],
  activeIndex: -1,
  crop: null,
  currentJobId: null,
  pollHandle: null,
  imageCache: new Map(),
  drawState: {
    dragging: false,
    startX: 0,
    startY: 0,
  },
  canvasFit: null,
};

const elements = {
  statusOnline: document.getElementById("statusOnline"),
  statusModel: document.getElementById("statusModel"),
  statusEndpoint: document.getElementById("statusEndpoint"),
  modelPreset: document.getElementById("modelPreset"),
  refreshStatusBtn: document.getElementById("refreshStatusBtn"),
  quickStartBtn: document.getElementById("quickStartBtn"),
  start7bBtn: document.getElementById("start7bBtn"),
  start30bBtn: document.getElementById("start30bBtn"),
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("fileInput"),
  folderInput: document.getElementById("folderInput"),
  clearFilesBtn: document.getElementById("clearFilesBtn"),
  gallery: document.getElementById("gallery"),
  cropCanvas: document.getElementById("cropCanvas"),
  cropInfo: document.getElementById("cropInfo"),
  activeInfo: document.getElementById("activeInfo"),
  resetCropBtn: document.getElementById("resetCropBtn"),
  saveCropBtn: document.getElementById("saveCropBtn"),
  loadCropBtn: document.getElementById("loadCropBtn"),
  autoStartToggle: document.getElementById("autoStartToggle"),
  applyCropAllToggle: document.getElementById("applyCropAllToggle"),
  translateBtn: document.getElementById("translateBtn"),
  progressFill: document.getElementById("progressFill"),
  progressText: document.getElementById("progressText"),
  logBox: document.getElementById("logBox"),
  downloads: document.getElementById("downloads"),
  results: document.getElementById("results"),
};

const canvasContext = elements.cropCanvas.getContext("2d");
const savedCropKey = "manga-hub-crop";

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fileSortKey(entry) {
  return entry.displayName;
}

function sortFiles(files) {
  return [...files].sort((a, b) =>
    fileSortKey(a).localeCompare(fileSortKey(b), undefined, {
      numeric: true,
      sensitivity: "base",
    }),
  );
}

function setLog(message) {
  elements.logBox.textContent = message;
}

function addFiles(fileList) {
  const additions = [];
  for (const file of Array.from(fileList)) {
    if (!file.type.startsWith("image/")) {
      continue;
    }
    additions.push({
      id: crypto.randomUUID(),
      file,
      displayName: file.webkitRelativePath || file.name || `image-${Date.now()}.png`,
      previewUrl: URL.createObjectURL(file),
    });
  }
  if (!additions.length) {
    return;
  }
  state.files = sortFiles([...state.files, ...additions]);
  if (state.activeIndex === -1) {
    state.activeIndex = 0;
  } else {
    state.activeIndex = Math.min(state.activeIndex, state.files.length - 1);
  }
  renderGallery();
  drawActiveImage();
  setLog(`已载入 ${state.files.length} 张图片。`);
}

function clearFiles() {
  state.files.forEach((entry) => URL.revokeObjectURL(entry.previewUrl));
  state.files = [];
  state.activeIndex = -1;
  state.crop = null;
  state.imageCache.clear();
  renderGallery();
  drawEmptyCanvas();
  renderCropInfo();
  setLog("等待上传图片。");
  elements.results.innerHTML = '<div class="muted">把图片拖进来后，结果会出现在这里。</div>';
  elements.downloads.innerHTML = "";
  elements.progressFill.style.width = "0%";
  elements.progressText.textContent = "还没有开始任务。";
}

function renderGallery() {
  if (!state.files.length) {
    elements.gallery.innerHTML = '<div class="muted">当前还没有图片。</div>';
    return;
  }
  elements.gallery.innerHTML = state.files
    .map(
      (entry, index) => `
        <div class="thumb ${index === state.activeIndex ? "active" : ""}" data-index="${index}">
          <button class="thumb-remove" type="button" data-remove="${index}">×</button>
          <img src="${entry.previewUrl}" alt="${escapeHtml(entry.displayName)}">
          <div class="thumb-caption">${escapeHtml(entry.displayName)}</div>
        </div>
      `,
    )
    .join("");
}

function getActiveFile() {
  if (state.activeIndex < 0 || state.activeIndex >= state.files.length) {
    return null;
  }
  return state.files[state.activeIndex];
}

async function loadImage(entry) {
  if (!entry) {
    return null;
  }
  if (state.imageCache.has(entry.id)) {
    return state.imageCache.get(entry.id);
  }
  const image = new Image();
  image.src = entry.previewUrl;
  await image.decode();
  state.imageCache.set(entry.id, image);
  return image;
}

function drawEmptyCanvas() {
  canvasContext.clearRect(0, 0, elements.cropCanvas.width, elements.cropCanvas.height);
  canvasContext.fillStyle = "rgba(35, 25, 18, 0.05)";
  canvasContext.fillRect(0, 0, elements.cropCanvas.width, elements.cropCanvas.height);
  canvasContext.fillStyle = "#6c5b4d";
  canvasContext.font = "18px 'Yu Gothic UI'";
  canvasContext.textAlign = "center";
  canvasContext.fillText(
    "选择一张图片后，这里可以框选固定区域",
    elements.cropCanvas.width / 2,
    elements.cropCanvas.height / 2,
  );
  state.canvasFit = null;
  elements.activeInfo.textContent = "当前预览：未选择图片";
}

function renderCropInfo() {
  if (!state.crop) {
    elements.cropInfo.textContent = "当前区域：未设置";
    return;
  }
  const percent = (value) => `${Math.round(value * 1000) / 10}%`;
  elements.cropInfo.textContent = `当前区域：x ${percent(state.crop.x)} / y ${percent(state.crop.y)} / 宽 ${percent(state.crop.width)} / 高 ${percent(state.crop.height)}`;
}

function drawCropOverlay() {
  if (!state.crop || !state.canvasFit) {
    return;
  }
  const fit = state.canvasFit;
  const x = fit.offsetX + state.crop.x * fit.drawWidth;
  const y = fit.offsetY + state.crop.y * fit.drawHeight;
  const width = state.crop.width * fit.drawWidth;
  const height = state.crop.height * fit.drawHeight;
  canvasContext.fillStyle = "rgba(187, 90, 42, 0.16)";
  canvasContext.strokeStyle = "#bb5a2a";
  canvasContext.lineWidth = 3;
  canvasContext.fillRect(x, y, width, height);
  canvasContext.strokeRect(x, y, width, height);
}

async function drawActiveImage() {
  const entry = getActiveFile();
  if (!entry) {
    drawEmptyCanvas();
    return;
  }
  const image = await loadImage(entry);
  const maxWidth = elements.cropCanvas.width;
  const maxHeight = elements.cropCanvas.height;
  const scale = Math.min(maxWidth / image.width, maxHeight / image.height);
  const drawWidth = image.width * scale;
  const drawHeight = image.height * scale;
  const offsetX = (maxWidth - drawWidth) / 2;
  const offsetY = (maxHeight - drawHeight) / 2;

  canvasContext.clearRect(0, 0, maxWidth, maxHeight);
  canvasContext.fillStyle = "rgba(35, 25, 18, 0.04)";
  canvasContext.fillRect(0, 0, maxWidth, maxHeight);
  canvasContext.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);
  state.canvasFit = { offsetX, offsetY, drawWidth, drawHeight, naturalWidth: image.width, naturalHeight: image.height };
  elements.activeInfo.textContent = `当前预览：${entry.displayName} (${image.width}×${image.height})`;
  drawCropOverlay();
  renderCropInfo();
}

function canvasPointToInternal(clientX, clientY) {
  const rect = elements.cropCanvas.getBoundingClientRect();
  const scaleX = elements.cropCanvas.width / rect.width;
  const scaleY = elements.cropCanvas.height / rect.height;
  return {
    x: (clientX - rect.left) * scaleX,
    y: (clientY - rect.top) * scaleY,
  };
}

function clampToImage(point) {
  if (!state.canvasFit) {
    return point;
  }
  return {
    x: Math.min(state.canvasFit.offsetX + state.canvasFit.drawWidth, Math.max(state.canvasFit.offsetX, point.x)),
    y: Math.min(state.canvasFit.offsetY + state.canvasFit.drawHeight, Math.max(state.canvasFit.offsetY, point.y)),
  };
}

function updateCropFromCanvas(startPoint, endPoint) {
  if (!state.canvasFit) {
    return;
  }
  const fit = state.canvasFit;
  const left = Math.min(startPoint.x, endPoint.x);
  const top = Math.min(startPoint.y, endPoint.y);
  const right = Math.max(startPoint.x, endPoint.x);
  const bottom = Math.max(startPoint.y, endPoint.y);
  const width = right - left;
  const height = bottom - top;
  if (width < 8 || height < 8) {
    state.crop = null;
  } else {
    state.crop = {
      x: (left - fit.offsetX) / fit.drawWidth,
      y: (top - fit.offsetY) / fit.drawHeight,
      width: width / fit.drawWidth,
      height: height / fit.drawHeight,
    };
  }
  drawActiveImage();
}

function persistCrop() {
  if (!state.crop) {
    setLog("还没有框选区域。");
    return;
  }
  localStorage.setItem(savedCropKey, JSON.stringify(state.crop));
  setLog("固定区域已保存到浏览器。");
}

function loadSavedCrop() {
  const raw = localStorage.getItem(savedCropKey);
  if (!raw) {
    setLog("还没有保存过固定区域。");
    return;
  }
  try {
    state.crop = JSON.parse(raw);
    renderCropInfo();
    drawActiveImage();
    setLog("已读取保存的固定区域。");
  } catch (error) {
    setLog("保存的固定区域损坏了，已忽略。");
  }
}

function resetCrop() {
  state.crop = null;
  renderCropInfo();
  drawActiveImage();
  setLog("已切回整页翻译。");
}

function initializeSavedCrop() {
  const raw = localStorage.getItem(savedCropKey);
  if (!raw) {
    return;
  }
  try {
    state.crop = JSON.parse(raw);
  } catch (error) {
    localStorage.removeItem(savedCropKey);
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    if (data.online && data.active) {
      elements.statusOnline.textContent = "在线";
      elements.statusOnline.className = "status-value online";
      elements.statusModel.textContent = data.active.model || "已连接";
      elements.statusEndpoint.textContent = data.active.endpoint || "127.0.0.1";
    } else {
      elements.statusOnline.textContent = "离线";
      elements.statusOnline.className = "status-value offline";
      elements.statusModel.textContent = "未连接";
      elements.statusEndpoint.textContent = "127.0.0.1";
    }
  } catch (error) {
    elements.statusOnline.textContent = "异常";
    elements.statusOnline.className = "status-value offline";
    elements.statusModel.textContent = "无法访问网页后端";
    elements.statusEndpoint.textContent = "-";
  }
}

async function startModel(modelPreset) {
  setLog(`正在启动 ${modelPreset.toUpperCase()} ...`);
  try {
    const response = await fetch("/api/start-model", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_preset: modelPreset }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "启动失败");
    }
    await refreshStatus();
    setLog(`模型已就绪：${data.active.model} @ ${data.active.endpoint}`);
  } catch (error) {
    setLog(`模型启动失败：${error.message}`);
  }
}

function renderDownloads(downloads) {
  if (!downloads || !Object.keys(downloads).length) {
    elements.downloads.innerHTML = "";
    return;
  }
  elements.downloads.innerHTML = `
    <a class="file-label" href="${downloads.zip}" target="_blank" rel="noreferrer">下载整包 ZIP</a>
    <a class="file-label" href="${downloads.markdown}" target="_blank" rel="noreferrer">下载 Markdown</a>
    <a class="file-label" href="${downloads.csv}" target="_blank" rel="noreferrer">下载 CSV</a>
    <a class="file-label" href="${downloads.json}" target="_blank" rel="noreferrer">下载 JSON</a>
  `;
}

function renderResults(result) {
  if (!result || !result.pages || !result.pages.length) {
    elements.results.innerHTML = '<div class="muted">这次任务没有产出可显示的页面结果。</div>';
    return;
  }
  elements.results.innerHTML = result.pages
    .map((page, index) => {
      const rows = page.items && page.items.length
        ? page.items
            .map(
              (item) => `
                <tr>
                  <td>${escapeHtml(item.id)}</td>
                  <td>${escapeHtml(item.type)}</td>
                  <td>${escapeHtml(item.source_jp || "")}</td>
                  <td>${escapeHtml(item.target_zh || "")}</td>
                  <td>${escapeHtml(item.notes || "")}</td>
                </tr>
              `,
            )
            .join("")
        : '<tr><td colspan="5">没有识别到可翻译文本，或者需要手动查看原始回复。</td></tr>';

      return `
        <details class="result-card" ${index === 0 ? "open" : ""}>
          <summary>
            <div class="result-title">
              <div class="result-name">${escapeHtml(page.name)}</div>
              <div class="result-summary">${escapeHtml(page.summary || "未生成摘要")}</div>
            </div>
            <div class="tiny">${page.items ? page.items.length : 0} 条</div>
          </summary>
          <div class="result-body">
            ${page.preview_url ? `<div class="result-preview"><img src="${page.preview_url}" alt="${escapeHtml(page.name)}"></div>` : ""}
            <div class="muted">整页备注：${escapeHtml(page.global_notes || "（无）")}</div>
            <div class="result-links">
              ${page.raw_url ? `<a class="file-label" href="${page.raw_url}" target="_blank" rel="noreferrer">原始回复</a>` : ""}
              ${page.json_url ? `<a class="file-label" href="${page.json_url}" target="_blank" rel="noreferrer">单页 JSON</a>` : ""}
              ${page.md_url ? `<a class="file-label" href="${page.md_url}" target="_blank" rel="noreferrer">单页 Markdown</a>` : ""}
            </div>
            <table>
              <thead>
                <tr>
                  <th>序号</th>
                  <th>类型</th>
                  <th>日文原文</th>
                  <th>中文汉化</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </details>
      `;
    })
    .join("");
}

async function pollJob(jobId) {
  if (state.pollHandle) {
    clearInterval(state.pollHandle);
  }

  async function tick() {
    const response = await fetch(`/api/jobs/${jobId}`);
    const data = await response.json();
    if (!response.ok || !data.ok) {
      setLog(data.error || "任务状态查询失败。");
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      return;
    }

    const job = data.job;
    const total = Math.max(1, Number(job.progress.total || 0));
    const current = Number(job.progress.current || 0);
    const percent = Math.min(100, Math.round((current / total) * 100));
    elements.progressFill.style.width = `${percent}%`;
    elements.progressText.textContent = `${job.status === "done" ? "完成" : "处理中"} ${current} / ${total} ${job.progress.current_name ? `- ${job.progress.current_name}` : ""}`;
    setLog(job.error ? `${job.message}\n${job.error}` : job.message);

    if (job.status === "done") {
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      renderDownloads(job.downloads);
      renderResults(job.result);
      await refreshStatus();
    } else if (job.status === "error") {
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      renderDownloads(job.downloads);
    }
  }

  await tick();
  state.pollHandle = setInterval(tick, 2000);
}

async function startTranslation() {
  if (!state.files.length) {
    setLog("请先添加至少一张图片。");
    return;
  }

  const formData = new FormData();
  state.files.forEach((entry) => {
    formData.append("files", entry.file, entry.displayName);
  });
  formData.append("model_preset", elements.modelPreset.value);
  formData.append("start_if_needed", elements.autoStartToggle.checked ? "true" : "false");
  formData.append("timeout", "300");
  formData.append("max_tokens", "1800");

  const shouldUseCrop = !!state.crop && (state.files.length === 1 || elements.applyCropAllToggle.checked);
  if (shouldUseCrop) {
    formData.append("crop_json", JSON.stringify(state.crop));
  }

  elements.translateBtn.disabled = true;
  elements.downloads.innerHTML = "";
  elements.results.innerHTML = '<div class="muted">任务已经提交，正在等待模型返回结果。</div>';
  elements.progressFill.style.width = "0%";
  elements.progressText.textContent = "任务已提交。";
  setLog("正在创建翻译任务...");

  try {
    const response = await fetch("/api/translate", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "创建任务失败");
    }
    state.currentJobId = data.job_id;
    await pollJob(data.job_id);
  } catch (error) {
    setLog(`创建任务失败：${error.message}`);
  } finally {
    elements.translateBtn.disabled = false;
  }
}

elements.dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  elements.dropzone.classList.add("dragging");
});

elements.dropzone.addEventListener("dragleave", () => {
  elements.dropzone.classList.remove("dragging");
});

elements.dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  elements.dropzone.classList.remove("dragging");
  addFiles(event.dataTransfer.files);
});

document.addEventListener("paste", (event) => {
  const items = Array.from(event.clipboardData?.items || []);
  const images = items.filter((item) => item.type.startsWith("image/"));
  if (!images.length) {
    return;
  }
  event.preventDefault();
  const files = images.map((item, index) => {
    const file = item.getAsFile();
    return new File([file], `clipboard-${Date.now()}-${index + 1}.png`, { type: file.type || "image/png" });
  });
  addFiles(files);
  setLog(`已从剪贴板添加 ${files.length} 张截图。`);
});

elements.fileInput.addEventListener("change", (event) => {
  addFiles(event.target.files);
  event.target.value = "";
});

elements.folderInput.addEventListener("change", (event) => {
  addFiles(event.target.files);
  event.target.value = "";
});

elements.clearFilesBtn.addEventListener("click", clearFiles);
elements.refreshStatusBtn.addEventListener("click", refreshStatus);
elements.quickStartBtn.addEventListener("click", () => startModel(elements.modelPreset.value));
elements.start7bBtn.addEventListener("click", () => startModel("7b"));
elements.start30bBtn.addEventListener("click", () => startModel("30b"));
elements.resetCropBtn.addEventListener("click", resetCrop);
elements.saveCropBtn.addEventListener("click", persistCrop);
elements.loadCropBtn.addEventListener("click", loadSavedCrop);
elements.translateBtn.addEventListener("click", startTranslation);

elements.gallery.addEventListener("click", (event) => {
  const removeIndex = event.target.getAttribute("data-remove");
  if (removeIndex !== null) {
    const removed = state.files.splice(Number(removeIndex), 1);
    if (removed.length) {
      URL.revokeObjectURL(removed[0].previewUrl);
    }
    if (!state.files.length) {
      state.activeIndex = -1;
    } else {
      state.activeIndex = Math.min(state.activeIndex, state.files.length - 1);
    }
    renderGallery();
    drawActiveImage();
    return;
  }

  const thumb = event.target.closest("[data-index]");
  if (!thumb) {
    return;
  }
  state.activeIndex = Number(thumb.getAttribute("data-index"));
  renderGallery();
  drawActiveImage();
});

elements.cropCanvas.addEventListener("mousedown", (event) => {
  if (!state.canvasFit) {
    return;
  }
  const point = clampToImage(canvasPointToInternal(event.clientX, event.clientY));
  state.drawState.dragging = true;
  state.drawState.startX = point.x;
  state.drawState.startY = point.y;
});

elements.cropCanvas.addEventListener("mousemove", async (event) => {
  if (!state.drawState.dragging || !state.canvasFit) {
    return;
  }
  const point = clampToImage(canvasPointToInternal(event.clientX, event.clientY));
  await drawActiveImage();
  canvasContext.fillStyle = "rgba(187, 90, 42, 0.14)";
  canvasContext.strokeStyle = "#bb5a2a";
  canvasContext.lineWidth = 3;
  const x = Math.min(state.drawState.startX, point.x);
  const y = Math.min(state.drawState.startY, point.y);
  const width = Math.abs(point.x - state.drawState.startX);
  const height = Math.abs(point.y - state.drawState.startY);
  canvasContext.fillRect(x, y, width, height);
  canvasContext.strokeRect(x, y, width, height);
});

["mouseup", "mouseleave"].forEach((eventName) => {
  elements.cropCanvas.addEventListener(eventName, (event) => {
    if (!state.drawState.dragging || !state.canvasFit) {
      return;
    }
    const point = clampToImage(canvasPointToInternal(event.clientX, event.clientY));
    state.drawState.dragging = false;
    updateCropFromCanvas({ x: state.drawState.startX, y: state.drawState.startY }, point);
  });
});

window.addEventListener("resize", () => {
  drawActiveImage();
});

elements.modelPreset.value = document.body.dataset.defaultPreset || "7b";
initializeSavedCrop();
drawEmptyCanvas();
renderCropInfo();
refreshStatus();
setInterval(refreshStatus, 15000);
