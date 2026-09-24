#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

PORT=8082
SERVER_URL="http://localhost:$PORT/workout_dashboard.html"
PYTHON_BIN="$DIR/.venv/bin/python3"

if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "========================================================"
echo " 🏃 건강 및 운동 관리 대시보드 (Workout Dashboard)"
echo "========================================================"
echo " 구글 스프레드시트 실시간 동기화 시스템"
echo " 시트: 건강 및 운동 관리 대시보드 (1prXk269ik5JTbghA5UZbh3uW56pMrzGhqnNtkrm3YKw)"
echo "========================================================"

# Check if workout_sync_server is already running
PID=$(pgrep -f "workout_sync_server.py" | head -n 1)

if [ -n "$PID" ]; then
    echo "✓ 실시간 동기화 서버가 이미 실행 중입니다 (PID: $PID)"
else
    echo "🚀 실시간 동기화 서버를 백그라운드에서 가동합니다..."
    nohup "$PYTHON_BIN" "$DIR/workout_sync_server.py" $PORT > "$DIR/workout_sync_server.log" 2>&1 &
    NEW_PID=$!
    sleep 2
    if ps -p $NEW_PID > /dev/null; then
        echo "✓ 실시간 동기화 서버 가동 완료 (PID: $NEW_PID, 포트: $PORT)"
    else
        echo "⚠️ 서버 백그라운드 가동 확인 필요 (로그: $DIR/workout_sync_server.log)"
    fi
fi

echo "🌐 웹 브라우저에서 대시보드를 엽니다: $SERVER_URL"

if command -v open >/dev/null 2>&1; then
    open "$SERVER_URL"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$SERVER_URL"
else
    echo "브라우저에서 아래 URL로 직접 접속해주세요:"
    echo "$SERVER_URL"
fi

echo "--------------------------------------------------------"
echo "💡 동기화 서버 로그 확인: tail -f $DIR/workout_sync_server.log"
echo "💡 서버 종료: pkill -f workout_sync_server.py"
echo "========================================================"
