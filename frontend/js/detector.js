import { CONFIG } from './config.js';
import { state } from './state.js';
import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { LandInfo } from './landInfo.js';
import { History } from './history.js';
import { Auth } from './auth.js';
import { API } from './api.js';
import { Annotator } from './annotator.js';
import { Notify } from './notify.js';
import { CompareSlider } from './compareSlider.js';
import { ShareView } from './shareView.js';
import { I18n } from './i18n.js';
import { NDVIViewer } from './ndviViewer.js';
import { ImageTools } from './imageTools.js';
import { Gallery } from './gallery.js';

export const Detector = {
    _scoreImageData: null,  // cached score_map ImageData for re-thresholding
    _t2Img: null,           // cached T2 Image element for fusion

    init() {
        document.getElementById("startBtn").onclick = () => this.start();
        document.getElementById("clearBtn").onclick = () => this.reset();
        document.getElementById("retryBtn").onclick = () => this.start();
        document.getElementById("aiAnalysisBtn").onclick = () => this.handleAIAnalysis();
        document.getElementById("revertMaskBtn").onclick = () => this.revertMask();
        const autoBtn = document.getElementById("autoThresholdBtn");
        if (autoBtn) autoBtn.onclick = () => this.autoThreshold();

        // Threshold slider
        const slider = document.getElementById("thresholdSlider");
        if (slider) {
            slider.oninput = () => this._onSliderInput();
        }
        const otsuBtn = document.getElementById("otsuResultBtn");
        if (otsuBtn) otsuBtn.onclick = () => this._applyOtsuResult();
        const saveBtn = document.getElementById("saveThresholdBtn");
        if (saveBtn) saveBtn.onclick = () => this._saveThreshold();

        // Swap T1/T2
        const swapBtn = document.getElementById("swapPairBtn");
        if (swapBtn) swapBtn.onclick = () => this._swapImages();

        // SUSY-CD quick pair (requires HTTPS / secure context)
        const quickPairBtn = document.getElementById("susycdQuickBtn");
        if (quickPairBtn) {
            if (!window.isSecureContext) {
                quickPairBtn.style.display = 'none';
                const hint = document.createElement('span');
                hint.className = 'field-hint';
                hint.textContent = 'SUSY-CD 快速配对需要 HTTPS 安全连接，当前为 HTTP';
                hint.style.color = 'var(--text-tertiary)';
                hint.style.fontSize = '12px';
                quickPairBtn.parentNode?.appendChild(hint);
            } else {
                quickPairBtn.onclick = () => this._quickPairSUSYCD();
            }
        }

        // Save settings on change
        const modelSel = document.getElementById("model_type");
        if (modelSel) modelSel.onchange = () => this._saveSettings();
        const threshInp = document.getElementById("threshold");
        if (threshInp) threshInp.onchange = () => this._saveSettings();
        document.querySelectorAll('.model-compare-check').forEach(cb => {
            cb.onchange = () => this._saveSettings();
        });

        // Restore last settings
        this._restoreSettings();
    },

    _saveSettings() {
        const config = {
            model: document.getElementById("model_type")?.value,
            threshold: document.getElementById("threshold")?.value,
            checks: Array.from(document.querySelectorAll('.model-compare-check:checked')).map(cb => cb.value)
        };
        Utils.safeLocalStorage.setItem(CONFIG.DETECT_CONFIG_KEY, JSON.stringify(config));
    },

    _restoreSettings() {
        try {
            const saved = Utils.safeLocalStorage.getItem(CONFIG.DETECT_CONFIG_KEY);
            if (!saved) return;
            const config = JSON.parse(saved);
            if (config.model) {
                const sel = document.getElementById("model_type");
                if (sel && sel.querySelector(`option[value="${config.model}"]`)) sel.value = config.model;
            }
            if (config.threshold) {
                document.getElementById("threshold").value = config.threshold;
            }
            if (config.checks && config.checks.length) {
                document.querySelectorAll('.model-compare-check').forEach(cb => {
                    cb.checked = config.checks.includes(cb.value);
                });
            }
        } catch (e) {}
    },

    _swapImages() {
        const file1 = document.getElementById("file1");
        const file2 = document.getElementById("file2");
        const img1 = document.getElementById("img1");
        const img2 = document.getElementById("img2");
        const name1 = document.getElementById("f1name");
        const name2 = document.getElementById("f2name");
        const zone1 = document.getElementById("upload1");
        const zone2 = document.getElementById("upload2");

        // Swap file inputs
        const tmpFile = file1.files[0] ? new File([file1.files[0]], file1.files[0].name, { type: file1.files[0].type }) : null;
        const tmpFile2 = file2.files[0] ? new File([file2.files[0]], file2.files[0].name, { type: file2.files[0].type }) : null;
        if (tmpFile2) {
            const dt = new DataTransfer();
            dt.items.add(tmpFile2);
            file1.files = dt.files;
        } else {
            file1.value = '';
        }
        if (tmpFile) {
            const dt = new DataTransfer();
            dt.items.add(tmpFile);
            file2.files = dt.files;
        } else {
            file2.value = '';
        }

        // Swap previews
        const tmpSrc = img1.src;
        const tmpHidden = img1.classList.contains('hidden');
        img1.src = img2.src;
        img1.classList.toggle('hidden', img2.classList.contains('hidden'));
        img2.src = tmpSrc;
        img2.classList.toggle('hidden', tmpHidden);

        // Swap names
        const tmpText = name1.textContent;
        const tmpHidden2 = name1.classList.contains('hidden');
        name1.textContent = name2.textContent;
        name1.classList.toggle('hidden', name2.classList.contains('hidden'));
        name2.textContent = tmpText;
        name2.classList.toggle('hidden', tmpHidden2);

        // Swap upload zone states
        zone1.classList.toggle('has-file', !name1.classList.contains('hidden'));
        zone2.classList.toggle('has-file', !name2.classList.contains('hidden'));

        // Trigger onchange to update any dependent state
        if (file1.files[0]) file1.dispatchEvent(new Event('change'));
        if (file2.files[0]) file2.dispatchEvent(new Event('change'));

        Utils.showToast(I18n.t('detect.swapDone'));
    },

    async _quickPairSUSYCD() {
        // File System Access API — select root dataset folder
        if (!window.showDirectoryPicker) {
            Modal.alert(I18n.t('detect.susycdNeedChrome'));
            return;
        }
        try {
            const rootHandle = await window.showDirectoryPicker({ mode: 'read' });
            let aHandle, bHandle;
            try { aHandle = await rootHandle.getDirectoryHandle('A'); } catch (e) {}
            try { bHandle = await rootHandle.getDirectoryHandle('B'); } catch (e) {}
            if (!aHandle || !bHandle) {
                try { aHandle = await rootHandle.getDirectoryHandle('a'); } catch (e) {}
                try { bHandle = await rootHandle.getDirectoryHandle('b'); } catch (e) {}
            }
            if (!aHandle || !bHandle) {
                return Modal.alert(I18n.t('detect.susycdNoDir'));
            }

            const aFiles = []; const bFiles = [];
            for await (const [name] of aHandle.entries()) {
                if (/\.(png|jpg|jpeg|tif|tiff|bmp)$/i.test(name)) aFiles.push(name);
            }
            for await (const [name] of bHandle.entries()) {
                if (/\.(png|jpg|jpeg|tif|tiff|bmp)$/i.test(name)) bFiles.push(name);
            }
            const bSet = new Set(bFiles.map(f => f.toLowerCase()));

            const pairs = aFiles.filter(f => bSet.has(f.toLowerCase()));
            if (pairs.length === 0) {
                return Modal.alert(I18n.t('detect.susycdNoMatch'));
            }

            const chosen = await this._showPairPicker(pairs);
            if (chosen) {
                const [aFile, bFile] = await Promise.all([
                    aHandle.getFileHandle(chosen).then(h => h.getFile()),
                    bHandle.getFileHandle(chosen).then(h => h.getFile())
                ]);
                const dt1 = new DataTransfer(); dt1.items.add(aFile);
                const dt2 = new DataTransfer(); dt2.items.add(bFile);
                const f1 = document.getElementById("file1");
                const f2 = document.getElementById("file2");
                f1.files = dt1.files;
                f2.files = dt2.files;
                f1.dispatchEvent(new Event('change'));
                f2.dispatchEvent(new Event('change'));
            }
        } catch (e) {
            if (e.name !== 'AbortError') {
                console.error('SUSY-CD quick pair error:', e);
                Modal.alert('读取数据集失败：' + e.message);
            }
        }
    },

    _showPairPicker(pairs) {
        return new Promise((resolve) => {
            const html = '<div class="modal-box" style="max-width:500px;max-height:80vh;display:flex;flex-direction:column;">' +
                '<div class="modal-title">SUSY-CD 快速配对 <button id="modalCloseBtn" style="float:right;background:none;border:none;font-size:20px;cursor:pointer;color:var(--text-tertiary);">&times;</button></div>' +
                '<div style="overflow-y:auto;flex:1;padding:0 4px;">' +
                '<p style="margin-bottom:12px;color:var(--text-secondary);font-size:13px;">找到 <strong>' + pairs.length + '</strong> 对匹配图片，点击选择：</p>' +
                pairs.map(p => '<button class="btn-gray susycd-pair-btn" data-name="' + p + '" style="display:block;width:100%;text-align:left;margin-bottom:4px;padding:10px 14px;font-family:monospace;font-size:13px;">📷 ' + p + '</button>').join('') +
                '</div></div>';
            const { overlay, close } = Modal.createOverlay(html);
            // Bind pair buttons
            setTimeout(() => {
                overlay.querySelectorAll('.susycd-pair-btn').forEach(btn => {
                    btn.onclick = () => {
                        close();
                        resolve(btn.dataset.name);
                    };
                });
                // Close button and overlay click already handled by createOverlay, resolve null
                const origClose = close;
                // Override close to resolve null
                overlay.addEventListener('click', function handler(e) {
                    if (e.target === overlay) {
                        overlay.removeEventListener('click', handler);
                        resolve(null);
                    }
                });
            }, 100);
        });
    },

    async start() {
        if (!Auth.checkLogin()) return;

        const file1 = document.getElementById("file1").files[0];
        const file2 = document.getElementById("file2").files[0];
        if (!file1 || !file2) return Modal.alert(I18n.t('detect.uploadFirst'));
        const v1 = Utils.validateFile(file1);
        const v2 = Utils.validateFile(file2);
        if (!v1.valid) return Modal.alert("T1: " + v1.msg);
        if (!v2.valid) return Modal.alert("T2: " + v2.msg);

        const btn = document.getElementById("startBtn");
        const status = document.getElementById("status");
        btn.disabled = true;
        btn.innerHTML = I18n.t('detect.detecting');
        status.className = "status-badge show loading";
        status.innerHTML = '<span>' + I18n.t('detect.inferring') + '</span>';
        document.getElementById("resultArea").classList.add("hidden");
        document.getElementById("aiAnalysisResult").classList.add("hidden");
        var mcs = document.getElementById("modelCompareSection");
        if (mcs) mcs.classList.add("hidden");
        document.getElementById("retryBtn").style.display = 'none';
        const reportBtn = document.getElementById("downloadReportBtn");
        if (reportBtn) reportBtn.style.display = 'none';

        const landData = LandInfo.getData();
        const changeType = landData.change_type_define || "黑土层变薄退化";

        // Model comparison: if multiple checkboxes checked, run compare mode
        const selectedModels = this._getSelectedCompareModels();
        if (selectedModels.length >= 2) {
            return this._startCompare(file1, file2, btn, status, landData, changeType);
        }
        const modelName = selectedModels.length === 1 ? selectedModels[0] : document.getElementById("model_type").value;

        const fd = new FormData();
        fd.append("img1", file1);
        fd.append("img2", file2);
        fd.append("model", modelName);
        fd.append("threshold", document.getElementById("threshold").value);
        fd.append("lat_lng", landData.lat_lng || "");
        fd.append("location", (landData.province || "") + (landData.city || ""));
        fd.append("change_type", changeType);
        fd.append("t1_time", landData.t1_time || "");
        fd.append("t2_time", landData.t2_time || "");

        try {
            const json = await API.postDetect(fd);
            if (json.code === 200) {
                state.currentDetectResult = {
                    detection_id: json.detection_id,
                    change_area_ratio: json.stats.ratio,
                    change_pixel: json.stats.change_pixel,
                    total_pixel: json.stats.total_pixel,
                    threshold: json.stats.threshold,
                    change_type: changeType,
                    t1_time: landData.t1_time,
                    t2_time: landData.t2_time,
                    province: landData.province,
                    city: landData.city,
                    lat_lng: landData.lat_lng || "未填写",
                    area: landData.area || "未填写",
                    land_type: landData.land_type,
                    crop_type: landData.crop_type,
                    data_source: landData.data_source,
                    location: (landData.province || "") + (landData.city || ""),
                    model: modelName,
                    t1_url: document.getElementById("img1").src,
                    t2_url: document.getElementById("img2").src,
                    mask_url: json.mask,
                    heat_url: json.heat,
                    fusion_url: json.fusion,
                    score_url: json.score || ""
                };
                this.showResult(json);
                state.persist();
                Notify.detectComplete(state.currentDetectResult);
                History.load();
                if (json.detection_id) this._runClassification(json.detection_id);
                // 游客配额递减
                if (Auth.isGuest()) {
                    const remaining = Auth.useGuestQuota();
                    if (remaining <= 0) {
                        setTimeout(() => {
                            Modal.alert(I18n.t('guest.quotaExhausted'));
                            Auth.showAuthOverlay('login');
                        }, 800);
                    }
                }
            } else {
                throw new Error(json.msg || I18n.t('detect.detectFailed'));
            }
        } catch (e) {
            status.className = "status-badge show error";
            status.innerHTML = '<span>' + e.message + '</span>';
            document.getElementById("retryBtn").style.display = 'inline-block';
        } finally {
            btn.disabled = false;
            btn.innerHTML = I18n.t('detect.start');
        }
        this._saveSettings();
    },

    showResult(json) {
        const status = document.getElementById("status");
        status.className = "status-badge show success";
        const cacheHit = json.msg && json.msg.includes('缓存');
        status.innerHTML = '<span>' + I18n.t('detect.detectComplete') + (cacheHit ? ' <small>' + I18n.t('detect.fromCache') + '</small>' : '') + '</span>';
        document.getElementById("img1_big").src = document.getElementById("img1").src;
        document.getElementById("img2_big").src = document.getElementById("img2").src;

        const maskSrc = state.currentDetectResult?.mask_url || json.mask;
        document.getElementById("resultMask").src = maskSrc;
        document.getElementById("resultHeat").src = json.heat;
        document.getElementById("resultFusion").src = json.fusion;
        document.getElementById("t_pixel").innerText = json.stats.total_pixel;
        document.getElementById("c_pixel").innerText = json.stats.change_pixel;
        document.getElementById("c_ratio").innerText = json.stats.ratio + "%";
        document.getElementById("t_used").innerText = json.stats.threshold;

        const areaEl = document.getElementById("area");
        const areaMu = parseFloat(areaEl?.value) || 0;
        if (areaMu > 0 && json.stats.total_pixel > 0) {
            const actualMu = (json.stats.change_pixel / json.stats.total_pixel) * areaMu;
            document.getElementById("actual_area").innerText = actualMu.toFixed(2) + " 亩";
            state.currentDetectResult.actual_area = parseFloat(actualMu.toFixed(2));
        } else {
            document.getElementById("actual_area").innerText = I18n.t('detect.noAreaHint');
        }

        const revertBtn = document.getElementById("revertMaskBtn");
        if (revertBtn) {
            revertBtn.style.display = state.currentDetectResult?._original_mask_url ? 'inline-flex' : 'none';
        }

        // Show threshold adjust bar if score_url is available
        if (json.score) {
            const bar = document.getElementById("thresholdAdjustBar");
            if (bar) {
                bar.classList.remove("hidden");
            }
            const slider = document.getElementById("thresholdSlider");
            if (slider) {
                const t = Math.round(json.stats.threshold * 100);
                slider.value = t;
                document.getElementById("thresholdSliderVal").innerText = json.stats.threshold.toFixed(2);
            }
            // Store score URL and T2 for re-thresholding
            state.currentDetectResult.score_url = json.score;
            this._loadScoreMap(json.score);
        }

        const ra2 = document.getElementById("resultArea");
        ra2.classList.remove("hidden");
        // 恢复单模型结果元素（对比模式可能已隐藏它们）
        const restoreEls = ra2.querySelectorAll('.stats-row, .result-images-grid, .result-actions, #thresholdAdjustBar, #aiClassificationResult');
        restoreEls.forEach(function(el) { el.style.display = ''; });
        document.getElementById("retryBtn").style.display = 'inline-block';
        const compareBtn = document.getElementById("compareViewBtn");
        if (compareBtn) {
            compareBtn.style.display = 'inline-flex';
            const t1Url = document.getElementById("img1").src;
            const t2Url = document.getElementById("img2").src;
            compareBtn.onclick = () => CompareSlider.show(t1Url, t2Url);
        }
        const annotateBtn = document.getElementById("annotateBtn");
        if (annotateBtn) {
            annotateBtn.style.display = 'inline-flex';
            annotateBtn.onclick = () => {
                Annotator.open(state.currentDetectResult.detection_id, state.currentDetectResult.mask_url);
            };
        }
        const shareBtn = document.getElementById("shareLinkBtn");
        if (shareBtn) {
            shareBtn.style.display = 'inline-flex';
            shareBtn.onclick = () => ShareView.copyLink(state.currentDetectResult);
        }
        document.getElementById("downloadBtn").onclick = () => window.open(json.mask);
        const reportBtn = document.getElementById("downloadReportBtn");
        if (reportBtn) {
            reportBtn.style.display = 'inline-flex';
            reportBtn.onclick = () => {
                import('./reportGenerator.js').then(m => {
                    m.ReportGenerator.generateSingleReport({
                        ...state.currentDetectResult,
                        ai_analysis: document.getElementById("aiAnalysisContent")?.innerText || ''
                    });
                });
            };
        }

        // Show advanced tool buttons
        ['ndviT1Btn', 'checkRegBtn', 'areaStatsBtn', 'exportGeojsonBtn', 'preprocessImgBtn', 'galleryViewBtn'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.style.display = 'inline-flex';
        });
        // Wire advanced tool buttons
        const ndviBtn = document.getElementById('ndviT1Btn');
        if (ndviBtn) ndviBtn.onclick = () => NDVIViewer.computeForImage('file2');
        const regBtn = document.getElementById('checkRegBtn');
        if (regBtn) regBtn.onclick = () => NDVIViewer.checkRegistration();
        const areaBtn = document.getElementById('areaStatsBtn');
        if (areaBtn) areaBtn.onclick = () => NDVIViewer.showAreaStats();
        const geojsonBtn = document.getElementById('exportGeojsonBtn');
        if (geojsonBtn) geojsonBtn.onclick = () => NDVIViewer.exportGeoJSON();
        const preprocessBtn = document.getElementById('preprocessImgBtn');
        if (preprocessBtn) preprocessBtn.onclick = () => {
            const t2Img = document.getElementById('img2_big');
            if (t2Img && t2Img.complete && t2Img.naturalWidth > 0) ImageTools.open(t2Img);
        };
        const galleryBtn = document.getElementById('galleryViewBtn');
        if (galleryBtn) galleryBtn.onclick = () => {
            const images = [];
            const t1 = document.getElementById('img1_big');
            const t2 = document.getElementById('img2_big');
            const mask = document.getElementById('resultMask');
            const heat = document.getElementById('resultHeat');
            const fusion = document.getElementById('resultFusion');
            if (t1?.src) images.push({ url: t1.src, label: 'T1 ' + I18n.t('detect.t1Label') });
            if (t2?.src) images.push({ url: t2.src, label: 'T2 ' + I18n.t('detect.t2Label') });
            if (mask?.src) images.push({ url: mask.src, label: I18n.t('history.detailMask') });
            if (heat?.src) images.push({ url: heat.src, label: I18n.t('history.detailHeat') });
            if (fusion?.src) images.push({ url: fusion.src, label: I18n.t('history.detailFusion') });
            Gallery.open(images, 0);
        };
    },

    reset() {
        document.getElementById("file1").value = "";
        document.getElementById("file2").value = "";
        document.getElementById("f1name").classList.add("hidden");
        document.getElementById("f2name").classList.add("hidden");
        document.getElementById("status").className = "status-badge";
        document.getElementById("resultArea").classList.add("hidden");
        document.getElementById("aiAnalysisResult").classList.add("hidden");
        var mcs = document.getElementById("modelCompareSection");
        if (mcs) mcs.classList.add("hidden");
        document.getElementById("retryBtn").style.display = 'none';
        const reportBtn = document.getElementById("downloadReportBtn");
        if (reportBtn) reportBtn.style.display = 'none';
        const annotateBtn = document.getElementById("annotateBtn");
        if (annotateBtn) annotateBtn.style.display = 'none';
        const compareBtn = document.getElementById("compareViewBtn");
        if (compareBtn) compareBtn.style.display = 'none';
        const revertBtn = document.getElementById("revertMaskBtn");
        if (revertBtn) revertBtn.style.display = 'none';
        ['ndviT1Btn', 'checkRegBtn', 'areaStatsBtn', 'exportGeojsonBtn', 'preprocessImgBtn', 'galleryViewBtn'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.style.display = 'none';
        });
        const threshBar = document.getElementById("thresholdAdjustBar");
        if (threshBar) threshBar.classList.add("hidden");
        this._scoreImageData = null;
        this._t2Img = null;
        ['img1','img2','img1_big','img2_big','resultMask','resultHeat','resultFusion'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                if (el.src) Utils.releaseObjectURL(el.src);
                el.src = '';
            }
        });
        document.querySelectorAll('.upload-zone').forEach(zone => zone.classList.remove('has-file'));
        state.currentDetectResult = null;
        state.persist();
    },

    async handleAIAnalysis() {
        if (!state.currentDetectResult) return Modal.alert(I18n.t('detect.completeFirst'));
        const btn = document.getElementById("aiAnalysisBtn");
        btn.disabled = true;
        btn.innerHTML = I18n.t('detect.generating');
        try {
            const res = await Utils.authFetch(CONFIG.API_BASE_URL + '/ai/analysis-detect-result', {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(state.currentDetectResult)
            });
            const data = await res.json();
            if (data.code === 200) {
                document.getElementById("aiAnalysisContent").innerHTML = Utils.parseMarkdown(data.analysis);
                document.getElementById("aiAnalysisResult").classList.remove("hidden");
            } else {
                throw new Error(data.error || I18n.t('detect.aiGenerateFailed'));
            }
        } catch (e) {
            Modal.alert(I18n.t('detect.aiFailed') + "：" + e.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = I18n.t('detect.aiAnalysis');
        }
    },

    revertMask() {
        if (!state.currentDetectResult?._original_mask_url) return;
        state.currentDetectResult.mask_url = state.currentDetectResult._original_mask_url;
        delete state.currentDetectResult._original_mask_url;
        state.persist();
        document.getElementById('resultMask').src = state.currentDetectResult.mask_url;
        document.getElementById('revertMaskBtn').style.display = 'none';
        Utils.showToast(I18n.t('detect.maskReverted'));
    },

    async autoThreshold() {
        const file1 = document.getElementById("file1").files[0];
        const file2 = document.getElementById("file2").files[0];
        if (!file1 || !file2) return Modal.alert(I18n.t('detect.uploadFirst'));
        try {
            const threshold = await API.recommendThreshold(file1, file2);
            document.getElementById("threshold").value = threshold;
            this._saveSettings();
        } catch (e) {
            Modal.alert(e.message || I18n.t('detect.thresholdFailed'));
        }
    },

    async _runClassification(detectionId) {
        const result = state.currentDetectResult;
        if (!result) return;
        try {
            const classifyData = {
                change_ratio: result.change_area_ratio,
                change_pixel: result.change_pixel,
                total_pixel: result.total_pixel,
                threshold: result.threshold,
                location: result.location || '',
                lat_lng: result.lat_lng || '',
                land_type: result.land_type || '',
                crop_type: result.crop_type || '',
                t1_time: result.t1_time || '',
                t2_time: result.t2_time || '',
                detection_id: detectionId,
            };
            const res = await API.classifyChange(classifyData);
            if (res.code === 200 && res.change_type) {
                state.currentDetectResult.ai_change_type = res.change_type;
                state.currentDetectResult.ai_confidence = res.confidence;
                state.currentDetectResult.ai_reasoning = res.reasoning;
                state.persist();
                this._renderClassificationBadge();
            }
        } catch (e) {
            // AI classification failure is non-critical
        }
    },

    _renderClassificationBadge() {
        const aiType = state.currentDetectResult?.ai_change_type;
        const aiConf = state.currentDetectResult?.ai_confidence;
        if (!aiType) return;

        const container = document.getElementById('aiClassificationResult');
        if (!container) return;
        container.innerHTML = [
            '<div class="ai-classify-badge">',
            '<span class="ai-badge-label">' + I18n.t('classify.aiSuggestion') + '</span>',
            '<span class="ai-badge-type">' + aiType + '</span>',
            '<span class="ai-badge-confidence">' + I18n.t('classify.confidence') + ': ' + (aiConf * 100).toFixed(0) + '%</span>',
            '<button class="btn-small-action" id="acceptAiClassifyBtn">' + I18n.t('classify.acceptAi') + '</button>',
            '<button class="btn-small-action btn-small-secondary" id="dismissAiClassifyBtn">' + I18n.t('classify.override') + '</button>',
            '</div>'
        ].join('');
        container.classList.remove('hidden');

        document.getElementById('acceptAiClassifyBtn').onclick = async () => {
            try {
                await API.updateChangeType(state.currentDetectResult.detection_id, aiType);
                state.currentDetectResult.change_type = aiType;
                state.persist();
                Utils.showToast(I18n.t('classify.accepted'), 'success');
                const btn = document.getElementById('acceptAiClassifyBtn');
                btn.disabled = true;
                btn.textContent = I18n.t('classify.applied');
                document.getElementById('dismissAiClassifyBtn').style.display = 'none';
            } catch {
                Utils.showToast(I18n.t('common.error'), 'error');
            }
        };

        document.getElementById('dismissAiClassifyBtn').onclick = () => {
            container.classList.add('hidden');
        };
    },

    _getSelectedCompareModels() {
        const checks = document.querySelectorAll('.model-compare-check:checked');
        return Array.from(checks).map(cb => cb.value);
    },

    async _startCompare(file1, file2, btn, status, landData, changeType) {
        const selectedModels = this._getSelectedCompareModels();
        const threshold = document.getElementById("threshold").value;

        // 显示父容器，隐藏单模型结果元素，只展示对比区域
        const ra = document.getElementById("resultArea");
        ra.classList.remove("hidden");
        const singleEls = ra.querySelectorAll('.stats-row, .result-images-grid, .result-actions, #thresholdAdjustBar, #aiClassificationResult');
        singleEls.forEach(function(el) { el.style.display = 'none'; });
        document.getElementById("aiAnalysisResult").classList.add("hidden");
        const mcs = document.getElementById("modelCompareSection");
        mcs.classList.remove("hidden");
        mcs.scrollIntoView({ behavior: 'smooth', block: 'start' });
        document.getElementById("modelCompareGrid").innerHTML = '<div class="status-badge show loading" style="grid-column:1/-1;text-align:center;"><span>' + I18n.t('detect.inferring') + '</span></div>';

        const fd = new FormData();
        fd.append("img1", file1);
        fd.append("img2", file2);
        fd.append("models", JSON.stringify(selectedModels));
        fd.append("threshold", threshold);
        fd.append("lat_lng", landData.lat_lng || "");
        fd.append("location", (landData.province || "") + (landData.city || ""));
        fd.append("change_type", changeType);
        fd.append("t1_time", landData.t1_time || "");
        fd.append("t2_time", landData.t2_time || "");

        try {
            const json = await API.compareModels(fd);
            if (json.code === 200) {
                status.className = "status-badge show success";
                status.innerHTML = '<span>' + I18n.t('detect.detectComplete') + '</span>';
                document.getElementById("retryBtn").style.display = 'inline-block';
                this._renderCompareResults(json.results, json.detection_id);
                // 自动滚动到对比结果
                setTimeout(() => {
                    const mcs2 = document.getElementById('modelCompareSection');
                    if (mcs2) mcs2.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 200);

                const firstModel = selectedModels[0];
                const firstResult = json.results && json.results[firstModel];
                if (firstResult) {
                    state.currentDetectResult = {
                        detection_id: json.detection_id,
                        change_area_ratio: firstResult.stats.ratio,
                        change_pixel: firstResult.stats.change_pixel,
                        total_pixel: firstResult.stats.total_pixel,
                        threshold: firstResult.stats.threshold,
                        change_type: changeType,
                        t1_time: landData.t1_time,
                        t2_time: landData.t2_time,
                        province: landData.province,
                        city: landData.city,
                        lat_lng: landData.lat_lng || "未填写",
                        area: landData.area || "未填写",
                        land_type: landData.land_type,
                        crop_type: landData.crop_type,
                        data_source: landData.data_source,
                        location: (landData.province || "") + (landData.city || ""),
                        model: firstModel,
                        t1_url: document.getElementById("img1").src,
                        t2_url: document.getElementById("img2").src,
                        mask_url: firstResult.mask,
                        heat_url: firstResult.heat,
                        fusion_url: firstResult.fusion,
                        score_url: firstResult.score || "",
                    };
                    state.persist();
                    Notify.detectComplete(state.currentDetectResult);
                    History.load();
                    if (json.detection_id) this._runClassification(json.detection_id);
                    // 游客配额递减
                    if (Auth.isGuest()) {
                        const remaining = Auth.useGuestQuota();
                        if (remaining <= 0) {
                            setTimeout(() => {
                                Modal.alert(I18n.t('guest.quotaExhausted'));
                                Auth.showAuthOverlay('login');
                            }, 800);
                        }
                    }
                }
            } else {
                throw new Error(json.msg || I18n.t('detect.detectFailed'));
            }
        } catch (e) {
            console.error('模型对比失败:', e);
            status.className = "status-badge show error";
            status.innerHTML = '<span>' + Utils.escapeHtml(e.message || I18n.t('detect.detectFailed')) + '</span>';
            document.getElementById("retryBtn").style.display = 'inline-block';
            // 清除 loading 动画，显示错误信息
            const grid = document.getElementById('modelCompareGrid');
            if (grid) grid.innerHTML = '<div class="status-badge show error" style="grid-column:1/-1;text-align:center;"><span>' + Utils.escapeHtml(e.message || I18n.t('detect.detectFailed')) + '</span></div>';
        } finally {
            btn.disabled = false;
            btn.innerHTML = I18n.t('detect.start');
        }
    },

    _renderCompareResults(results) {
        const grid = document.getElementById('modelCompareGrid');
        if (!grid) return;

        if (!results || typeof results !== 'object' || Object.keys(results).length === 0) {
            grid.innerHTML = '<div class="status-badge show error" style="grid-column:1/-1;text-align:center;"><span>' + I18n.t('detect.detectFailed') + '</span></div>';
            return;
        }

        const modelOrder = Object.keys(results);
        const isMulti = modelOrder.length > 1;
        const bitResult = results['BIT'];
        grid.style.gridTemplateColumns = isMulti ? 'repeat(auto-fit, minmax(220px, 1fr))' : '1fr';

        // Find max/min for highlighting
        const ratios = modelOrder.map(function(m) { return results[m] ? results[m].stats.ratio : 0; });
        const maxRatio = Math.max.apply(null, ratios);
        const minRatio = Math.min.apply(null, ratios);

        grid.innerHTML = modelOrder.map(function(name) {
            const r = results[name];
            if (!r) return '';
            const isBasic = name === 'DIFF';
            const tagClass = isBasic ? 'model-tag-basic' : 'model-tag-ai';
            const tagLabel = isBasic ? I18n.t('modelCompare.basicMethod') : I18n.t('modelCompare.aiModel');
            const isMax = r.stats.ratio === maxRatio && isMulti;
            const isMin = r.stats.ratio === minRatio && isMulti;
            var html = '<div class="model-compare-col">';
            html += '<h4>' + name + ' <small class="' + tagClass + '">' + tagLabel + '</small>';
            if (isMax) html += ' <span class="badge-compare badge-compare-high">' + I18n.t('modelCompare.highest') + '</span>';
            if (isMin) html += ' <span class="badge-compare badge-compare-low">' + I18n.t('modelCompare.lowest') + '</span>';
            html += '</h4>';
            if (r.mask) {
                html += '<div style="margin-bottom:4px;">';
                html += '<span style="font-size:11px;color:var(--text-tertiary);">' + I18n.t('history.detailMask') + '</span>';
                html += '<img src="' + r.mask + '" crossorigin="anonymous">';
                html += '</div>';
            }
            if (r.heat) {
                html += '<div style="margin-bottom:4px;">';
                html += '<span style="font-size:11px;color:var(--text-tertiary);">' + I18n.t('history.detailHeat') + '</span>';
                html += '<img src="' + r.heat + '" crossorigin="anonymous">';
                html += '</div>';
            }
            if (r.fusion) {
                html += '<div>';
                html += '<span style="font-size:11px;color:var(--text-tertiary);">' + I18n.t('history.detailFusion') + '</span>';
                html += '<img src="' + r.fusion + '" crossorigin="anonymous">';
                html += '</div>';
            }
            html += '<div class="compare-stats">';
            html += '<span>' + I18n.t('detect.changeRatio') + ': <strong>' + r.stats.ratio + '%</strong></span>';
            html += '<span>' + I18n.t('detect.changePixel') + ': ' + r.stats.change_pixel.toLocaleString() + '</span>';
            if (bitResult && name !== 'BIT') {
                var delta = (r.stats.ratio - bitResult.stats.ratio).toFixed(2);
                var sign = delta > 0 ? '+' : '';
                html += '<span style="font-size:11px;color:var(--text-secondary);">vs BIT: ' + sign + delta + '%</span>';
            }
            html += '</div></div>';
            return html;
        }).join('');

        // Render stats table and bar chart if multi-model
        if (isMulti) {
            this._renderCompareTable(results, modelOrder, bitResult);
            this._renderCompareChart(results, modelOrder);
        }

        const note = document.querySelector('.model-compare-note');
        if (note) {
            note.style.display = modelOrder.some(function(m) { return m !== 'BIT'; }) ? '' : 'none';
        }
    },

    _renderCompareTable(results, modelOrder, bitResult) {
        var container = document.getElementById('compareStatsTable');
        var analysis = document.getElementById('modelCompareAnalysis');
        if (!container || !analysis) return;
        analysis.classList.remove('hidden');

        var rows = '';
        modelOrder.forEach(function(name) {
            var r = results[name];
            if (!r) return;
            var deltaStr = '';
            if (bitResult && name !== 'BIT') {
                var delta = (r.stats.ratio - bitResult.stats.ratio).toFixed(2);
                var sign = delta > 0 ? '+' : '';
                var color = Math.abs(delta) > 5 ? 'var(--danger)' : 'var(--text-secondary)';
                deltaStr = '<td style="color:' + color + ';">' + sign + delta + '%</td>';
            } else if (name === 'BIT') {
                deltaStr = '<td style="color:var(--text-tertiary);">—</td>';
            } else {
                deltaStr = '<td style="color:var(--text-tertiary);">—</td>';
            }
            rows += '<tr>' +
                '<td><strong>' + name + '</strong></td>' +
                '<td>' + r.stats.ratio + '%</td>' +
                '<td>' + r.stats.change_pixel.toLocaleString() + '</td>' +
                '<td>' + r.stats.total_pixel.toLocaleString() + '</td>' +
                deltaStr +
                '</tr>';
        });

        container.innerHTML = '<table class="compare-table">' +
            '<thead><tr>' +
            '<th data-i18n="modelCompare.modelCol">模型</th>' +
            '<th data-i18n="detect.changeRatio">变化比例</th>' +
            '<th data-i18n="detect.changePixel">变化像素</th>' +
            '<th data-i18n="detect.totalPixel">总像素</th>' +
            '<th data-i18n="modelCompare.deltaFromBIT">相对BIT偏差</th>' +
            '</tr></thead>' +
            '<tbody>' + rows + '</tbody></table>';
    },

    _renderCompareChart(results, modelOrder) {
        var container = document.getElementById('compareBarChart');
        var analysis = document.getElementById('modelCompareAnalysis');
        if (!container || !analysis) return;
        analysis.classList.remove('hidden');

        var maxRatio = 0;
        modelOrder.forEach(function(m) {
            if (results[m] && results[m].stats.ratio > maxRatio) maxRatio = results[m].stats.ratio;
        });

        var bars = '';
        modelOrder.forEach(function(name) {
            var r = results[name];
            if (!r) return;
            var pct = maxRatio > 0 ? (r.stats.ratio / maxRatio * 100) : 0;
            var isBasic = name === 'DIFF';
            var barColor = isBasic ? 'var(--primary-light)' : 'var(--primary)';
            bars += '<div class="bar-chart-row">' +
                '<span class="bar-chart-label">' + name + '</span>' +
                '<div class="bar-chart-track">' +
                '<div class="bar-chart-fill" style="width:' + pct + '%;background:' + barColor + ';"></div>' +
                '</div>' +
                '<span class="bar-chart-value">' + r.stats.ratio + '%</span>' +
                '</div>';
        });

        container.innerHTML = bars;
    },

    // ---- Interactive threshold slider ----

    _loadScoreMap(scoreUrl) {
        this._scoreImageData = null;
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = img.width;
            canvas.height = img.height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            this._scoreImageData = ctx.getImageData(0, 0, img.width, img.height);
        };
        img.src = scoreUrl;
    },

    _onSliderInput() {
        const slider = document.getElementById("thresholdSlider");
        if (!slider) return;
        const t = parseInt(slider.value) / 100;
        document.getElementById("thresholdSliderVal").innerText = t.toFixed(2);

        if (!this._scoreImageData) return;
        this._applyThresholdAndRender(t);
    },

    _applyThresholdAndRender(threshold) {
        const scoreData = this._scoreImageData;
        const w = scoreData.width;
        const h = scoreData.height;

        // Create mask
        const maskCanvas = document.createElement('canvas');
        maskCanvas.width = w; maskCanvas.height = h;
        const maskCtx = maskCanvas.getContext('2d');
        const maskData = maskCtx.createImageData(w, h);

        // Create heatmap
        const heatCanvas = document.createElement('canvas');
        heatCanvas.width = w; heatCanvas.height = h;
        const heatCtx = heatCanvas.getContext('2d');
        const heatData = heatCtx.createImageData(w, h);

        const thresh = Math.round(threshold * 255);
        let changePx = 0;

        for (let i = 0; i < scoreData.data.length; i += 4) {
            const val = scoreData.data[i]; // R channel = grayscale score
            const isChange = val > thresh;
            const idx = i; // same index in RGBA

            // Mask: white for change, black for no change
            maskData.data[idx] = isChange ? 255 : 0;
            maskData.data[idx + 1] = isChange ? 255 : 0;
            maskData.data[idx + 2] = isChange ? 255 : 0;
            maskData.data[idx + 3] = 255;

            // Heatmap: JET colormap
            const normVal = val / 255;
            const [r, g, b] = this._jetColormap(normVal);
            heatData.data[idx] = r;
            heatData.data[idx + 1] = g;
            heatData.data[idx + 2] = b;
            heatData.data[idx + 3] = 255;

            if (isChange) changePx++;
        }

        maskCtx.putImageData(maskData, 0, 0);
        heatCtx.putImageData(heatData, 0, 0);

        // Update mask image
        const oldMaskUrl = document.getElementById("resultMask").src;
        document.getElementById("resultMask").src = maskCanvas.toDataURL('image/png');
        if (oldMaskUrl && oldMaskUrl.startsWith('blob:')) Utils.releaseObjectURL(oldMaskUrl);

        // Update heatmap image
        const oldHeatUrl = document.getElementById("resultHeat").src;
        document.getElementById("resultHeat").src = heatCanvas.toDataURL('image/png');
        if (oldHeatUrl && oldHeatUrl.startsWith('blob:')) Utils.releaseObjectURL(oldHeatUrl);

        // Update fusion: blend mask with T2
        this._updateFusionCanvas(maskCanvas);

        // Update stats
        const totalPx = w * h;
        const ratio = (changePx / totalPx * 100).toFixed(2);
        document.getElementById("c_pixel").innerText = changePx.toLocaleString();
        document.getElementById("c_ratio").innerText = ratio + "%";
        document.getElementById("t_used").innerText = threshold.toFixed(2);

        const areaEl = document.getElementById("area");
        const areaMu = parseFloat(areaEl?.value) || 0;
        if (areaMu > 0) {
            document.getElementById("actual_area").innerText = (changePx / totalPx * areaMu).toFixed(2) + " 亩";
        }
    },

    _updateFusionCanvas(maskCanvas) {
        const t2El = document.getElementById("img2_big");
        if (!t2El || !t2El.complete) return;
        const w = maskCanvas.width;
        const h = maskCanvas.height;
        const fusionCanvas = document.createElement('canvas');
        fusionCanvas.width = w; fusionCanvas.height = h;
        const ctx = fusionCanvas.getContext('2d');

        // Draw T2 image
        ctx.drawImage(t2El, 0, 0, w, h);
        const t2Data = ctx.getImageData(0, 0, w, h);

        // Overlay mask with red tint at alpha=0.6
        const maskCtx = maskCanvas.getContext('2d');
        const maskData = maskCtx.getImageData(0, 0, w, h);

        for (let i = 0; i < t2Data.data.length; i += 4) {
            if (maskData.data[i] > 0) {
                t2Data.data[i] = Math.round(t2Data.data[i] * 0.4 + 220 * 0.6);     // R
                t2Data.data[i + 1] = Math.round(t2Data.data[i + 1] * 0.4 + 50 * 0.6); // G
                t2Data.data[i + 2] = Math.round(t2Data.data[i + 2] * 0.4 + 50 * 0.6); // B
            }
        }
        ctx.putImageData(t2Data, 0, 0);
        const oldFusionUrl = document.getElementById("resultFusion").src;
        document.getElementById("resultFusion").src = fusionCanvas.toDataURL('image/png');
        if (oldFusionUrl && oldFusionUrl.startsWith('blob:')) Utils.releaseObjectURL(oldFusionUrl);
    },

    _jetColormap(t) {
        // Simplified JET: blue → cyan → green → yellow → red
        let r, g, b;
        if (t < 0.125) {
            r = 0; g = 0; b = Math.round(128 + 127 * (t / 0.125));
        } else if (t < 0.375) {
            const s = (t - 0.125) / 0.25;
            r = 0; g = Math.round(255 * s); b = 255;
        } else if (t < 0.625) {
            const s = (t - 0.375) / 0.25;
            r = Math.round(255 * s); g = 255; b = Math.round(255 * (1 - s));
        } else if (t < 0.875) {
            const s = (t - 0.625) / 0.25;
            r = 255; g = Math.round(255 * (1 - s)); b = 0;
        } else {
            const s = (t - 0.875) / 0.125;
            r = Math.round(255 * (1 - 0.5 * s)); g = 0; b = 0;
        }
        return [r, g, b];
    },

    _computeOtsuFromScore() {
        if (!this._scoreImageData) return 0.5;
        const data = this._scoreImageData.data;
        const hist = new Array(256).fill(0);
        for (let i = 0; i < data.length; i += 4) {
            hist[data[i]]++;
        }
        const total = this._scoreImageData.width * this._scoreImageData.height;
        let sum = 0;
        for (let i = 0; i < 256; i++) sum += i * hist[i];

        let sumB = 0, wB = 0;
        let maxVariance = 0, threshold = 128;
        for (let t = 0; t < 256; t++) {
            wB += hist[t];
            if (wB === 0) continue;
            const wF = total - wB;
            if (wF === 0) break;
            sumB += t * hist[t];
            const mB = sumB / wB;
            const mF = (sum - sumB) / wF;
            const variance = wB * wF * (mB - mF) * (mB - mF);
            if (variance > maxVariance) {
                maxVariance = variance;
                threshold = t;
            }
        }
        return threshold / 255;
    },

    _applyOtsuResult() {
        const otsuVal = this._computeOtsuFromScore();
        const slider = document.getElementById("thresholdSlider");
        if (slider) {
            slider.value = Math.round(otsuVal * 100);
            document.getElementById("thresholdSliderVal").innerText = otsuVal.toFixed(2);
            this._onSliderInput();
        }
    },

    async _saveThreshold() {
        const detectionId = state.currentDetectResult?.detection_id;
        if (!detectionId) return;
        const slider = document.getElementById("thresholdSlider");
        const threshold = parseInt(slider.value) / 100;
        try {
            const json = await API.rethreshold(detectionId, threshold);
            if (json.code === 200) {
                // Update state with saved URLs
                state.currentDetectResult.mask_url = json.mask;
                state.currentDetectResult.heat_url = json.heat;
                state.currentDetectResult.fusion_url = json.fusion;
                state.currentDetectResult.threshold = json.stats.threshold;
                state.currentDetectResult.change_area_ratio = json.stats.ratio;
                state.currentDetectResult.change_pixel = json.stats.change_pixel;
                state.currentDetectResult.total_pixel = json.stats.total_pixel;
                state.persist();
                // Switch displayed images from blob URLs to saved server URLs
                document.getElementById("resultMask").src = json.mask;
                document.getElementById("resultHeat").src = json.heat;
                if (json.fusion) document.getElementById("resultFusion").src = json.fusion;
                Utils.showToast(I18n.t('detect.thresholdSaved'), 'success');
            } else {
                throw new Error(json.msg || 'Save failed');
            }
        } catch (e) {
            Utils.showToast(e.message, 'error');
        }
    },
};
