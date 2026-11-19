#!/bin/zsh -l
# ดับเบิลคลิกไฟล์นี้ใน Finder เพื่อเปิดเว็บ Belka (ปิดหน้าต่าง Terminal = ปิดเว็บ)
cd "$(dirname "$0")/backend" || exit 1
command -v uv >/dev/null || export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
echo "กำลังเปิด Belka ที่ http://127.0.0.1:8000 …"
( for i in {1..60}; do curl -s http://127.0.0.1:8000/api/health >/dev/null && open http://127.0.0.1:8000 && exit; sleep 1; done ) &
uv run --with fastapi --with uvicorn uvicorn belka.api:app --host 127.0.0.1 --port 8000
