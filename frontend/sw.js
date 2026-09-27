const CACHE_NAME = 'bitcd-v8';

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
  'https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js'
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
