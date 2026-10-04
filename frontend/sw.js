const CACHE_NAME = 'bitcd-v11';

const PRECACHE_URLS = [
  './',
  './index.html',
  './css/styles.css',
  './images/logo.png',
  './js/config.js',
  './js/state.js',
  './js/eventBus.js',
  './js/utils.js',
  './js/api.js',
  './js/modal.js',
  './js/auth.js',
  './js/navigator.js',
  './js/uploader.js',
  './js/gpsLocator.js',
  './js/landInfo.js',
  './js/detector.js',
  './js/batchDetector.js',
  './js/mapViewer.js',
  './js/reportGenerator.js',
  './js/timeline.js',
  './js/bigscreen.js',
  './js/compare.js',
  './js/status.js',
  './js/disaster.js',
  './js/annotator.js',
  './js/history.js',
  './js/chatbot.js',
  './js/userManager.js',
  './js/chartUtils.js',
  './js/compareSlider.js',
  './js/notify.js',
  './js/taskQueue.js',
  './js/i18n.js',
  './js/locales/zh-CN.js',
  './js/locales/en.js',
  // 以下 13 个文件此前漏在清单外，其中 main.js 是应用入口、toast.js 被
  // utils.js 直接 import —— 缺了它们离线打开基本是坏的。
  './js/main.js',
  './js/toast.js',
  './js/models.js',
  './js/agent.js',
  './js/evaluator.js',
  './js/profile.js',
  './js/gallery.js',
  './js/imageTools.js',
  './js/indexedDB.js',
  './js/ndviViewer.js',
  './js/shareView.js',
  './js/shortcuts.js',
  './js/config.local.js',
  // 这四个库与三份字体已改为自托管。原先这里预缓存的是 jsdelivr / cdnjs 的地址，
  // 自托管之后那几条既不生效（图表库那条还会因为 jsdelivr 被重置而静默失败），
  // 真正在用的 /vendor/ 文件反而没有离线副本。
  './vendor/echarts.min.js',
  './vendor/geotiff.js',
  './vendor/jspdf.umd.min.js',
  './vendor/html2canvas.min.js',
  './vendor/fonts/inter-latin-400.woff2',
  './vendor/fonts/inter-latin-500.woff2',
  './vendor/fonts/inter-latin-600.woff2'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return Promise.allSettled(
        PRECACHE_URLS.map(url => cache.add(url).catch(() => {}))
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // 只处理同源的 http/https GET 静态资源
  if (req.method !== 'GET') return;
  if (!url.protocol.startsWith('http')) return;  // 跳过 chrome-extension:// 等
  if (url.origin !== self.location.origin) return; // 跳过跨域请求（API 在 8000）

  event.respondWith(
    caches.match(req).then(cached => {
      // cache: 'no-cache' = 每次都带 ETag 向服务端协商，有更新就取新的。
      // 后端静态文件没有 Cache-Control 头，浏览器会按 Last-Modified 走启发式缓存，
      // 导致改过的 JS 长时间不生效（曾因此出现「历史/看板空白」的假故障）。
      return fetch(req, { cache: 'no-cache' }).then(response => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
        }
        return response;
      }).catch(() => cached);
    })
  );
});
