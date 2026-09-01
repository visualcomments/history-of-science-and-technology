const http = require('http');
function req(url) {
  return new Promise((resolve) => {
    const u = new URL(url);
    const r = http.request(u, { method: 'GET', headers: { 'Accept': '*/*' } }, (res) => {
      let b = '';
      res.on('data', (c) => { b += c; });
      res.on('end', () => resolve(res.statusCode + ' | ' + b.slice(0, 90)));
    });
    r.on('error', (e) => resolve('ERR ' + e.message.slice(0, 80)));
    r.end();
  });
}
(async () => {
  const gw = 'http://172.18.0.1:1359/rag/search?q=';
  console.log('encoded:', await req(gw + encodeURIComponent('Коперник и гелиоцентрическая система') + '&k=1'));
  console.log('raw-spaces:', await req(gw + 'Коперник%20и%20телиоцентрическая%20система&k=1'));
  console.log('simple:', await req('http://172.18.0.1:1359/rag/search?q=test&k=1'));
})();