/**
 * Toast 通知模块 — 替代 alert()
 * 支持 success / error / warning / info 四种类型
 */
let _container = null;

function _ensureContainer() {
    if (_container && _container.parentNode) return _container;
    _container = document.createElement('div');
    _container.className = 'toast-container';
    document.body.appendChild(_container);
    return _container;
}

const ICONS = {
    success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    error:   '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info:    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
};

function _show(type, message, duration) {
    var d = duration || (type === 'error' ? 5000 : 3000);
    var container = _ensureContainer();
    var el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.innerHTML = '<span class="toast-icon">' + (ICONS[type] || ICONS.info) + '</span><span class="toast-msg">' + message + '</span>';
    container.appendChild(el);

    // 入场动画
    requestAnimationFrame(function () {
        el.classList.add('toast-enter');
    });

    // 自动移除
    var timer = setTimeout(function () {
        _dismiss(el);
    }, d);

    // 点击关闭
    el.addEventListener('click', function () {
        clearTimeout(timer);
        _dismiss(el);
    });
}

function _dismiss(el) {
    el.classList.remove('toast-enter');
    el.classList.add('toast-exit');
    el.addEventListener('transitionend', function () {
        if (el.parentNode) el.parentNode.removeChild(el);
    }, { once: true });
    // fallback if transitionend doesn't fire
    setTimeout(function () {
        if (el.parentNode) el.parentNode.removeChild(el);
    }, 400);
}

export const Toast = {
    success: function (msg) { _show('success', msg, 3000); },
    error:   function (msg) { _show('error', msg, 5000); },
    warning: function (msg) { _show('warning', msg, 4000); },
    info:    function (msg) { _show('info', msg, 3000); },
};
