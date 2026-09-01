const path = require('path');
const fs = require('fs');
const wd = '/usr/local/lib/node_modules/n8n';
function find(dir, name, depth) {
  if (depth < 0) return null;
  const p = path.join(dir, name);
  if (fs.existsSync(p)) return p;
  for (const d of fs.readdirSync(dir)) {
    if (d.startsWith('.')) continue;
    const sub = path.join(dir, d);
    let st;
    try { st = fs.statSync(sub); } catch { continue; }
    if (!st.isDirectory()) continue;
    const r = find(sub, name, depth - 1);
    if (r) return r;
  }
  return null;
}
const ax = find(wd, 'axios.js', 5) || find(wd, 'axios/index.js', 5);
console.log('axios at:', ax);
if (ax && require.resolve(ax)) {
  const axios = require(ax);
  (async () => {
    for (let i = 0; i < 3; i++) {
      try {
        const r = await axios.get('https://smoky-steadier-quintet.ngrok-free.dev/rag/search', {
          params: { q: 'Менделеев периодический закон', k: 2 },
          timeout: 60000,
        });
        console.log('try', i, '->', r.status, 'count:', r.data && r.data.count);
      } catch (e) {
        console.log('try', i, '-> ERR', e.code || e.message, e.response ? 'http ' + e.response.status : '');
      }
    }
  })();
} else {
  console.log('axios not found');
}