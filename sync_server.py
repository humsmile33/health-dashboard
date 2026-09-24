#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Synchronization Server for Reading & Essay Tutoring Dashboard
Connects to Google Spreadsheet:
https://docs.google.com/spreadsheets/d/1cT7wCoT8aDh01ofDRb5Sh0ANHElVRZSro5TH1-IH6d0/edit?usp=sharing
Sheet: '독후감 이력관리'

Provides:
- Auto-sync background thread polling Google Sheets every 15s
- GET /api/data: returns latest synchronized reading records
- POST /api/sync: triggers immediate Google Sheets fetch and returns records
- GET /api/status: returns server status and sync metadata
- Static HTTP file server (serves reading_dashboard.html on /)
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
SPREADSHEET_ID = "1cT7wCoT8aDh01ofDRb5Sh0ANHElVRZSro5TH1-IH6d0"
SHEET_RANGE = "독후감 이력관리!A1:Z500"
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
DATA_FILE = os.path.join(BASE_DIR, "reading_data.json")

POLL_INTERVAL_SECONDS = 15
DEFAULT_PORT = 8080

# Thread-safe global cache
cache_lock = threading.Lock()
cached_records = []
last_sync_timestamp = ""
last_data_hash = ""
sync_status = "초기화 대기 중"
sync_count = 0


def load_local_cached_data():
    """Load reading_data.json if exists."""
    global cached_records, last_data_hash, last_sync_timestamp
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
            print(f"[Init] reading_data.json 캐시 로드 성공 ({len(cached_records)}건)")
        except Exception as e:
            print(f"[Warn] reading_data.json 로드 실패: {e}")


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
    """Fetch raw values from '독후감 이력관리' and update cache and file."""
    global cached_records, last_sync_timestamp, last_data_hash, sync_status, sync_count
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
            # Ensure elements are serializable (strings or numbers)
            clean_row = []
            for cell in row:
                if cell is None:
                    clean_row.append("")
                else:
                    clean_row.append(cell)
            formatted.append({"index_": i, "row": clean_row})

        content_str = json.dumps(formatted, sort_keys=True)
        cur_hash = hashlib.md5(content_str.encode("utf-8")).hexdigest()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        has_changed = (cur_hash != last_data_hash)

        with cache_lock:
            cached_records = formatted
            last_data_hash = cur_hash
            last_sync_timestamp = now_str
            sync_status = "정상 동기화됨"
            sync_count += 1

        # Write to reading_data.json
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(formatted, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[File Error] reading_data.json 저장 실패: {e}")

        if has_changed:
            print(f"[LiveSync] 🔄 구글 시트 변경사항 감지 및 갱신 완료: 총 {len(formatted)}행 ({now_str})")
        else:
            print(f"[LiveSync] ✓ 구글 시트 확인 완료 (변경사항 없음, 총 {len(formatted)}행, {now_str})")

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
            self.send_header('Location', '/reading_dashboard.html')
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
                "sheet_name": "독후감 이력관리",
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
                "status": "success" if ok else "warning",
                "message": msg,
                "synced_at": ts,
                "sync_status": st,
                "sync_count": sc,
                "spreadsheet_id": SPREADSHEET_ID,
                "sheet_name": "독후감 이력관리",
                "count": len(data_copy),
                "data": data_copy
            }
            body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200 if ok else 207)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()


def find_available_port(start_port=DEFAULT_PORT):
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port


def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    load_local_cached_data()

    # Initial sync
    print("[Init] 초기 구글 시트 데이터 동기화 시도 중...")
    fetch_and_update_from_sheets()

    # Start polling worker thread
    worker = threading.Thread(target=background_sync_worker, daemon=True)
    worker.start()

    # Start HTTP server
    server_port = find_available_port(port)
    server_address = ('0.0.0.0', server_port)
    httpd = HTTPServer(server_address, SyncServerHandler)

    print("\n" + "=" * 65)
    print(" 🚀 독서 & 논술 지도 튜터링 대시보드 실시간 동기화 서버 가동")
    print("=" * 65)
    print(f" • 로컬 대시보드 URL : http://localhost:{server_port}/reading_dashboard.html")
    print(f" • 연동 구글 시트 ID : {SPREADSHEET_ID}")
    print(f" • 연동 시트 이름     : 독후감 이력관리")
    print(f" • 자동 동기화 주기   : 매 {POLL_INTERVAL_SECONDS}초마다 실시간 체크")
    print(f" • 수동 동기화 엔드포인트 : POST http://localhost:{server_port}/api/sync")
    print("=" * 65 + "\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] 서버를 안전하게 종료합니다.")
        httpd.server_close()


if __name__ == '__main__':
    main()
