// ═══ L1 · 内容层 / Content API(只读、稳定)═══
// 上层(L2/L3)只通过这些方法访问数据,永不直接碰存储。
let WORKS = [], BY = {}, ADJ = {}, GRAPH = null;

export const Content = {
  async load() {
    [WORKS, GRAPH] = await Promise.all([
      fetch('data/artworks.json').then(r => r.json()),
      fetch('data/graph.json').then(r => r.json()),
    ]);
    WORKS.forEach(w => { BY[w.slug] = w; ADJ[w.slug] = []; });
    GRAPH.edges.forEach(e => {
      ADJ[e.a].push({ to: e.b, type: e.type, why: e.why });
      ADJ[e.b].push({ to: e.a, type: e.type, why: e.why });
    });
    return this;
  },
  all() { return WORKS; },
  getWork(id) { return BY[id]; },
  neighbors(id, { types } = {}) {
    let e = ADJ[id] || [];
    if (types) e = e.filter(x => types.includes(x.type));
    // 去重(同一目标多条边取第一条)
    const seen = {}; return e.filter(x => (seen[x.to] ? false : (seen[x.to] = 1)));
  },
  byTheme(theme) { return WORKS.filter(w => (w.themes || []).includes(theme)); },
  byMood({ valence, arousal, tol = 0.25 }) {
    return WORKS.filter(w => w.mood && Math.abs(w.mood.valence - valence) <= tol && Math.abs(w.mood.arousal - arousal) <= tol);
  },
  search(text) { const q = (text || '').toLowerCase(); return WORKS.filter(w => (w.title + w.artist).toLowerCase().includes(q)); },
  typeLabel(t) { return (GRAPH && GRAPH.typeLabels[t]) || t; },
  stats() { return { total: WORKS.length, edges: GRAPH ? GRAPH.edges.length : 0 }; },
};
