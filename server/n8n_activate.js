// Register production webhook (mirrors n8n UI save) for target workflow;
// removes any stale webhook rows for the same path (e.g. older workflow id).
const target = process.argv[2] || '1002';
const pathName = process.argv[3] || 'course-rag-demo';
const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/sqlite3');
const db = new sqlite3.Database('/home/node/.n8n/database.sqlite');
db.serialize(() => {
  db.run('update workflow_entity set active=1, activeVersionId=versionId, triggerCount=1 where id=?', [target], (e) => {
    console.log('activate err:', e ? e.message : 'none');
    db.run('delete from webhook_entity where webhookPath=?', [pathName], (e1) => {
      console.log('clean-old err:', e1 ? e1.message : 'none');
      db.run(
        "insert into webhook_entity (workflowId, webhookPath, method, node, webhookId, pathLength) values (?,?,?,?,?,?)",
        [target, pathName, 'POST', 'Webhook', null, null],
        (e2) => {
          console.log('webhook insert err:', e2 ? e2.message : 'none');
          db.all("select workflowId, webhookPath, method from webhook_entity where webhookPath=?", [pathName], (e3, rows) => {
            console.log('rows now:', JSON.stringify(rows));
            db.close();
          });
        });
    });
  });
});