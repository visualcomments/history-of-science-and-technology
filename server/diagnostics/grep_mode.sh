#!/bin/sh
grep -rhoE '(onLastNode|lastNode|onReceived|responseNode)' \
  /usr/local/lib/node_modules/n8n/node_modules/n8n-nodes-base/dist/nodes/Webhook/ 2>/dev/null \
  | sort | uniq -c | sort -rn | head -10