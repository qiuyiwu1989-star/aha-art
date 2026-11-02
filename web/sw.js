/* aha 人类美术馆 — service worker (保守策略,手写无依赖)
   - 壳预缓存;HTML network-first(回缓存→offline);同源静态 cache-first;
   - /api /cat 与跨域(COS图)一律直连不缓存。改了缓存逻辑就 bump VERSION。 */
const VERSION = 'aha-v4';
const CACHE = 'aha-shell-' + VERSION;

const MAX_ENTRIES=120, MAX_AGE=7*86400000;
async function save(req,net){
 if(!net.ok||net.type!=='basic'||/private|no-store/i.test(net.headers.get('cache-control')||''))return;
 const headers=new Headers(net.headers);headers.set('x-aha-cached-at',String(Date.now()));
 const copy=new Response(await net.clone().arrayBuffer(),{status:net.status,statusText:net.statusText,headers});
 const c=await caches.open(CACHE);await c.put(req,copy);const keys=await c.keys();
 for(const key of keys.slice(0,Math.max(0,keys.length-MAX_ENTRIES)))await c.delete(key);
}
async function cached(req){const c=await caches.open(CACHE),r=await c.match(req);if(!r)return null;
 const stamp=Number(r.headers.get('x-aha-cached-at'));if(stamp&&Date.now()-stamp>MAX_AGE){await c.delete(req);return null}return r;}
// 预缓存外壳(逐个 add,缺失不致命)
const PRECACHE = [
  '/offline.html',
  '/museum.html',
  '/js/aha-app.js',
  '/js/cloud.js',
  '/aha-mem.js',
  '/css/aha-frames.css',
  '/icons/icon-192.png',
  '/manifest.webmanifest'
];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(CACHE);
    await Promise.allSettled(PRECACHE.map(async (u) => save(u, await fetch(u))));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k.startsWith('aha-shell-') && k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

const STATIC_RE = /\.(?:css|js|mjs|png|jpg|jpeg|webp|gif|svg|ico|woff2?|ttf|json|webmanifest)$/i;

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (_) { return; }

  // 跨域(COS 大图、Google Fonts 等)→ 不拦截,交给浏览器直连
  if (url.origin !== self.location.origin) return;

  // 动态后端 → 永远直连,不缓存
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/cat/') || /dashboard|admin|account|profile/.test(url.pathname) || /pass|token|auth/i.test(url.search) || req.headers.has('authorization')) return;

  const isHTML = req.mode === 'navigate' ||
    (req.headers.get('accept') || '').includes('text/html');

  if (isHTML) {
    // network-first:内容随时新鲜,断网回缓存→离线页
    e.respondWith((async () => {
      try {
        const net = await fetch(req);
        await save(req, net);
        return net;
      } catch (_) {
        return (await cached(req)) ||
               (await cached('/offline.html')) ||
               new Response('离线', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
      }
    })());
    return;
  }

  if (STATIC_RE.test(url.pathname)) {
    // stale-while-revalidate:命中缓存即返回(快),同时后台拉最新回填,
    // 下次加载即得新版——避免"museum.html 是新的、cloud.js/aha-app.js 还是旧的"漂移。
    e.respondWith((async () => {
      const hit = await cached(req);
      const fetching = fetch(req).then((net) => {
        if (net && net.ok && net.type === 'basic') {
          return save(req, net).then(()=>net);
        }
        return net;
      }).catch(() => null);
      e.waitUntil(fetching.then(()=>{}));
      return hit || (await fetching) || Response.error();
    })());
  }
});
