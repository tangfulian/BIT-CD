/**
 * IndexedDB 封装：批量检测任务持久化存储。
 * Database: BIT_CD_Batch
 * Object Store: tasks (keyPath: id)
 */
const DB_NAME = 'BIT_CD_Batch';
const DB_VERSION = 1;
const STORE_NAME = 'tasks';

function _openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
                store.createIndex('status', 'status', { unique: false });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

export const BatchStore = {
    /** 保存一个任务（覆盖已存在的） */
    async saveTask(taskData) {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite');
            const store = tx.objectStore(STORE_NAME);
            const record = {
                id: taskData.id,
                index: taskData.index,
                fileName: taskData.fileName,
                t1File: taskData.t1File,
                t2File: taskData.t2File,
                modelName: taskData.modelName,
                threshold: taskData.threshold,
                latLng: taskData.latLng,
                location: taskData.location,
                changeType: taskData.changeType,
                status: taskData.status || 'pending',
                result: taskData.result || null,
            };
            store.put(record);
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
    },

    /** 更新任务状态和结果 */
    async updateTask(id, updates) {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite');
            const store = tx.objectStore(STORE_NAME);
            const req = store.get(id);
            req.onsuccess = () => {
                const record = req.result;
                if (!record) { resolve(false); return; }
                Object.assign(record, updates);
                store.put(record);
                tx.oncomplete = () => resolve(true);
                tx.onerror = () => reject(tx.error);
            };
            req.onerror = () => reject(req.error);
        });
    },

    /** 获取单个任务 */
    async getTask(id) {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readonly');
            const store = tx.objectStore(STORE_NAME);
            const req = store.get(id);
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => reject(req.error);
        });
    },

    /** 获取所有任务 */
    async getAllTasks() {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readonly');
            const store = tx.objectStore(STORE_NAME);
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result || []);
            req.onerror = () => reject(req.error);
        });
    },

    /** 删除单个任务 */
    async deleteTask(id) {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite');
            const store = tx.objectStore(STORE_NAME);
            store.delete(id);
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
    },

    /** 清除所有任务 */
    async clearAll() {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite');
            const store = tx.objectStore(STORE_NAME);
            store.clear();
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
    }
};
