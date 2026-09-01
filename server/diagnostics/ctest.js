const base = 'https://smoky-steadier-quintet.ngrok-free.dev';
(async () => {
  for (const p of ['/rag/health', '/rag/search?q=test&k=1', '/v1/models']) {
    try {
      const r = await fetch(base + p, { signal: AbortSignal.timeout(40000) });
      console.log(p, '->', r.status);
    } catch (e) {
      console.log(p, '-> ERR', e.message.slice(0, 120));
    }
  }
})();