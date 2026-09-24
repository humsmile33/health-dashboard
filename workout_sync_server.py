#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Synchronization Server for Health & Fitness Workout Dashboard
Connects to Google Spreadsheet:
https://docs.google.com/spreadsheets/d/1prXk269ik5JTbghA5UZbh3uW56pMrzGhqnNtkrm3YKw/edit?usp=sharing
Sheet: '운동 기록' (and '건강 데이터')

Provides:
- Auto-sync background thread polling Google Sheets every 15s
- GET /api/data: returns latest synchronized workout records
- POST /api/sync: triggers immediate Google Sheets fetch and returns records
- GET /api/health: returns latest body composition and health records
- GET /api/status: returns server status and sync metadata
- Static HTTP file server (serves workout_dashboard.html on /)
"""

import os
import sys
import json
import time
import socket
import hashlib
import datetime
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Google API client libraries
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPREADSHEET_ID = "1prXk269ik5JTbghA5UZbh3uW56pMrzGhqnNtkrm3YKw"
SHEET_RANGE = "'운동 기록'!A1:Z500"
HEALTH_RANGE = "'건강 데이터'!A1:Z100"
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
DATA_FILE = os.path.join(BASE_DIR, "workout_data.json")
HEALTH_FILE = os.path.join(BASE_DIR, "health_data.json")

POLL_INTERVAL_SECONDS = 15
DEFAULT_PORT = 8082

# Thread-safe global cache
cache_lock = threading.Lock()
cached_records = []
cached_health_records = []
last_sync_timestamp = ""
last_data_hash = ""
sync_status = "초기화 대기 중"
sync_count = 0


def load_local_cached_data():
    """Load workout_data.json and health_data.json if they exist."""
    global cached_records, cached_health_records, last_data_hash, last_sync_timestamp
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    with cache_lock:
                        cached_records = data
                        content_str = json.dumps(data, sort_keys=True)
                        last_data_hash = hashlib.md5(content_str.encode("utf-8")).hexdigest()
                        last_sync_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[Init] workout_data.json 캐시 로드 성공 ({len(cached_records)}건)")
        except Exception as e:
            print(f"[Warn] workout_data.json 로드 실패: {e}")

    if os.path.exists(HEALTH_FILE):
        try:
            with open(HEALTH_FILE, "r", encoding="utf-8") as f:
                h_data = json.load(f)
                if isinstance(h_data, list):
                    with cache_lock:
                        cached_health_records = h_data
            print(f"[Init] health_data.json 캐시 로드 성공 ({len(cached_health_records)}건)")
        except Exception as e:
            print(f"[Warn] health_data.json 로드 실패: {e}")


def get_sheets_service():
    """Build authorized Google Sheets service from token.json."""
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('sheets', 'v4', credentials=creds, static_discovery=True)
    except Exception as e:
        print(f"[Auth Error] Google Sheets 인증 실패: {e}")
        return None


def fetch_and_update_from_sheets():
    """Fetch raw values from '운동 기록' and update cache and file."""
    global cached_records, cached_health_records, last_sync_timestamp, last_data_hash, sync_status, sync_count
    service = get_sheets_service()
    if not service:
        sync_status = "Google Sheets 인증 실패 (token.json 확인 필요)"
        return False, sync_status

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_RANGE,
            valueRenderOption='UNFORMATTED_VALUE',
            dateTimeRenderOption='FORMATTED_STRING'
        ).execute()

        values = result.get('values', [])
        if not values:
            sync_status = "스프레드시트에서 데이터를 찾을 수 없음"
            return False, sync_status

        # Convert to dashboard expected format: [{"index_": i, "row": [...]}]
        formatted = []
        for i, row in enumerate(values):
            clean_row = []
            for cell in row:
                if cell is None:
                    clean_row.append("")
                else:
                    clean_row.append(cell)
            if len(clean_row) < 9:
                clean_row.extend([""] * (9 - len(clean_row)))
            formatted.append({"index_": i, "row": clean_row})

        content_str = json.dumps(formatted, sort_keys=True)
        cur_hash = hashlib.md5(content_str.encode("utf-8")).hexdigest()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        has_changed = (cur_hash != last_data_hash)

        # Also fetch health data if available
        try:
            h_res = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=HEALTH_RANGE
            ).execute()
            h_values = h_res.get('values', [])
            if h_values:
                with open(HEALTH_FILE, "w", encoding="utf-8") as f:
                    json.dump(h_values, f, ensure_ascii=False, indent=2)
                with cache_lock:
                    cached_health_records = h_values
        except Exception as e:
            pass

        with cache_lock:
            cached_records = formatted
            last_data_hash = cur_hash
            last_sync_timestamp = now_str
            sync_status = "정상 동기화됨"
            sync_count += 1

        # Write to workout_data.json
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(formatted, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[File Error] workout_data.json 저장 실패: {e}")

        if has_changed:
            print(f"[LiveSync] 🔄 구글 시트 변경사항 감지 및 갱신 완료: 총 {len(formatted)}행 ({now_str})")
        else:
            print(f"[LiveSync] ✓ 구글 시트 확인 완료 (총 {len(formatted)}행 최신 유지, {now_str})")

        return True, f"성공적으로 {len(formatted)}행을 동기화했습니다."

    except Exception as e:
        err_msg = str(e)
        print(f"[Sync Error] 구글 시트 데이터 로드 중 오류: {err_msg}")
        with cache_lock:
            sync_status = f"오류 발생: {err_msg[:60]}"
        return False, err_msg


def background_sync_worker():
    """Background thread polling Google Sheets periodically."""
    print(f"[Worker] 구글 시트 백그라운드 자동 동기화 시작 (주기: {POLL_INTERVAL_SECONDS}초)...")
    while True:
        try:
            fetch_and_update_from_sheets()
        except Exception as e:
            print(f"[Worker Exception] {e}")
        time.sleep(POLL_INTERVAL_SECONDS)


class SyncServerHandler(SimpleHTTPRequestHandler):
    """HTTP request handler providing API endpoints and static file serving."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Enable CORS for local web interactions
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Cache-Control')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/' or parsed.path == '/index.html':
            self.send_response(302)
            self.send_header('Location', '/workout_dashboard.html')
            self.end_headers()
            return

        if parsed.path == '/api/data':
            with cache_lock:
                data_copy = list(cached_records)
                ts = last_sync_timestamp
                st = sync_status
                sc = sync_count

            response_data = {
                "status": "success",
                "synced_at": ts,
                "sync_status": st,
                "sync_count": sc,
                "spreadsheet_id": SPREADSHEET_ID,
                "sheet_name": "운동 기록",
                "count": len(data_copy),
                "data": data_copy
            }
            body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == '/api/health':
            with cache_lock:
                h_copy = list(cached_health_records)
            response_data = {
                "status": "success",
                "count": len(h_copy),
                "data": h_copy
            }
            body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == '/api/status':
            with cache_lock:
                status_info = {
                    "status": "online",
                    "synced_at": last_sync_timestamp,
                    "sync_status": sync_status,
                    "sync_count": sync_count,
                    "count": len(cached_records),
                    "spreadsheet_id": SPREADSHEET_ID,
                    "sheet_url": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
                }
            body = json.dumps(status_info, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Fallback to standard static file serving
        return super().do_GET()

    def do_POST(self):
        global cached_records, last_data_hash, last_sync_timestamp
        parsed = urlparse(self.path)

        if parsed.path == '/api/sync':
            print("[API] 🔄 클라이언트로부터 즉시 동기화(POST /api/sync) 요청 수신")
            ok, msg = fetch_and_update_from_sheets()

            with cache_lock:
                data_copy = list(cached_records)
                ts = last_sync_timestamp
                st = sync_status
                sc = sync_count

            response_data = {
                "status": "success" if ok else "error",
                "message": msg,
                "synced_at": ts,
                "sync_status": st,
                "sync_count": sc,
                "count": len(data_copy),
                "data": data_copy
            }
            body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200 if ok else 500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Handle local save / update if provided
        if parsed.path in ('/api/save', '/api/update'):
            content_length = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_length).decode('utf-8')
            try:
                payload = json.loads(post_body)
                if isinstance(payload, list):
                    with cache_lock:
                        cached_records = payload
                        last_data_hash = hashlib.md5(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()
                        last_sync_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with open(DATA_FILE, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                    res = {"status": "success", "message": f"{len(payload)}개 기록 로컬 캐시 갱신 완료"}
                else:
                    res = {"status": "error", "message": "Payload must be a list"}
            except Exception as e:
                res = {"status": "error", "message": str(e)}

            body = json.dumps(res, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def run_server(port=DEFAULT_PORT):
    load_local_cached_data()

    # Perform initial fetch from Google Sheets
    print("[Server] 🚀 구글 시트 최초 데이터 동기화 시도 중...")
    ok, msg = fetch_and_update_from_sheets()
    if ok:
        print(f"[Server] ✓ 구글 시트 최초 동기화 완료: {msg}")
    else:
        print(f"[Server] ⚠️ 구글 시트 동기화 실패 (로컬 캐시 사용): {msg}")

    # Start background polling thread
    worker_thread = threading.Thread(target=background_sync_worker, daemon=True)
    worker_thread.start()

    server_address = ('', port)
    httpd = HTTPServer(server_address, SyncServerHandler)
    print(f"\n========================================================")
    print(f" 🏃 건강 및 운동 관리 대시보드 실시간 동기화 서버 가동")
    print(f"========================================================")
    print(f" - 포트: http://localhost:{port}/")
    print(f" - 대시보드 URL: http://localhost:{port}/workout_dashboard.html")
    print(f" - 시트 ID: {SPREADSHEET_ID} ('운동 기록')")
    print(f" - 자동 동기화 주기: {POLL_INTERVAL_SECONDS}초")
    print(f"========================================================\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] 서버를 종료합니다.")
        httpd.server_close()


if __name__ == '__main__':
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    if is_port_in_use(port):
        print(f"[Notice] 포트 {port}가 이미 사용 중입니다. 기존 프로세스를 확인하거나 다른 포트를 사용해주세요.")
        sys.exit(0)

    run_server(port)
