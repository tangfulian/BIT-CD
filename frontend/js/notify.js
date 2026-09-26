import { eventBus } from './eventBus.js';

let _permitted = false;
let _audioCtx = null;

function _beep() {
    try {
        if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = _audioCtx.createOscillator();
        const gain = _audioCtx.createGain();
        osc.connect(gain); gain.connect(_audioCtx.destination);
        osc.frequency.value = 880; osc.type = 'sine';
        gain.gain.setValueAtTime(0.15, _audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, _audioCtx.currentTime + 0.3);
        osc.start(_audioCtx.currentTime); osc.stop(_audioCtx.currentTime + 0.3);
    } catch { /* 静默失败 */ }
}

function _notify(title, body, onClick) {
    if (!_permitted || !('Notification' in window)) return;
    try {
        const n = new Notification(title, { body, icon: 'images/logo.png', tag: 'bitcd-notify' });
        if (onClick) {
            n.onclick = () => { onClick(); n.close(); };
        }
    } catch { /* 静默失败 */ }
    _beep();
}

export const Notify = {
    async init() {
        if (!('Notification' in window)) return;
        if (Notification.permission === 'granted') { _permitted = true; return; }
        if (Notification.permission === 'denied') return;
        const result = await Notification.requestPermission();
        _permitted = result === 'granted';
    },

    detectComplete(result) {
        _notify(
            '检测完成',
            `变化率 ${result.change_area_ratio?.toFixed(2)}%，变化区域 ${result.change_pixel} 像素`,
            () => eventBus.emit('navigate', 'single')
        );
    },

    batchComplete(total, doneCount, errCount) {
        _notify(
            '批量检测完成',
            `共 ${total} 张：${doneCount} 成功${errCount > 0 ? '，' + errCount + ' 失败' : ''}`,
            () => eventBus.emit('navigate', 'batch')
        );
    },

    aiReply(preview) {
        _notify(
            'AI 分析已生成',
            preview?.substring(0, 60) || '点击查看分析结果',
            () => eventBus.emit('navigate', 'single')
        );
    },

    info(msg) {
        _notify('Agent 通知', msg?.substring(0, 80) || '');
    }
};
