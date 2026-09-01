#!/usr/bin/env bash
echo "--- proxy x6 ---"
for i in 1 2 3 4 5 6; do
  curl -s -m 40 "http://127.0.0.1:1359/rag/search?q=test${i}&k=1" -o /dev/null -w "${i}:%{http_code} " &
done
wait
echo
echo "--- ngrok path x6 ---"
for i in 1 2 3 4 5 6; do
  curl -s -m 60 "https://smoky-steadier-quintet.ngrok-free.dev/rag/search?q=test${i}&k=1" -o /dev/null -w "${i}:%{http_code} " &
done
wait
echo