#!/usr/bin/env bash
for i in 1 2 3; do
  echo -n "post ${i}: "
  curl -s -m 120 -X POST http://127.0.0.1:5678/webhook/course-rag-demo \
    -H 'Content-Type: application/json' --data-binary @/tmp/req.json -w " [%{http_code}]"
  echo
  sleep 2
done