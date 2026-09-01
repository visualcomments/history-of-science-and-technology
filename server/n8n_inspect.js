const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/sqlite3');
const db = new sqlite3.Database('/home/node/.n8n/database.sqlite');
db.run('pragma busy_timeout=10000', () => {
  db.all("select data from execution_data where executionId=49", (e, rows) => {
    if (!rows.length) { process.exit(0); }
    const raw = rows[0].data;
    console.log('has ngrok:', raw.indexOf('ngrok-free') >= 0);
    console.log('has 172.18.0.1:', raw.indexOf('172.18.0.1') >= 0);
    let i = raw.indexOf('172.18.0.1');
    if (i < 0) i = raw.indexOf('ngrok-free');
    console.log('url context:', raw.slice(i - 100, i + 160).replace(/\\n/g, ' '));
    const arr = JSON.parse(raw);
    console.log('msg:', arr[23], '| node:', arr[20]);
    process.exit(0);
  });
});