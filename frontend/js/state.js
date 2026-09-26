/**
 * 共享应用状态，持久化到 sessionStorage。
 * @module state
 */
const STATE_KEY = 'app_state';

function _loadPersisted() {
    try {
        const raw = sessionStorage.getItem(STATE_KEY);
        return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
}

function _persist(s) {
    try {
        const subset = {
            batchResult: s.batchResult.map(item => ({
                name: item.name, ratio: item.ratio, changePixel: item.changePixel,
                totalPixel: item.totalPixel, model: item.model, threshold: item.threshold,
                time: item.time, status: item.status,
                maskUrl: item.maskUrl, heatUrl: item.heatUrl, fusionUrl: item.fusionUrl
                // 注意：blob URL 不持久化（页面刷新后失效）
            })),
            currentDetectResult: s.currentDetectResult
        };
        sessionStorage.setItem(STATE_KEY, JSON.stringify(subset));
    } catch { /* quota exceeded, ignore */ }
}

const _persisted = _loadPersisted();

export const state = {
    currentUser: null,
    currentUserRole: 'user',
    map: null,
    marker: null,
    batchResult: _persisted.batchResult || [],
    currentDetectResult: _persisted.currentDetectResult || null,
    chatHistory: [],

    persist() {
        _persist(this);
    }
};