#!/bin/sh
echo "container->public:"
curl -s -m 40 -o /dev/null -w "  search: %{http_code} %{time_total}s\n" "https://smoky-steadier-quintet.ngrok-free.dev/rag/search?q=test&k=1"
curl -s -m 40 -o /dev/null -w "  health: %{http_code} %{time_total}s\n" "https://smoky-steadier-quintet.ngrok-free.dev/rag/health"
curl -s -m 40 -o /dev/null -w "  gateway /v1/models: %{http_code}\n" "https://smoky-steadier-quintet.ngrok-free.dev/v1/models"