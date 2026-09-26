import { eventBus } from './eventBus.js';
import { CONFIG } from './config.js';

class TaskQueue {
    constructor(concurrency = 3) {
        this._concurrency = concurrency;
        this._pending = [];
        this._running = new Map();
        this._results = new Map();
        this._nextId = 1;
    }

    add(fn, meta = {}) {
        const id = this._nextId++;
        const controller = new AbortController();
        const task = { id, fn, meta, controller, status: 'pending', tr: meta.tr || null };
        this._pending.push(task);
        eventBus.emit('task-queued', { id, total: this.size });
        this._tick();
        return id;
    }

    pause(id) {
        const task = this._findTask(id);
        if (!task) return false;
        if (task.status === 'pending') {
            task.status = 'paused';
            eventBus.emit('task-paused', { id });
            this._tick();
            return true;
        }
        if (task.status === 'running') {
            task.controller.abort();
            task.status = 'paused';
            this._running.delete(id);
            eventBus.emit('task-paused', { id });
            this._tick();
            return true;
        }
        return false;
    }

    cancel(id) {
        const task = this._findTask(id);
        if (!task) return false;
        if (task.status === 'running') {
            task.controller.abort();
            this._running.delete(id);
        }
        task.status = 'cancelled';
        this._pending = this._pending.filter(t => t.id !== id);
        eventBus.emit('task-cancelled', { id });
        this._tick();
        return true;
    }

    retry(id) {
        const task = this._findTask(id);
        if (!task || (task.status !== 'error' && task.status !== 'cancelled' && task.status !== 'paused')) return false;
        task.status = 'pending';
        task.controller = new AbortController();
        this._pending.push(task);
        eventBus.emit('task-retried', { id });
        this._tick();
        return true;
    }

    resume(id) {
        const task = this._findTask(id);
        if (!task || task.status !== 'paused') return false;
        task.status = 'pending';
        task.controller = new AbortController();
        eventBus.emit('task-resumed', { id });
        this._tick();
        return true;
    }

    get size() {
        return this._pending.length + this._running.size;
    }

    get activeCount() {
        return this._running.size;
    }

    get pendingCount() {
        return this._pending.length;
    }

    _findTask(id) {
        if (this._running.has(id)) return this._running.get(id);
        return this._pending.find(t => t.id === id) || null;
    }

    getResult(id) {
        return this._results.get(id) || null;
    }

    async _tick() {
        while (this._running.size < this._concurrency) {
            const idx = this._pending.findIndex(t => t.status === 'pending');
            if (idx === -1) break;
            const task = this._pending.splice(idx, 1)[0];
            task.status = 'running';
            this._running.set(task.id, task);
            this._runTask(task);
        }
    }

    async _runTask(task) {
        eventBus.emit('task-started', { id: task.id });
        try {
            const result = await task.fn(task.controller.signal);
            task.status = 'completed';
            this._results.set(task.id, { status: 'completed', result });
            eventBus.emit('task-completed', { id: task.id, result });
        } catch (e) {
            if (e?.name === 'AbortError') {
                if (task.status === 'running') {
                    // 非用户操作的 abort（如超时），按错误处理
                    task.status = 'error';
                    this._results.set(task.id, { status: 'error', error: 'Aborted' });
                    eventBus.emit('task-error', { id: task.id, error: 'Aborted' });
                }
                // 用户暂停/取消时已在 pause/cancel 中修改了 status
            } else {
                task.status = 'error';
                this._results.set(task.id, { status: 'error', error: e.message });
                eventBus.emit('task-error', { id: task.id, error: e.message });
            }
        } finally {
            this._running.delete(task.id);
            eventBus.emit('task-progress', {
                total: this._results.size,
                completed: [...this._results.values()].filter(r => r.status === 'completed').length,
                error: [...this._results.values()].filter(r => r.status === 'error').length
            });
            this._tick();
        }
    }

    reset() {
        this._pending = [];
        this._running.clear();
        this._results.clear();
        this._nextId = 1;
    }

    getStats() {
        const entries = [...this._results.values()];
        return {
            completed: entries.filter(r => r.status === 'completed').length,
            error: entries.filter(r => r.status === 'error').length,
            total: entries.length
        };
    }
}

export const taskQueue = new TaskQueue(CONFIG.BATCH_CONCURRENCY);
