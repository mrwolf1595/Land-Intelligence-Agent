#!/bin/bash
# ============================================================
#  Land Intelligence Agent — تشغيل كامل بأمر واحد
#  الاستخدام: bash start_all_kali.sh
#  ملاحظة: شغّل من مجلد المشروع نفسه
# ============================================================

# مجلد المشروع = المجلد الحالي (لا تعديل مطلوب)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="land-agent"
VENV="$APP_DIR/.venv/bin/activate"

echo ">>> مجلد المشروع: $APP_DIR"

# تحقق من .venv
if [ ! -f "$VENV" ]; then
  echo "خطأ: .venv غير موجود في $APP_DIR"
  echo "شغّل أولاً: cd $APP_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# تثبيت tmux لو مش موجود
if ! command -v tmux &>/dev/null; then
  sudo apt install -y tmux
fi

# تأكد من صلاحيات DB
mkdir -p "$APP_DIR/db"
touch "$APP_DIR/db/agent.db"
chmod 664 "$APP_DIR/db/agent.db"

# إيقاف جلسة قديمة
tmux kill-session -t $SESSION 2>/dev/null
echo ">>> تشغيل Land Intelligence Agent..."

# نافذة 1: Agent الرئيسي
tmux new-session -d -s $SESSION -n "agent"
tmux send-keys -t $SESSION:agent "cd $APP_DIR && source $VENV && python main.py" Enter

# نافذة 2: Dashboard
tmux new-window -t $SESSION -n "dashboard"
tmux send-keys -t $SESSION:dashboard "cd $APP_DIR && source $VENV && streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true" Enter

# نافذة 3: Logs
tmux new-window -t $SESSION -n "logs"
tmux send-keys -t $SESSION:logs "cd $APP_DIR && tail -f logs/agent.log" Enter

# ارجع لنافذة agent
tmux select-window -t $SESSION:agent

echo ""
echo "=== كل الخدمات شغالة ==="
echo ""
echo "  نافذة [agent]     - الـ agent + WhatsApp + scheduler"
echo "  نافذة [dashboard] - http://localhost:8501"
echo "  نافذة [logs]      - logs مباشر"
echo ""
echo "  tmux attach -t $SESSION   ← ادخل للجلسة (لمسح QR)"
echo "  Ctrl+B ثم 0/1/2           ← انتقل بين النوافذ"
echo "  Ctrl+B ثم D               ← اخرج وخليها شغالة"
echo ""
