#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Google Sheets Synchronization & Auto-Deployment Script
Fetches latest data for:
1. Workout records ('운동 기록') from 1prXk269ik5JTbghA5UZbh3uW56pMrzGhqnNtkrm3YKw
2. Health composition records ('건강 데이터') from 1prXk269ik5JTbghA5UZbh3uW56pMrzGhqnNtkrm3YKw
3. Reading tutoring records ('독후감 이력관리') from 1cT7wCoT8aDh01ofDRb5Sh0ANHElVRZSro5TH1-IH6d0

Rebuilds index.html and workout_dashboard.html, and if changes occur, commits and pushes to GitHub.
Can be executed:
- Automatically once a day via cron
- Manually on-demand anytime
"""

import os
import sys
import json
import datetime
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

SPREADSHEET_ID = "1prXk269ik5JTbghA5UZbh3uW56pMrzGhqnNtkrm3YKw"
SHEET_RANGE = "'운동 기록'!A1:Z500"
HEALTH_RANGE = "'건강 데이터'!A1:Z100"

READING_SPREADSHEET_ID = "1cT7wCoT8aDh01ofDRb5Sh0ANHElVRZSro5TH1-IH6d0"
READING_RANGE = "'독후감 이력관리'!A:R"

WORKOUT_FILE = os.path.join(BASE_DIR, "workout_data.json")
HEALTH_FILE = os.path.join(BASE_DIR, "health_data.json")
READING_FILE = os.path.join(BASE_DIR, "reading_data.json")


def get_sheets_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not os.path.exists(TOKEN_PATH):
        raise FileNotFoundError(f"token.json not found at {TOKEN_PATH}")

    scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('sheets', 'v4', credentials=creds, static_discovery=True)


def sync_all(push_to_git=True):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] [DailySync] 구글 시트 데이터 동기화 시작...")

    service = get_sheets_service()
    has_changes = False

    # 1. Workout data
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_RANGE,
            valueRenderOption='UNFORMATTED_VALUE',
            dateTimeRenderOption='FORMATTED_STRING'
        ).execute()
        values = res.get('values', [])
        if values:
            formatted_workout = []
            for idx, row in enumerate(values):
                cleaned_row = ["" if c is None else c for c in row]
                formatted_workout.append({"index_": idx, "row": cleaned_row})

            # Check if changed
            existing = []
            if os.path.exists(WORKOUT_FILE):
                with open(WORKOUT_FILE, "r", encoding="utf-8") as f:
                    try:
                        existing = json.load(f)
                    except Exception:
                        pass
            if json.dumps(existing, sort_keys=True) != json.dumps(formatted_workout, sort_keys=True):
                with open(WORKOUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(formatted_workout, f, ensure_ascii=False, indent=2)
                has_changes = True
                print(f"[DailySync] ✓ 운동 데이터 갱신 완료 (총 {len(formatted_workout)}행)")
            else:
                print(f"[DailySync] - 운동 데이터 변경 없음 (총 {len(formatted_workout)}행)")
    except Exception as e:
        print(f"[DailySync Error] 운동 데이터 동기화 실패: {e}")

    # 2. Health data
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=HEALTH_RANGE,
            valueRenderOption='UNFORMATTED_VALUE',
            dateTimeRenderOption='FORMATTED_STRING'
        ).execute()
        h_values = res.get('values', [])
        if h_values:
            existing = []
            if os.path.exists(HEALTH_FILE):
                with open(HEALTH_FILE, "r", encoding="utf-8") as f:
                    try:
                        existing = json.load(f)
                    except Exception:
                        pass
            if json.dumps(existing, sort_keys=True) != json.dumps(h_values, sort_keys=True):
                with open(HEALTH_FILE, "w", encoding="utf-8") as f:
                    json.dump(h_values, f, ensure_ascii=False, indent=2)
                has_changes = True
                print(f"[DailySync] ✓ 건강 데이터 갱신 완료 (총 {len(h_values)}행)")
            else:
                print(f"[DailySync] - 건강 데이터 변경 없음 (총 {len(h_values)}행)")
    except Exception as e:
        print(f"[DailySync Error] 건강 데이터 동기화 실패: {e}")

    # 3. Reading data
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=READING_SPREADSHEET_ID,
            range=READING_RANGE,
            valueRenderOption='UNFORMATTED_VALUE',
            dateTimeRenderOption='FORMATTED_STRING'
        ).execute()
        r_values = res.get('values', [])
        if r_values:
            formatted_reading = []
            for idx, r_row in enumerate(r_values):
                c_row = ["" if c is None else c for c in r_row]
                if len(c_row) < 18:
                    c_row.extend([""] * (18 - len(c_row)))
                formatted_reading.append({"index_": idx, "row": c_row})

            existing = []
            if os.path.exists(READING_FILE):
                with open(READING_FILE, "r", encoding="utf-8") as f:
                    try:
                        existing = json.load(f)
                    except Exception:
                        pass
            if json.dumps(existing, sort_keys=True) != json.dumps(formatted_reading, sort_keys=True):
                with open(READING_FILE, "w", encoding="utf-8") as f:
                    json.dump(formatted_reading, f, ensure_ascii=False, indent=2)
                has_changes = True
                print(f"[DailySync] ✓ 독서 논술 데이터 갱신 완료 (총 {len(formatted_reading)}행)")
            else:
                print(f"[DailySync] - 독서 논술 데이터 변경 없음 (총 {len(formatted_reading)}행)")
    except Exception as e:
        print(f"[DailySync Error] 독서 논술 데이터 동기화 실패: {e}")

    # 4. Rebuild HTML dashboard
    build_script = os.path.join(BASE_DIR, "build_workout_dashboard.py")
    if os.path.exists(build_script):
        try:
            subprocess.run([sys.executable, build_script], check=True, cwd=BASE_DIR)
            print("[DailySync] ✓ 대시보드 HTML 빌드 완료 (index.html, workout_dashboard.html)")
        except Exception as e:
            print(f"[DailySync Error] 대시보드 빌드 실패: {e}")

    # 5. Git Commit & Push if changes
    if push_to_git:
        try:
            status = subprocess.run(["git", "status", "--porcelain"], cwd=BASE_DIR, capture_output=True, text=True).stdout
            # Check if any data json or html files changed
            target_files = ["workout_data.json", "health_data.json", "reading_data.json", "index.html", "workout_dashboard.html"]
            needs_push = any(tf in status for tf in target_files)
            if needs_push:
                print("[DailySync] 🚀 변경사항 감지: GitHub Pages 자동 배포 푸시 시작...")
                subprocess.run(["git", "add"] + target_files, cwd=BASE_DIR, check=True)
                commit_msg = f"chore(auto-sync): Daily Google Sheets sync [{now_str}]"
                subprocess.run(["git", "commit", "-m", commit_msg], cwd=BASE_DIR, check=True)
                subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=True)
                print("[DailySync] ✓ GitHub 푸시 완료! GitHub Pages 배포 진행 중")
            else:
                print("[DailySync] Git 변경사항 없음. 푸시 생략.")
        except Exception as e:
            print(f"[DailySync Error] Git 푸시 실패: {e}")

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DailySync] 작업 완료.")
    return has_changes


if __name__ == "__main__":
    push = "--no-push" not in sys.argv
    sync_all(push_to_git=push)
