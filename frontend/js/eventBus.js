// 简单的事件总线，用于模块间解耦通信
class EventBus {
    constructor() {
        this._events = {};
    }
    on(event, callback) {
        if (!this._events[event]) this._events[event] = [];
        this._events[event].push(callback);
    }
    off(event, callback) {
        if (!this._events[event]) return;
        this._events[event] = this._events[event].filter(cb => cb !== callback);
    }
    emit(event, ...args) {
        if (!this._events[event]) return;
        this._events[event].forEach(cb => cb(...args));
    }
}

export const eventBus = new EventBus();