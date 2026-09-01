#!/usr/bin/env bash
# Deploy the remote RAG API on a RAG server (ssh by key, FALT_SERVER=user@host).
# Run from repo root:  FALT_SERVER=user@host bash server/deploy.sh
set -euo pipefail

SERVER="${FALT_SERVER:?Задайте FALT_SERVER=(пользователь@хост вашего RAG-сервера)}"
APP_DIR=~/ragd/app
SERVICE_NAME=rag-api-course

echo "== 1. copy app to server =="
scp -q "$(dirname "$0")/rag_api_server.py" "${SERVER}:${APP_DIR}/rag_api_server.py"

echo "== 2. ensure index present =="
ssh "${SERVER}" "ls ${APP_DIR}/rag_api_server.py"

echo "== 3. systemd unit =="
ssh "${SERVER}" "cat > /tmp/rag-api-course.service <<EOF
[Unit]
Description=Course RAG API (history of science, remote access via ngrok)
After=network.target

[Service]
User=zzz
WorkingDirectory=${APP_DIR}
Environment=RAG_PORT=8010
Environment=RAG_INDEX_DIR=/home/zzz/ragd/index
ExecStart=/home/zzz/ragd/bin/python ${APP_DIR}/rag_api_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo cp /tmp/rag-api-course.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable ${SERVICE_NAME} && sudo systemctl restart ${SERVICE_NAME}"
sleep 3
echo "== 4. health =="
ssh "${SERVER}" "curl -s http://127.0.0.1:8010/health; echo; curl -s 'http://127.0.0.1:8010/search?q=%D0%9D%D1%8C%D1%8E%D1%82%D0%BE%D0%BD' | head -c 300"
echo
echo "OK: RAG API на :8010"