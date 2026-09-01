#!/usr/bin/env bash
q="https://smoky-steadier-quintet.ngrok-free.dev/rag/search?q=%D0%9C%D0%B5%D0%BD%D0%B4%D0%B5%D0%BB%D0%B5%D0%B5%D0%B2%20%D0%BF%D0%B5%D1%80%D0%B8%D0%BE%D0%B4%D0%B8%D1%87%D0%B5%D1%81%D0%BA%D0%B8%D0%B9%20%D0%B7%D0%B0%D0%BA%D0%BE%D0%BD&k=3"
echo -n "plain: "; curl -s -m 60 -o /dev/null -w "%{http_code} %{time_total}s\n" "$q"
echo -n "n8n-UA: "; curl -s -m 60 -o /dev/null -w "%{http_code} %{time_total}s\n" -A "n8n/1.68.0" -H "Accept: */*" "$q"
echo -n "gzip-UA: "; curl -s -m 60 -o /dev/null -w "%{http_code} %{time_total}s\n" -A "n8n/1.68.0" -H "Accept-Encoding: gzip, deflate, br" "$q"
echo -n "kill-conn: "; curl -s -m 60 -o /dev/null -w "%{http_code} %{time_total}s\n" -A "n8n/1.68.0" -H "Connection: close" "$q"