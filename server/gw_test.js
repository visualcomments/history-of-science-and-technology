(async () => {
  try {
    const r = await fetch('http://172.18.0.1:1359/rag/health');
    console.log('fetch health:', r.status, JSON.stringify(await r.json()));
  } catch (e) {
    console.log('fetch err:', e.message.slice(0, 140));
  }
  try {
    const r = await fetch('http://172.18.0.1:1359/rag/search?q=%D0%9C%D0%B5%D0%BD%D0%B4%D0%B5%D0%BB%D0%B5%D0%B5%D0%B2&k=1');
    const j = await r.json();
    console.log('fetch search:', r.status, 'count:', j.count, 'top:', j.results && j.results[0] && j.results[0].file.slice(0, 40));
  } catch (e) {
    console.log('search err:', e.message.slice(0, 140));
  }
})();