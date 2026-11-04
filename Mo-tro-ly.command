#!/bin/bash
# Mở Trợ lý gia sư: bấm đúp. Lần đầu cài uv, Python và thư viện (cần mạng, vài phút). Đóng cửa sổ này để tắt app.
cd "$(dirname "$0")" || exit 1
export TUTOR_DATA="${TUTOR_DATA:-$HOME/GiaSuToan}"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -x "$UV" ]; then
  echo "Đang cài uv (chỉ lần đầu)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
"$UV" run --frozen --no-dev tutor app
echo "App đã dừng. Nếu có lỗi ở trên, chụp màn hình gửi người cài. Nhấn Enter để đóng."
read -r
