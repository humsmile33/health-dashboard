#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import datetime
import base64
import urllib.parse
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
import feedparser
from jinja2 import Environment, FileSystemLoader

# Google API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

# Scopes required for Google APIs
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

WEATHER_CODES = {
    0: ("☀️", "맑음"),
    1: ("🌤️", "대체로 맑음"),
    2: ("⛅", "구름 조금"),
    3: ("☁️", "흐림"),
    45: ("🌫️", "안개"),
    48: ("🌫️", "침적 안개"),
    51: ("🌧️", "가벼운 이슬비"),
    53: ("🌧️", "이슬비"),
    55: ("🌧️", "강한 이슬비"),
    61: ("☔", "약한 비"),
    63: ("☔", "비"),
    65: ("☔", "강한 비"),
    71: ("❄️", "약한 눈"),
    73: ("❄️", "눈"),
    75: ("❄️", "강한 눈"),
    77: ("❄️", "싸락눈"),
    80: ("🌦️", "약한 소나기"),
    81: ("🌦️", "소나기"),
    82: ("🌦️", "강한 소나기"),
    85: ("🌨️", "약한 눈 소나기"),
    86: ("🌨️", "눈 소나기"),
    95: ("⚡", "뇌우"),
    96: ("⚡", "우박을 동반한 약한 뇌우"),
    99: ("⚡", "우박을 동반한 강한 뇌우")
}

KOREAN_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

def get_google_services():
    """Initializes Google API services using local credentials.json."""
    if not GOOGLE_LIBS_AVAILABLE:
        print("[Warn] Google libraries not installed. Running in DEMO mode.")
        return None, None, None, None

    creds = None
    # Token cache file
    token_path = 'token.json'
    credentials_path = 'credentials.json'

    if os.path.exists(token_path):
        try:
            # Read raw JSON scopes to verify they match SCOPES
            with open(token_path, 'r') as f:
                token_data = json.load(f)
            token_scopes = token_data.get('scopes', [])
            if not all(scope in token_scopes for scope in SCOPES):
                print("[Info] Token scopes are outdated. Forcing re-authentication...")
                creds = None
                try:
                    os.remove(token_path)
                except OSError:
                    pass
            else:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            print(f"[Warn] Failed to load token.json: {e}")
            creds = None

    # If credentials are not valid or do not exist, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[Warn] Failed to refresh token: {e}")
                creds = None

        if not creds:
            if not os.path.exists(credentials_path):
                print(f"[Info] '{credentials_path}' not found. Google integration is disabled. Running in DEMO mode.")
                return None, None, None, None
            try:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                print(f"[Error] Failed to complete authentication flow: {e}")
                return None, None, None, None

    try:
        # Prevent hangs during discovery load by specifying static_discovery=True
        sheets_service = build('sheets', 'v4', credentials=creds, static_discovery=True)
        calendar_service = build('calendar', 'v3', credentials=creds, static_discovery=True)
        drive_service = build('drive', 'v3', credentials=creds, static_discovery=True)
        gmail_service = build('gmail', 'v1', credentials=creds, static_discovery=True)
        return sheets_service, calendar_service, drive_service, gmail_service
    except Exception as e:
        print(f"[Error] Failed to build Google API services: {e}")
        return None, None, None, None

def find_spreadsheet_id(drive_service, name="은퇴자산계좌5"):
    """Finds the ID of the spreadsheet with the given name."""
    if not drive_service:
        return None
    try:
        query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.spreadsheet'"
        results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        if not files:
            print(f"[Warn] Spreadsheet named '{name}' not found in Google Drive.")
            return None
        return files[0]['id']
    except Exception as e:
        print(f"[Error] Failed to find spreadsheet '{name}': {e}")
        return None

def parse_value(val_str):
    """Parses a percentage or currency string to a float."""
    if not val_str:
        return 0.0
    val_clean = val_str.replace('₩', '').replace('%', '').replace(',', '').strip()
    try:
        return float(val_clean)
    except ValueError:
        return 0.0

def calculate_comparison(curr_val, prev_val):
    """Calculates difference and formats comparison string."""
    if not curr_val or not prev_val:
        return {"text": "", "class": ""}
    
    is_percentage = '%' in curr_val or '%' in prev_val
    is_won = '₩' in curr_val or '₩' in prev_val or curr_val.startswith('₩') or prev_val.startswith('₩')
    
    c_num = parse_value(curr_val)
    p_num = parse_value(prev_val)
    
    diff = c_num - p_num
    
    if diff > 0.0001:
        arrow = "▲"
        color_class = "text-emerald-400"
    elif diff < -0.0001:
        arrow = "▼"
        color_class = "text-rose-400"
    else:
        arrow = "-"
        color_class = "text-slate-500"
        
    diff_abs = abs(diff)
    
    if is_percentage:
        diff_str = f"{arrow}{diff_abs:.2f}%"
    elif is_won:
        diff_str = f"{arrow}₩{int(round(diff_abs)):,}"
    else:
        if diff_abs == int(diff_abs):
            diff_str = f"{arrow}{int(diff_abs)}"
        else:
            diff_str = f"{arrow}{diff_abs:.2f}"
            
    return {"text": f"({diff_str})", "class": color_class}

def fetch_sheets_data(sheets_service, spreadsheet_id):
    """Fetches asset data from Google Sheets and filters high-volatility ones."""
    summary_data = {'headers': [], 'values': [], 'comparisons': []}
    high_volatility_assets = []

    if not sheets_service or not spreadsheet_id:
        return get_mock_sheets_data()

    # 1. Fetch '1.종합시트'!A1:U2
    try:
        range_name = '1.종합시트!A1:U2'
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name
        ).execute()
        rows = result.get('values', [])
        if len(rows) >= 2:
            headers = rows[0]
            values = rows[1]
            
            for h, v in zip(headers, values):
                h_clean = h.strip()
                if h_clean:
                    # Skip numeric headers
                    try:
                        float(h_clean)
                        continue
                    except ValueError:
                        pass
                    summary_data['headers'].append(h_clean)
                    summary_data['values'].append(v.strip())
        else:
            print("[Warn] '1.종합시트!A1:U2' returned insufficient rows.")
    except Exception as e:
        print(f"[Error] Failed to fetch data from '1.종합시트': {e}")

    # 2. Fetch '2.자산변동률'!A1:AO600 for comparisons
    change_rows = []
    try:
        range_name = '2.자산변동률!A1:AO600'
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name
        ).execute()
        change_rows = result.get('values', [])
    except Exception as e:
        print(f"[Error] Failed to fetch data from '2.자산변동률': {e}")

    headers_change = []
    data_rows = []
    if len(change_rows) >= 2:
        headers_change = [h.strip() for h in change_rows[1]]
        for r_idx, row in enumerate(change_rows):
            if r_idx < 2:
                continue
            if len(row) > 1 and row[1].strip():
                data_rows.append((r_idx, row))

    # 오늘 날짜 행 인덱스 찾기
    today_date_std = datetime.date.today().strftime("%Y. %-m. %-d")
    today_row_idx_in_data = -1
    for i, (orig_idx, row) in enumerate(data_rows):
        if row[1].strip() == today_date_std:
            today_row_idx_in_data = i
            break

    # 직전 값 검색 기준 인덱스 설정
    if today_row_idx_in_data != -1:
        search_start_idx = today_row_idx_in_data - 1
    else:
        search_start_idx = len(data_rows) - 1

    # Map summary header to change sheet header
    MAP_SUMMARY_TO_CHANGE = {
        '년초대비수익률': '년초대비수익률',
        '직전대비 수익금변동': '일별수익금변동',
        '년초대비수익금': '년초대비수익금',
        '총누적수익': '총차익금',
        '미국 수익률': '미국자산배분수익률',
        '한국 수익률': '국내자산배분수익률',
        'KOSPI': 'KOSPI',
        'S&P 500': 'S&P',
        '비트코인': '비트코인',
        '금': '금',
        '원유': '원유'
    }

    # Calculate comparisons (scans backwards to skip errors/empty values)
    for h, v in zip(summary_data['headers'], summary_data['values']):
        comp_info = {"text": "", "class": ""}
        if h == '총누적수익률':
            # 총누적수익률은 비교 제외
            summary_data['comparisons'].append(comp_info)
            continue

        if h in MAP_SUMMARY_TO_CHANGE and headers_change:
            change_col_name = MAP_SUMMARY_TO_CHANGE[h]
            if change_col_name in headers_change:
                col_idx = headers_change.index(change_col_name)
                
                prev_val = None
                for i in range(search_start_idx, -1, -1):
                    _, row_data = data_rows[i]
                    if col_idx < len(row_data):
                        val_candidate = row_data[col_idx].strip()
                        # Skip empty, #N/A, #NUM!, #DIV/0!
                        if val_candidate and not any(err in val_candidate for err in ['#N/A', '#NUM!', '#DIV/0!', 'error', 'Error']):
                            prev_val = val_candidate
                            break
                            
                if prev_val is not None:
                    comp_info = calculate_comparison(v, prev_val)
        summary_data['comparisons'].append(comp_info)

    # 3. Fetch '1.종합시트'!C6:J125 for 3% threshold check
    try:
        range_name = '1.종합시트!C6:J125'
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name
        ).execute()
        assets_c6_j125 = result.get('values', [])
        
        seen_names = set()
        if assets_c6_j125 and len(assets_c6_j125) > 1:
            for row in assets_c6_j125[1:]:
                if not row or len(row) < 8:
                    continue
                symbol = row[0].strip()
                desc = row[1].strip()
                yield_val = row[5].strip()
                change_val = row[7].strip()
                
                try:
                    val_clean = change_val.replace('%', '').replace(',', '').strip()
                    val_float = float(val_clean)
                    if abs(val_float) >= 3.0:
                        name = symbol
                        if not symbol:
                            name = desc
                        elif symbol.isdigit():
                            name = f"{symbol} ({desc})"
                        
                        if name not in seen_names:
                            seen_names.add(name)
                            high_volatility_assets.append({
                                'name': name,
                                'change': change_val,
                                'yield': yield_val,
                                'change_float': val_float
                            })
                except ValueError:
                    pass
    except Exception as e:
        print(f"[Error] Failed to fetch data from '1.종합시트!C6:J125': {e}")

    # Fallback to mock if empty
    if not summary_data['headers']:
        print("[Info] Sheet data is empty, using Mock Data instead.")
        return get_mock_sheets_data()

    # Sort high-volatility assets by daily change percentage (absolute values) in descending order
    high_volatility_assets.sort(key=lambda x: abs(x['change_float']), reverse=True)

    return summary_data, high_volatility_assets

def get_mock_sheets_data():
    """Generates mock asset data for DEMO mode."""
    headers = ["총자산", "년초대비수익률", "직전대비 수익금변동", "년초대비수익금", "총누적수익", "미국 수익률", "한국 수익률", "총누적수익률", "KOSPI", "S&P 500", "비트코인", "금", "원유"]
    values = ["₩842,500,000", "9.43%", "₩103,508", "₩43,029,949", "₩127,769,569", "30.81%", "39.54%", "28.00%", "106.30%", "8.57%", "-25.55%", "-2.91%", "74.78%"]
    comparisons = [
        {"text": "(▲₩1,200,000)", "class": "text-emerald-400"},
        {"text": "(▲0.02%)", "class": "text-emerald-400"},
        {"text": "(▲₩103,508)", "class": "text-emerald-400"},
        {"text": "(▲₩5,000,000)", "class": "text-emerald-400"},
        {"text": "(▲₩12,000,000)", "class": "text-emerald-400"},
        {"text": "(▲0.16%)", "class": "text-emerald-400"},
        {"text": "(▼0.12%)", "class": "text-rose-400"},
        {"text": "", "class": ""},
        {"text": "(▲0.02%)", "class": "text-emerald-400"},
        {"text": "(▲0.11%)", "class": "text-emerald-400"},
        {"text": "(▼1.23%)", "class": "text-rose-400"},
        {"text": "(▲0.45%)", "class": "text-emerald-400"},
        {"text": "(▼0.82%)", "class": "text-rose-400"},
    ]
    summary_data = {'headers': headers, 'values': values, 'comparisons': comparisons}

    high_volatility_assets = [
        {'name': '497570 (TIGER 미국필라델피아AI반도체나스닥)', 'change': '4.24%', 'yield': '51.56%', 'change_float': 4.24},
        {'name': '삼성전자', 'change': '7.86%', 'yield': '442.52%', 'change_float': 7.86},
        {'name': 'lg에너지솔루션', 'change': '4.03%', 'yield': '33.97%', 'change_float': 4.03},
        {'name': '네이버', 'change': '10.27%', 'yield': '16.50%', 'change_float': 10.27},
        {'name': '셀트리온', 'change': '4.09%', 'yield': '-5.68%', 'change_float': 4.09},
        {'name': '두산에너빌리티', 'change': '5.08%', 'yield': '-10.20%', 'change_float': 5.08},
        {'name': '한화시스템', 'change': '8.35%', 'yield': '0.52%', 'change_float': 8.35},
        {'name': '카카오', 'change': '5.60%', 'yield': '4.16%', 'change_float': 5.60}
    ]
    # Sort mock data as well to align UI
    high_volatility_assets.sort(key=lambda x: abs(x['change_float']), reverse=True)

    return summary_data, high_volatility_assets


def fetch_calendar_events(calendar_service):
    """Fetches Google Calendar events from all user's calendars for the next 7 days."""
    if not calendar_service:
        # Provide Mock Data for DEMO mode
        return get_mock_calendar_events()

    events_list = []
    try:
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        time_max = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat() + 'Z'
        
        # 1. Fetch the list of all calendars the user has access to
        calendar_list = calendar_service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])
        
        raw_events = []
        for cal in calendars:
            cal_id = cal['id']
            # Fetch events for each calendar
            try:
                events_result = calendar_service.events().list(
                    calendarId=cal_id, timeMin=now, timeMax=time_max,
                    singleEvents=True, orderBy='startTime'
                ).execute()
                raw_events.extend(events_result.get('items', []))
            except Exception:
                # Some system calendars or read-only calendars might fail, skip gracefully
                continue

        # Deduplicate events (by ID) and sort chronologically
        seen_event_ids = set()
        for event in raw_events:
            event_id = event.get('id')
            if not event_id or event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            
            start_raw = event['start'].get('dateTime', event['start'].get('date'))
            
            # Create datetime sorting key
            if 'T' in start_raw:
                dt = datetime.datetime.fromisoformat(start_raw.replace('Z', '+00:00'))
                dt_local = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
                sort_key = dt_local
                weekday = KOREAN_WEEKDAYS[dt_local.weekday()]
                start_formatted = dt_local.strftime(f"%m월 %d일 ({weekday}) %H:%M")
            else:
                dt = datetime.datetime.strptime(start_raw, "%Y-%m-%d")
                dt_local = datetime.datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
                sort_key = dt_local
                weekday = KOREAN_WEEKDAYS[dt.weekday()]
                start_formatted = dt.strftime(f"%m월 %d일 ({weekday}) 하루 종일")

            events_list.append({
                'sort_key': sort_key,
                'start': start_formatted,
                'summary': event.get('summary', '제목 없음'),
                'description': event.get('description', ''),
                'location': event.get('location', '')
            })
            
        # Sort chronologically
        events_list.sort(key=lambda x: x['sort_key'])
        
        # Clean sort_key from items
        for ev in events_list:
            ev.pop('sort_key', None)
            
    except Exception as e:
        print(f"[Error] Failed to fetch Google Calendar events: {e}")
        return get_mock_calendar_events()

    return events_list

def get_mock_calendar_events():
    """Generates mock calendar events for DEMO mode."""
    today = datetime.datetime.now()
    events = []
    
    # Generate some mock events for the next few days
    days_offset = [0, 1, 3, 5]
    summaries = [
        "은퇴 연금 포트폴리오 정기 리밸런싱",
        "동탄 입주자 대표 회의",
        "세무사 미팅 (양도소득세 상담)",
        "가족 주말 저녁 식사 약속"
    ]
    descriptions = [
        "1.종합시트와 25.Review 시트를 기반으로 하여 자산 비중 조정 검토.",
        "오후 8시 관리사무소 회의실. 안건: 커뮤니티 센터 운영 건.",
        "오전 10시 세무법인 사무실 방문. 지참 서류: 매매계약서, 등기부등본.",
        "오후 6시 동탄 호수공원 근처 이탈리안 레스토랑 예약 완료."
    ]
    locations = [
        "서재",
        "단지 내 관리사무소",
        "강남역 세무법인 지평",
        "동탄 쁘띠쉐프"
    ]

    for i, offset in enumerate(days_offset):
        event_date = today + datetime.timedelta(days=offset)
        weekday = KOREAN_WEEKDAYS[event_date.weekday()]
        
        if i == 0:
            start_str = event_date.strftime(f"%m월 %d일 ({weekday}) 10:00")
        elif i == 1:
            start_str = event_date.strftime(f"%m월 %d일 ({weekday}) 20:00")
        elif i == 2:
            start_str = event_date.strftime(f"%m월 %d일 ({weekday}) 14:00")
        else:
            start_str = event_date.strftime(f"%m월 %d일 ({weekday}) 18:00")

        events.append({
            'start': start_str,
            'summary': summaries[i],
            'description': descriptions[i],
            'location': locations[i]
        })
    return events

def fetch_weather_data():
    """Fetches weather forecast for Dongtan, Hwaseong from Open-Meteo API."""
    # Dongtan (Hwanggye-dong, Hwaseong) Coordinates
    lat, lon = 37.1872, 127.0984
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Asia/Seoul"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            daily_data = data.get('daily', {})
            
            dates = daily_data.get('time', [])
            weathercodes = daily_data.get('weathercode', [])
            temp_maxs = daily_data.get('temperature_2m_max', [])
            temp_mins = daily_data.get('temperature_2m_min', [])
            precipitation_probs = daily_data.get('precipitation_probability_max', [])
            
            parsed_days = []
            for i in range(len(dates)):
                dt = datetime.datetime.strptime(dates[i], "%Y-%m-%d")
                weekday = KOREAN_WEEKDAYS[dt.weekday()]
                
                code = weathercodes[i] if i < len(weathercodes) else 0
                icon, desc = WEATHER_CODES.get(code, ("❓", "정보 없음"))
                
                parsed_days.append({
                    'date': dt.strftime("%m/%d"),
                    'day_of_week': weekday,
                    'icon_emoji': icon,
                    'desc': desc,
                    'temp_max': temp_maxs[i] if i < len(temp_maxs) else 0,
                    'temp_min': temp_mins[i] if i < len(temp_mins) else 0,
                    'rain_prob': precipitation_probs[i] if i < len(precipitation_probs) else 0
                })
            
            return {'daily': parsed_days}
        else:
            print(f"[Error] Weather API returned status code {response.status_code}")
    except Exception as e:
        print(f"[Error] Failed to fetch weather data: {e}")
        
    return get_mock_weather_data()

def get_mock_weather_data():
    """Generates mock weather data in case of API failure."""
    today = datetime.date.today()
    parsed_days = []
    
    mock_codes = [0, 1, 2, 3, 61, 80, 2]
    mock_maxs = [28, 29, 27, 25, 24, 26, 27]
    mock_mins = [18, 19, 18, 17, 16, 17, 18]
    mock_pops = [0, 10, 20, 40, 80, 60, 20]
    
    for i in range(7):
        dt = today + datetime.timedelta(days=i)
        weekday = KOREAN_WEEKDAYS[dt.weekday()]
        code = mock_codes[i]
        icon, desc = WEATHER_CODES.get(code, ("❓", "정보 없음"))
        
        parsed_days.append({
            'date': dt.strftime("%m/%d"),
            'day_of_week': weekday,
            'icon_emoji': icon,
            'desc': desc,
            'temp_max': mock_maxs[i],
            'temp_min': mock_mins[i],
            'rain_prob': mock_pops[i]
        })
    return {'daily': parsed_days}

def is_english(text):
    import re
    has_english = bool(re.search(r'[a-zA-Z]', text))
    has_korean = bool(re.search(r'[\uac00-\ud7a3\u3131-\u318e]', text))
    return has_english and not has_korean

def translate_text_free(text, target_lang='ko'):
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={urllib.parse.quote(text)}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            translated = "".join([part[0] for part in data[0] if part[0]])
            return translated
    except Exception as e:
        print(f"[Warn] Free translation failed: {e}")
    return text

def analyze_sentiment(title, snippet):
    """Classifies financial/economic article sentiment as 긍정, 부정, or 중립."""
    text = (title + " " + snippet).lower()
    
    neg_keywords = [
        '우려', '약세', '분사', '하락', '폭락', '악화', '급락', '방출', '수익성', 
        '마진 잠식', '부담', '감원', '파업', '갈등', '실수', '리스크', '붕괴', 
        '와르르', '반토막', '최저', '손실', '적자', '경고', '위기', '둔화', '감소', 
        '비관', '비대화', '부진', '제한', '압박', '경계', 'unsub', 'edit', 'error', 
        'reject', 'decline', 'drop', 'fall', 'dump', 'loss', 'worry', 'threat', 
        'layoff', 'strike', 'conflict', 'collapse', 'risk', 'deficit', 'slowdown'
    ]
    
    pos_keywords = [
        '상승', '인기', '개선', '수주', '안정화', '호재', '반등', '급증', '성공', 
        '최대', '돌풍', '성장', '확장', '확대', '호조', '이익', '흑자', '인도', 
        '안착', '선두', '초격차', '독점', '상장', '강화', '회복', '진전', '최고', 
        'leads', 'surpasses', 'win', 'beat', 'rise', 'growth', 'surge', 'boom', 
        'success', 'profit', 'expansion', 'strengthen', 'gain', 'jump', 'rebound'
    ]
    
    neg_score = sum(1 for kw in neg_keywords if kw in text)
    pos_score = sum(1 for kw in pos_keywords if kw in text)
    
    if neg_score > pos_score:
        return '부정'
    elif pos_score > neg_score:
        return '긍정'
    else:
        return '중립'

def generate_news_briefing(alerts_data):
    """Generates a daily brief summary of all news articles in 3-4 sentences."""
    api_key = os.environ.get('GEMINI_API_KEY')
    
    summary_text = ""
    for group in alerts_data:
        summary_text += f"\n주제: {group['topic']}\n"
        for art in group['articles']:
            summary_text += f"- {art['title']}: {art['snippet']}\n"
            
    if not summary_text.strip():
        return "오늘 주요 스크랩 소식이 없습니다. 새 구글 알리미 뉴스가 도착하면 여기에 분석 브리핑이 표시됩니다."
        
    if api_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"""
당신은 시니어 자산운용가이자 일류 금융/경제 평론가입니다.
오늘 스크랩된 아래의 뉴스 목록을 바탕으로, 자산 관리자 입장에서 오늘 하루 동안 가장 예리하고 날카롭게 눈여겨보아야 할 핵심 이슈와 전반적인 기사 동향(비용 리스크, AI 패권 구도, 거시경제 등)을 3~4문장의 프로페셔널한 서술형 줄글로 요약하여 브리핑해 주세요.
절대 식상하거나 뻔한 권고("모니터링하세요", "주의 깊게 살피세요") 대신, 시장 흐름의 이면을 짚는 날카롭고 직설적인 어조로 작성해야 합니다.
반드시 한국어로 작성하고, 4문장 이하로 제한합니다.

[뉴스 목록]
{summary_text}
"""
        try:
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            response = requests.post(url, headers=headers, json=payload, timeout=8)
            if response.status_code == 200:
                res_data = response.json()
                briefing = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                return briefing
        except Exception as e:
            print(f"[Warn] Gemini news briefing failed: {e}")
            
    # Fallback: Advanced Rule-Based Analytical Synthesis
    detected_topics = {group['topic'].lower() for group in alerts_data}
    sentences = []
    
    # 1. Broad Macro/Core Trend sentence
    if any(t in detected_topics for t in ['nvidia', '마이크로소프트', '오라클', 'ai']):
        sentences.append("금일 동향은 빅테크 기업들의 선단 AI 인프라 장악 경쟁 속에서 천문학적인 설비투자(CAPEX) 비용 비대화 우려와 마진 잠식 리스크가 공존하고 있음을 예리하게 보여줍니다.")
    elif any(t in detected_topics for t in ['비트코인', '금', '환율', 'cnh']):
        sentences.append("금일 동향은 안전자산인 금의 가격 변동성과 환율 하락 합의 기대감, 그리고 비트코인 등 고위험 자산의 지지선 붕괴가 맞물리며 매크로 불확실성이 극대화되는 국면입니다.")
    else:
        sentences.append("금일 시장 동향은 개별 산업군에서의 노사 리스크와 틈새공정 제품 라인업 확장 등 업황 변동성에 대응하기 위한 개별 기업들의 생존 게임이 심화되고 있습니다.")
        
    # 2. Key highlight article focus
    highlight_sent = ""
    if 'nvidia' in detected_topics:
        highlight_sent = "특히 NVIDIA가 Blackwell 아키텍처와 Agentic AI 벤치마크에서 초격차 독점을 예고한 반면, 마이크로소프트와 오라클 등은 자본 지출 우려로 주가 압박을 받고 있어 이들의 실적 이면을 냉정하게 주시해야 합니다."
    elif '비트코인' in detected_topics:
        highlight_sent = "특히 비트코인이 전고점 대비 반토막 수준인 6만 달러선 붕괴를 맞이하며 레버리지 청산과 위험자산 회피 성향이 극에 달해 있어 단기 투매 세력에 휩쓸리지 않는 이성적 대응이 절대적입니다."
    elif '환율' in detected_topics:
        highlight_sent = "특히 달러-원 환율이 종전 합의 임박 기대감으로 급변동성을 보이는 시점이므로 외환 노출도가 높은 자산군에 대한 단기 리스크 헷징이 최우선 과제입니다."
    elif '카카오' in detected_topics or '네이버' in detected_topics:
        highlight_sent = "특히 국내 테크 리더(카카오, 네이버)들의 노사 갈등 및 AI 로드맵의 구조적 정체는 글로벌 빅테크와의 격차를 더욱 벌리고 있어 자산 배분 비중 축소를 심각하게 고민해야 할 시점입니다."
        
    if highlight_sent:
        sentences.append(highlight_sent)
        
    # 3. Third Actionable/Sharp Insight sentence
    if '테슬라' in detected_topics:
        sentences.append("테슬라는 스페이스X의 성공적 데뷔가 하방을 받치고 있으나 본업의 마진 악화 압박은 해소되지 않았으므로 밸류에이션 리스크를 경계해야 합니다.")
    elif '금' in detected_topics:
        sentences.append("금 가격의 6개월 만의 최저점 폭락은 전통적인 안전자산 공식의 붕괴를 경고하며 고금리 장기화 기조하의 자산 재배치 압박을 가중시키고 있습니다.")
        
    # 4. Final sharp punchy summary (ensure total sentences <= 4)
    sentences.append("결론적으로 단기적인 낙폭 과대에 따른 매수 유혹보다는 비용 부담 리스크와 매크로 지지선 붕괴 조짐을 면밀히 분별하여 자산 방어에 치중할 것을 권고합니다.")
    
    return " ".join(sentences[:4])

def parse_google_alert_html(html_content, default_topic):
    """Parses Google Alert HTML to extract categorized article groups."""
    from bs4 import BeautifulSoup
    import urllib.parse
    import re

    groups = []
    current_group = None
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        tds = soup.find_all('td')
        
        # Check if the HTML body contains any topic headers
        has_body_headers = False
        exclude_headers = ["뉴스", "웹", "비디오", "블로그", "도서", "학술자료", "토론", "신고", "알림"]
        
        for td in tds:
            style = td.get('style', '')
            text = td.get_text(" ", strip=True)
            if 'padding:18px 0px 0px 0px' in style or 'padding:24px 0px 0px 0px' in style:
                if not td.find('a') and 0 < len(text) < 50:
                    clean_text = re.sub(r'\s+', ' ', text).strip()
                    if clean_text.lower() not in [h.lower() for h in exclude_headers]:
                        has_body_headers = True
                        break
                        
        # Parse sequentially
        for td in tds:
            style = td.get('style', '')
            text = td.get_text(" ", strip=True)
            
            # Detect topic header
            is_header = False
            if has_body_headers:
                if 'padding:18px 0px 0px 0px' in style or 'padding:24px 0px 0px 0px' in style:
                    if not td.find('a') and 0 < len(text) < 50:
                        clean_text = re.sub(r'\s+', ' ', text).strip()
                        if clean_text.lower() not in [h.lower() for h in exclude_headers]:
                            is_header = True
                            
            if is_header:
                topic_name = re.sub(r'\s+', ' ', text).strip()
                current_group = {
                    'topic': topic_name,
                    'articles': []
                }
                groups.append(current_group)
                continue
                
            # Check if TD contains article links
            links = td.find_all('a')
            for link in links:
                href = link.get('href', '')
                if 'google.com/url' in href:
                    title = link.get_text(" ", strip=True)
                    if not title or len(title) < 5:
                        continue
                        
                    # Decode target URL
                    parsed_href = urllib.parse.urlparse(href)
                    params = urllib.parse.parse_qs(parsed_href.query)
                    real_url = params.get('url', [None])[0]
                    if not real_url:
                        real_url = href
                        
                    # Target group routing
                    target_group = current_group
                    if not has_body_headers:
                        # Fallback for single topic alerts
                        if not groups:
                            groups.append({
                                'topic': default_topic,
                                'articles': []
                            })
                        target_group = groups[0]
                        
                    if not target_group:
                        continue
                        
                    # Deduplicate links in current group
                    if real_url in [a['link'] for a in target_group['articles']]:
                        continue
                        
                    # Extract snippet
                    td_text = td.get_text(" ", strip=True)
                    clean_text = " ".join(td_text.split())
                    clean_title = " ".join(title.split())
                    
                    if clean_title in clean_text:
                        snippet = clean_text.replace(clean_title, "", 1).strip()
                    else:
                        snippet = clean_text
                        
                    snippet = snippet.replace("관련성 없는 검색결과 신고", "").strip()
                    snippet = re.sub(r'\s+', ' ', snippet)
                    
                    # Clean title
                    clean_title = clean_title.replace("관련성 없는 검색결과 신고", "").strip()
                    clean_title = re.sub(r'\s+', ' ', clean_title)
                    
                    # If title is in English, translate it
                    if is_english(clean_title):
                        translated = translate_text_free(clean_title)
                        if translated != clean_title:
                            clean_title = f"[번역] {translated} ({clean_title})"
                            
                    # Skip administrative or irrelevant articles
                    exclude_keywords = ["알리미 수정", "비공식", "설정", "신고", "취소", "unsub", "edit", "google", "알리미 탈퇴", "자산변동률", "종합시트"]
                    title_lower = clean_title.lower()
                    if any(kw in title_lower for kw in exclude_keywords):
                        continue
                        
                    sentiment = analyze_sentiment(clean_title, snippet)
                    target_group['articles'].append({
                        'title': clean_title,
                        'link': real_url,
                        'snippet': snippet if snippet else "설명이 제공되지 않습니다.",
                        'sentiment': sentiment
                    })
                    
        # Filter groups with valid articles
        groups = [g for g in groups if g['articles']]
        return groups
    except Exception as e:
        print(f"[Error] Failed to parse Google Alert HTML: {e}")
        return []

def get_mock_google_alerts():
    """Generates mock Google Alerts data for DEMO mode or API fallback."""
    return [
        {
            'topic': '은퇴 자산',
            'date': '2026-06-20',
            'articles': [
                {
                    'title': '은퇴자산 10억 모으기 프로젝트: 실제 달성 전략 및 자산 배분',
                    'link': 'https://news.google.com',
                    'snippet': '은퇴를 준비하는 4050 세대를 위해 자산 10억 원을 모으기 위한 연금저축, IRP, 미국 배당주 포트폴리오 다변화 전략을 구체적으로 알아봅니다.',
                    'sentiment': 'neutral'
                }
            ]
        },
        {
            'topic': '반도체 시장',
            'date': '2026-06-20',
            'articles': [
                {
                    'title': '[번역] 엔비디아 차세대 AI 칩 블랙웰 출하량 증가 및 TSMC 수혜 전망 (NVIDIA Blackwell Shipments Surge)',
                    'link': 'https://news.google.com',
                    'snippet': '엔비디아의 새로운 AI 가속기 칩인 블랙웰의 수요가 강력하여 하반기 TSMC의 위탁 생산량이 예상을 크게 웃돌 것으로 보입니다.',
                    'sentiment': 'positive'
                }
            ]
        }
    ]

def fetch_google_alerts(gmail_service):
    """Fetches and parses Google Alerts from the user's Gmail inbox."""
    if not gmail_service:
        print("[Info] Gmail service not available. Defaulting to mock alerts.")
        return get_mock_google_alerts()
    
    try:
        # Search for messages from Google Alerts (googlealerts-noreply@google.com)
        # Fetch up to 50 messages to cover all alert categories registered by the user
        query = 'from:googlealerts-noreply@google.com'
        results = gmail_service.users().messages().list(userId='me', q=query, maxResults=50).execute()
        messages = results.get('messages', [])
        
        if not messages:
            print("[Info] No Google Alerts emails found. Defaulting to mock alerts.")
            return get_mock_google_alerts()
            
        alerts_dict = {}
        for msg in messages:
            msg_id = msg['id']
            message = gmail_service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            
            # Extract subject and date headers
            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            subject = ""
            date_str = ""
            for h in headers:
                if h['name'].lower() == 'subject':
                    subject = h['value']
                elif h['name'].lower() == 'date':
                    date_str = h['value']
            
            # Clean subject to get the topic name
            topic = subject.replace("Google 알리미 -", "").replace("Google Alert -", "").replace("Google 알리미:", "").strip()
            
            # Decode payload body
            body_html = ""
            parts = payload.get('parts', [])
            if not parts and 'body' in payload:
                body_data = payload['body'].get('data', '')
                if body_data:
                    body_html = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
            else:
                def get_html_part(parts_list):
                    for part in parts_list:
                        mime_type = part.get('mimeType', '')
                        if mime_type == 'text/html':
                            b_data = part.get('body', {}).get('data', '')
                            if b_data:
                                return base64.urlsafe_b64decode(b_data).decode('utf-8', errors='ignore')
                        elif 'parts' in part:
                            html = get_html_part(part['parts'])
                            if html:
                                return html
                    return ""
                body_html = get_html_part(parts)
            
            if body_html:
                parsed_groups = parse_google_alert_html(body_html, topic)
                for group in parsed_groups:
                    group_topic = group['topic']
                    if group_topic not in alerts_dict:
                        alerts_dict[group_topic] = {
                            'topic': group_topic,
                            'date': date_str,
                            'articles': []
                        }
                    # Merge articles, avoiding duplicate links
                    existing_links = [a['link'] for a in alerts_dict[group_topic]['articles']]
                    for art in group['articles']:
                        if art['link'] not in existing_links:
                            alerts_dict[group_topic]['articles'].append(art)
        
        # Compile final alerts data, slicing each topic to max 3 articles
        alerts_data = []
        for group_topic, data in alerts_dict.items():
            data['articles'] = data['articles'][:3]
            if data['articles']:
                alerts_data.append(data)
                
        if not alerts_data:
            print("[Info] Successfully read alerts emails but found no valid articles. Returning mock alerts.")
            return get_mock_google_alerts()
            
        return alerts_data
    except Exception as e:
        print(f"[Error] Failed to fetch google alerts: {e}")
        return get_mock_google_alerts()

def parse_morning_brief_text(text):
    """Parses morning brief text exported from Google Docs into 4 key structured data components:
    1. Section 1: 전체 동향 현황 요약 (Narrative Overview)
    2. Section 2: 총괄 거시경제 및 시장 환경 (Executive Summary, 5대 변곡점, 핵심 마크로 지표)
    3. Sections 3~5: 빅테크/산업재/거시 리스크 심층 분석 (Deep Dive)
    4. Section 6: 종합 투자자 대응 매트릭스 & 포트폴리오 전략 (Tactical Matrix)
    """
    if not text:
        return {}

    # 1. Extract Section 1 (전체 동향 현황 요약)
    s1_items = []
    p1 = text.find("1. 오늘")
    p2 = text.find("2. 총괄 거시경제")
    if p1 != -1 and p2 != -1:
        s1_chunk = text[p1:p2]
        for line in s1_chunk.split('\n'):
            line_s = line.strip().replace('\r', '')
            m = re.match(r'^([1-5])\.\s*(.*)', line_s)
            if m and "전체 동향" not in line_s:
                s1_items.append({
                    'num': m.group(1),
                    'text': m.group(2).strip()
                })

    # 2. Extract Section 2 (총괄 거시경제 및 시장 환경)
    s2_intro = ""
    s2_flows = []
    s2_categories = []
    p3 = text.find("3. Big Tech")
    if p2 != -1 and p3 != -1:
        s2_chunk = text[p2:p3]
        s2_lines = s2_chunk.split('\n')
        
        current_cat = None
        for line in s2_lines:
            line_s = line.strip().replace('\r', '')
            if not line_s or "2. 총괄 거시경제" in line_s or line_s.startswith("_____"):
                continue
                
            if '──>' in line_s or '-->' in line_s:
                s2_flows.append(line_s)
                continue
                
            cat_match = re.match(r'^\*\s*([A-Za-z0-9\s&/,\(\)]+):\s*(.*)', line_s)
            if cat_match:
                if current_cat:
                    s2_categories.append(current_cat)
                current_cat = {
                    'name': cat_match.group(1).strip(),
                    'text': cat_match.group(2).strip()
                }
                continue
            elif current_cat and line_s.startswith('*'):
                pass
            elif current_cat:
                current_cat['text'] += " " + line_s
                continue
                
            if not s2_flows and not current_cat and len(line_s) > 30 and "핵심 마크로" not in line_s:
                s2_intro += line_s + " "

        if current_cat:
            s2_categories.append(current_cat)

    # 3. Extract Section 6 (종합 투자자 대응 매트릭스)
    matrix_map = {}
    p6 = text.find("6. 종합 투자자 대응 매트릭스")
    if p6 != -1:
        s6_chunk = text[p6:]
        end_idx = s6_chunk.find("본 보고서는 Google Alerts")
        if end_idx != -1:
            s6_chunk = s6_chunk[:end_idx]
            
        s6_lines = [l.strip().replace('\r', '') for l in s6_chunk.split('\n') if l.strip().replace('\r', '')]
        # Cells appear sequentially: [Asset, Stance, Thesis, Risk, Asset, Stance, Thesis, Risk, ...]
        raw_cells = []
        for l in s6_lines:
            if "6. 종합" in l or "자산군 / 종목" in l or "투자의견" in l or "핵심 투자 논리" in l or "리스크 관리" in l or l.startswith("_____"):
                continue
            raw_cells.append(l)

        i = 0
        while i < len(raw_cells):
            # Check if asset name might span 2 lines
            asset = raw_cells[i]
            if i + 1 < len(raw_cells) and (raw_cells[i+1].startswith('(') and raw_cells[i+1].endswith(')')):
                asset += " " + raw_cells[i+1]
                i += 1

            if i + 3 < len(raw_cells):
                stance = raw_cells[i+1]
                thesis = raw_cells[i+2]
                risk = raw_cells[i+3]
                
                # Normalize key names
                clean_asset = asset.split('(')[0].strip()
                matrix_map[clean_asset.lower()] = {
                    'asset': asset,
                    'stance': stance,
                    'thesis': thesis,
                    'risk': risk
                }
                matrix_map[asset.lower()] = matrix_map[clean_asset.lower()]
                i += 4
            else:
                break

    # 4. Extract Deep Dive (Sections 3, 4, 5) per keyword
    deep_dive = {}
    p_end = text.find("6. 종합 투자자 대응 매트릭스")
    if p3 != -1 and p_end != -1:
        deep_chunk = text[p3:p_end]
        keywords = ["NVIDIA", "엔비디아", "Microsoft", "마이크로소프트", "Meta", "메타", "Tesla", "테슬라", "Corning", "코닝", "HD현대", "HD건설기계", "카카오", "네이버", "오라클", "비트코인", "금", "환율", "셀트리온", "두산에너빌", "두산에너빌리티", "CNH", "Home Depot"]
        subsections = re.split(r'\n(?=\([0-9]+\)|\*[A-Z]|\*\s*[A-Za-z0-9가-힣]+|\#\#)', deep_chunk)
        for sub in subsections:
            sub_s = sub.strip().replace('\r', '')
            if not sub_s or len(sub_s) < 30:
                continue
            for kw in keywords:
                if kw.lower() in sub_s.lower():
                    clean_kw = kw.upper()
                    if clean_kw not in deep_dive:
                        deep_dive[clean_kw] = []
                    deep_dive[clean_kw].append(sub_s)
                    break

    return {
        'section1_overview': s1_items,
        'section2_macro': {
            'intro': s2_intro.strip(),
            'flows': s2_flows,
            'categories': s2_categories
        },
        'section6_matrix': matrix_map,
        'deep_dive': deep_dive
    }

def fetch_morning_brief(drive_service):
    """Fetches the latest Morning Brief markdown report from Google Drive:
    Path: my_drive/1.Obsidian/Google_Obsidian/0.Slip-box/모닝브리프
    """
    if not drive_service:
        print("[Info] Drive service not available for morning brief. Using fallback.")
        return {}
        
    try:
        import io
        from googleapiclient.http import MediaIoBaseDownload
        
        # Search for folder "모닝브리프"
        query = "name = '모닝브리프' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = drive_service.files().list(q=query, fields='files(id, name)').execute()
        folders = results.get('files', [])
        if not folders:
            print("[Warn] Folder '모닝브리프' not found in Google Drive.")
            return {}
            
        folder_id = folders[0]['id']
        q_files = f"'{folder_id}' in parents and trashed = false"
        file_results = drive_service.files().list(q=q_files, fields='files(id, name, mimeType, modifiedTime)', pageSize=10, orderBy='name desc').execute()
        files = file_results.get('files', [])
        if not files:
            print("[Warn] No files found in '모닝브리프' folder.")
            return {}
            
        latest_file = files[0]
        file_id = latest_file['id']
        file_name = latest_file['name']
        mime = latest_file.get('mimeType', '')
        
        print(f"[Info] Downloading latest Morning Brief file: {file_name} (ID: {file_id})")
        if 'google-apps' in mime:
            req = drive_service.files().export_media(fileId=file_id, mimeType='text/plain')
        else:
            req = drive_service.files().get_media(fileId=file_id)
            
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            
        content = fh.getvalue().decode('utf-8', errors='replace')
        brief_data = parse_morning_brief_text(content)
        brief_data['file_name'] = file_name
        brief_data['date'] = file_name.replace('.md', '').strip()
        print(f"[Success] Successfully parsed Morning Brief: {len(brief_data.get('section1_overview', []))} overview items, {len(brief_data.get('section6_matrix', {}))} matrix entries.")
        return brief_data
    except Exception as e:
        print(f"[Error] Failed to fetch morning brief: {e}")
        return {}

            
        return alerts_data
    except Exception as e:
        print(f"[Error] Failed to fetch google alerts: {e}")
        return get_mock_google_alerts()

def parse_markdown_detail(md_text):
    """Parses an individual keyword markdown file into structured date sections."""
    if not md_text:
        return []
    
    sections = []
    current_section = None
    
    lines = md_text.split('\n')
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Match Date header: ## 2026-08-26 (수요일) or ## 2026-08-26
        if line_clean.startswith('## '):
            if current_section and (current_section['items'] or current_section['raw_lines']):
                sections.append(current_section)
            date_title = line_clean.replace('## ', '').strip()
            current_section = {
                'date': date_title,
                'items': [],
                'raw_lines': []
            }
            continue
            
        # Match list item: - **제목** — 출처. 내용... [링크](URL)
        if line_clean.startswith('- ') and current_section is not None:
            item_text = line_clean[2:].strip()
            
            # Extract link: [링크](url) or [텍스트](url)
            link_url = ""
            link_match = re.search(r'\[(.*?)\]\((https?://[^\)]+)\)', item_text)
            if link_match:
                link_url = link_match.group(2)
                item_text = re.sub(r'\[(.*?)\]\((https?://[^\)]+)\)', '', item_text).strip()
                if item_text.endswith('..') or item_text.endswith('.'):
                    item_text = item_text.rstrip('.').strip()
            
            # Extract bold title: **제목**
            title = ""
            body = item_text
            bold_match = re.search(r'^\*\*(.*?)\*\*(.*)', item_text)
            if bold_match:
                title = bold_match.group(1).strip()
                body = bold_match.group(2).strip()
            else:
                title = item_text
                body = ""
                
            # Extract source
            source = ""
            if body.startswith('—') or body.startswith('-') or body.startswith('–'):
                body = body.lstrip('—–-').strip()
                parts = body.split('. ', 1)
                if len(parts) == 2 and len(parts[0]) < 30:
                    source = parts[0].strip()
                    body = parts[1].strip()
                elif '—' in body:
                    s_parts = body.split('—', 1)
                    source = s_parts[0].strip()
                    body = s_parts[1].strip()
            
            current_section['items'].append({
                'title': title,
                'source': source,
                'body': body,
                'link': link_url
            })
        elif current_section is not None:
            current_section['raw_lines'].append(line_clean)
            
    if current_section and (current_section['items'] or current_section['raw_lines']):
        sections.append(current_section)
        
    return sections

def parse_index_markdown(index_md_text):
    """Parses _주요동향_인덱스.md into metadata and list of keyword entries."""
    lines = index_md_text.split('\n')
    
    subtitle = "Google Alerts 키워드 최신 현황 대시보드"
    last_updated = ""
    entries = []
    
    in_table = False
    headers = []
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        if line_clean.startswith('>'):
            sub_text = line_clean.lstrip('>').strip()
            if '최종 업데이트' in sub_text:
                parts = sub_text.split('최종 업데이트:')
                if len(parts) > 1:
                    last_updated = parts[1].strip()
            elif not subtitle or subtitle == "Google Alerts 키워드 최신 현황 대시보드":
                subtitle = sub_text
            continue
            
        if line_clean.startswith('|') and line_clean.endswith('|'):
            cols = [c.strip() for c in line_clean.strip('|').split('|')]
            if not cols:
                continue
                
            if '키워드' in cols[0] and not headers:
                headers = cols
                in_table = True
                continue
                
            if in_table and '---' in cols[0]:
                continue
                
            if in_table and len(cols) >= 4:
                keyword = cols[0].strip()
                summary = cols[1].strip()
                direction = cols[2].strip()
                doc_col = cols[3].strip()
                
                doc_name = ""
                doc_filename = ""
                doc_match = re.search(r'\[(.*?)\]\((.*?)\)', doc_col)
                if doc_match:
                    doc_name = doc_match.group(1).strip()
                    raw_file = doc_match.group(2).strip()
                    raw_file = urllib.parse.unquote(raw_file)
                    doc_filename = os.path.basename(raw_file)
                else:
                    doc_name = keyword
                    doc_filename = f"{keyword}.md"
                    
                entries.append({
                    'id': f"trend-{len(entries)}",
                    'keyword': keyword,
                    'summary': summary,
                    'direction': direction,
                    'doc_name': doc_name,
                    'doc_filename': doc_filename
                })
                
    return {
        'subtitle': subtitle,
        'last_updated': last_updated or datetime.date.today().strftime("%Y-%m-%d"),
        'entries': entries
    }

def get_mock_trends_data():
    """Generates mock trends data for offline/demo reliability."""
    mock_index_text = """
# 주요동향 인덱스

> Google Alerts 17개 키워드 최신 현황 대시보드
> 최종 업데이트: 2026-08-26

---

| 키워드 | 최신 동향 | 방향 | 문서 | |
| --- | --- | --- | --- | --- |
| NVIDIA | 오늘(8/26) 밤 실적발표—'하이퍼스케일러 의존' 최대 시험대(CNBC)·옵션시장, 실적 후 시총 2,800억달러(390조원) 스윙 예상(Reuters) | ↔ | [NVIDIA](NVIDIA.md) | |
| 마이크로소프트 | "S&P 500보다 낫다" 재평가—높은 성장성+낮은 PER(코인리더스)·487.31달러 0.84% 상승 마감(톱스타뉴스) | ▲ | [마이크로소프트](마이크로소프트.md) | |
| 메타 | AI 에이전트 '해치(Hatch)' 출시 임박·10월 새 모델 '워터멜론' 공개(AI타임스)·1.4조달러 '세기의 재판' | ▲ | [메타](메타.md) | |
| 환율 | 원화값 13개월 만에 최고—장중 1,370원대 원화 강세(매경)·'1,600원 바라던 환율이 1,300원대로' 3가지 이유 | ▼ | [환율](환율.md) | |
| 오라클 | '장부에 없는 3조달러 AI 부채' 경고—엔비디아→오픈AI→오라클 순환 고리(이데일리) | ▼ | [오라클](오라클.md) | |
| 금 | 금값 3개월래 최고치 경신—4,700달러선 접근(남도일보)·한 돈 89만원 시대 | ▲ | [금](금.md) | |
| 비트코인 | 석달만에 8만달러 돌파—달러약세에 금도 동반 급등(미주중앙일보)·지난 7거래일 +22% | ▲ | [비트코인](비트코인.md) | |
| 두산에너빌 | 체코 원전 모니터링 본격화·영남 SMR 5.1조 컨소시엄·AI 데이터센터 수혜 | ▲ | [두산에너빌](두산에너빌.md) | |
"""
    parsed_index = parse_index_markdown(mock_index_text)
    
    mock_details = {
        "trend-0": {
            "keyword": "NVIDIA",
            "direction": "↔",
            "doc_filename": "NVIDIA.md",
            "sections": [
                {
                    "date": "2026-08-26 (수요일)",
                    "items": [
                        {
                            "title": "엔비디아 실적발표, '하이퍼스케일러 의존'이 최대 시험대",
                            "source": "CNBC",
                            "body": "엔비디아의 초고속 성장은 MS·구글·메타·아마존 등 하이퍼스케일러들의 대량 GPU 구매에 힘입은 바 크다. 8/26 밤 실적발표에서 이 대고객 의존도가 최대 리스크로 지목된다.",
                            "link": "https://www.cnbc.com"
                        },
                        {
                            "title": "엔비디아 실적 후 시가총액 2,800억 달러 흔들린다…옵션시장 예상",
                            "source": "Reuters",
                            "body": "옵션 트레이더들이 엔비디아 실적 발표 후 시가총액 기준 약 2,800억 달러(약 390조원) 규모의 주가 변동이 있을 것으로 가격화하고 있다.",
                            "link": "https://www.reuters.com"
                        }
                    ]
                }
            ]
        }
    }
    
    return {
        'subtitle': parsed_index['subtitle'],
        'last_updated': parsed_index['last_updated'],
        'entries': parsed_index['entries'],
        'details': mock_details
    }

def fetch_trends_data(drive_service, morning_brief=None):
    """Fetches _주요동향_인덱스.md and all linked markdown files from Google Drive,
    and enriches with Morning Brief deep dive analysis."""
    if not drive_service:
        print("[Info] Drive service not available. Defaulting to mock trends data.")
        return get_mock_trends_data()
        
    index_file_id = '1hbEGqTY3FfPEHgDVwoNVnF1qntgHFJEg'
    try:
        import io
        from googleapiclient.http import MediaIoBaseDownload
        
        # 1. Download index file
        req = drive_service.files().get_media(fileId=index_file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        index_content = fh.getvalue().decode('utf-8', errors='replace')
        
        parsed_index = parse_index_markdown(index_content)
        if not parsed_index['entries']:
            print("[Warn] No entries parsed from _주요동향_인덱스.md. Using fallback.")
            return get_mock_trends_data()
            
        # 2. Find parent folder to map all markdown documents
        file_meta = drive_service.files().get(fileId=index_file_id, fields='parents').execute()
        parents = file_meta.get('parents', [])
        
        file_map = {}
        if parents:
            parent_id = parents[0]
            query = f"'{parent_id}' in parents and trashed = false and mimeType = 'text/markdown'"
            results = drive_service.files().list(q=query, fields='files(id, name)', pageSize=100).execute()
            files = results.get('files', [])
            file_map = {f['name']: f['id'] for f in files}
            
        deep_dive_map = morning_brief.get('deep_dive', {}) if morning_brief else {}
        brief_date = morning_brief.get('date', datetime.date.today().strftime("%Y-%m-%d")) if morning_brief else datetime.date.today().strftime("%Y-%m-%d")
        
        details_map = {}
        for entry in parsed_index['entries']:
            entry_id = entry['id']
            fname = entry['doc_filename']
            keyword = entry['keyword']
            
            # Find matching file ID
            matched_id = file_map.get(fname)
            if not matched_id:
                for k, v in file_map.items():
                    if k.lower() == fname.lower() or k.replace(' ', '') == fname.replace(' ', ''):
                        matched_id = v
                        break
                        
            sections = []
            if matched_id:
                try:
                    f_req = drive_service.files().get_media(fileId=matched_id)
                    f_fh = io.BytesIO()
                    f_downloader = MediaIoBaseDownload(f_fh, f_req)
                    f_done = False
                    while not f_done:
                        _, f_done = f_downloader.next_chunk()
                    md_text = f_fh.getvalue().decode('utf-8', errors='replace')
                    sections = parse_markdown_detail(md_text)
                    sections = sections[:15]
                except Exception as ex:
                    print(f"[Warn] Failed to download {fname}: {ex}")
                    
            # Check if there is Morning Brief deep dive analysis for this keyword (Req 3)
            matched_deep_dive = []
            for d_kw, d_texts in deep_dive_map.items():
                if d_kw.lower() in keyword.lower() or keyword.lower() in d_kw.lower() or (d_kw == 'HD건설기계' and '건설기계' in keyword):
                    matched_deep_dive.extend(d_texts)
                    
            if matched_deep_dive:
                # Format deep dive items
                brief_items = []
                for idx, dt in enumerate(matched_deep_dive):
                    clean_dt = dt.strip()
                    # Extract headline or first sentence
                    first_line = clean_dt.split('\n')[0].strip()
                    title = first_line.lstrip('*#- ').strip()
                    body = "\n".join(clean_dt.split('\n')[1:]).strip() if '\n' in clean_dt else clean_dt
                    if not body:
                        body = title
                        
                    brief_items.append({
                        'title': f"[모닝브리프 심층분석] {title}",
                        'source': "모닝브리프",
                        'body': body,
                        'link': f"https://drive.google.com/drive/folders/{parent_id}" if parents else "",
                        'is_deep_dive': True
                    })
                    
                # Prepend or merge with today's section
                today_header = f"{brief_date} (오늘)"
                if sections and (brief_date in sections[0]['date'] or '오늘' in sections[0]['date']):
                    # Merge into existing today section
                    sections[0]['items'] = brief_items + sections[0]['items']
                else:
                    # Create new today section at the top
                    sections.insert(0, {
                        'date': today_header,
                        'items': brief_items,
                        'raw_lines': []
                    })
                    
            details_map[entry_id] = {
                'keyword': entry['keyword'],
                'direction': entry['direction'],
                'doc_filename': entry['doc_filename'],
                'sections': sections
            }
            
        print(f"[Success] Successfully fetched {len(parsed_index['entries'])} trend topics from Google Drive.")
        return {
            'subtitle': parsed_index['subtitle'],
            'last_updated': parsed_index['last_updated'],
            'entries': parsed_index['entries'],
            'details': details_map
        }
    except Exception as e:
        print(f"[Error] Failed to fetch trends data from Google Drive: {e}")
        return get_mock_trends_data()


def fetch_stock_news(stock_name):
    """Searches and fetches the latest news headlines for a given stock from Google News RSS,
    filtering for articles published within D-2 days and prioritizing institutional analysis.
    """
    import datetime
    
    # Clean stock name: remove parentheticals, suffixes (e.g. "(H)", "액티브", etc.)
    clean_name = stock_name
    for stop_word in ["(H)", "(노출)", "액티브", "선물"]:
        clean_name = clean_name.replace(stop_word, "")
    clean_name = clean_name.split('(')[0].strip()
    
    is_eng = all(ord(char) < 128 for char in clean_name.replace(" ", ""))
    if is_eng:
        query = f"{clean_name} stock"
    else:
        query = f"{clean_name}"
            
    encoded_query = urllib.parse.quote(query)
    
    # Select appropriate feed based on language
    if is_eng:
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"
    else:
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        
    try:
        feed = feedparser.parse(url)
        entries = feed.get('entries', [])
        
        KST = datetime.timezone(datetime.timedelta(hours=9))
        today = datetime.datetime.now(KST).date()
        
        filtered_news = []
        for entry in entries:
            # 1. Date check (D-2)
            struct_time = entry.get('published_parsed')
            if not struct_time:
                continue
            
            # Convert published_parsed to datetime
            pub_dt = datetime.datetime(*struct_time[:6], tzinfo=datetime.timezone.utc)
            pub_date = pub_dt.astimezone(KST).date()
            
            # Do not refer to articles published before D-2
            if (today - pub_date).days > 2:
                continue
                
            title = entry.title
            source = entry.get('source', {}).get('title', '')
            if not source and " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0]
                source = parts[1]
                
            score = 0
            title_lower = title.lower()
            source_lower = source.lower() if source else ""
            
            # Reputable sources list
            reputable_sources = [
                # Korean
                "연합인포맥스", "이데일리", "매일경제", "한국경제", "비즈니스포스트", "팍스넷", "머니투데이", 
                "아시아경제", "파이낸셜뉴스", "서울경제", "조선비즈", "헤럴드경제", "인포스탁데일리", "뉴스1", "뉴시스",
                # English
                "reuters", "bloomberg", "marketwatch", "cnbc", "investor", "yahoo finance", "seeking alpha", 
                "motley fool", "simply wall st", "zacks", "barron", "wsj", "financial times", "ft.com"
            ]
            for rep in reputable_sources:
                if rep in source_lower:
                    score += 5
                    break
                    
            # Deep analysis keywords
            high_quality_keywords = [
                "분석", "전망", "리포트", "보고서", "목표가", "목표주가", "전략", "실적", "수주", "평가", "계약", "독점", 
                "체결", "어닝", "공급", "인수", "합병", "공시", "연구소", "특징주",
                "analysis", "outlook", "report", "forecast", "target price", "earnings", "contract", "order", 
                "strategy", "upgrade", "downgrade", "rating", "valuation", "result", "acquisition", "merger",
                "deal", "sec filing", "revenue", "guidance"
            ]
            for kw in high_quality_keywords:
                if kw in title_lower:
                    score += 3
                    
            # Simple price updates / spam de-prioritization
            low_quality_keywords = [
                "주주방", "토론방", "게시판", "찌라시", "상승출발", "하락출발", "일제히",
                "moved down", "moved up", "fell by", "rose by", "stock alert", "share alert", "stock movement"
            ]
            for kw in low_quality_keywords:
                if kw in title_lower:
                    score -= 10
                    
            filtered_news.append({
                'title': title,
                'link': entry.link,
                'date': pub_date.strftime("%Y-%m-%d"),
                'source': source,
                'score': score
            })
            
        # Sort by score (descending) and take top 5
        filtered_news.sort(key=lambda x: x['score'], reverse=True)
        
        # Clean title before returning
        news_items = []
        for item in filtered_news[:5]:
            title = item['title']
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            news_items.append({
                'title': title,
                'link': item['link']
            })
        return news_items
    except Exception as e:
        print(f"[Warn] Failed to fetch news for {stock_name}: {e}")
        return []

def generate_ai_analysis(summary_diffs, high_volatility_assets):
    """Generates AI governing message and asset analysis using Gemini API (if available)."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("[Info] GEMINI_API_KEY environment variable not found. Using local rule-based fallback analysis.")
        return get_fallback_analysis(summary_diffs, high_volatility_assets)
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    prompt = f"""
당신은 은퇴자산을 전문적으로 관리하는 AI 수석 자산운용가입니다.
오늘의 자산 변동 현황 데이터를 분석하여, 사용자가 아침에 보고 직관적으로 파악할 수 있는 브리핑 자료를 한국어로 작성해 주세요.

[분석 대상 데이터]
1. 주요 자산 변동 요약:
{json.dumps(summary_diffs, ensure_ascii=False, indent=2)}

2. 전일대비 ±3% 이상 급변동한 보유 종목 (각 종목의 최신 뉴스 헤드라인 'news' 정보 포함):
{json.dumps(high_volatility_assets, ensure_ascii=False, indent=2)}

[요구사항]
아래의 3개 항목을 포함하는 JSON 형식의 답변만 반환해 주세요. (마크다운 백틱 없이 순수 JSON만 반환)
JSON 키 이름:
- "governing_message": 어제 대비 자산 포트폴리오의 전체적인 변동 현황(예: 전체 자산 변동률, 주요 자산군 변동)을 요약하고, 이러한 변동이 발생한 주된 원인(거시경제, 반도체/AI 시장, 환율 등)을 매끄러운 2~3문장의 줄글로 요약하고, 마지막에는 "따라서 오늘은 어떤 포인트에 집중하여 포트폴리오를 모니터링해야 하는지" 조언을 추가해 주세요.
- "governing_summary": Governing Message 아래에 들어갈 핵심 요약 포인트 3가지를 리스트 형식으로 작성해 주세요. (예: ["DRAM/낸드 가격 상승으로 반도체 밸류체인 급등", "ESS 계약 호재로 인한 LG엔솔 반등", "환율 상승세 둔화에 따른 외화 자산 방어"])
- "asset_analysis_box": 우측 대시보드에 들어갈 "급변동 종목 요인 분석 및 투자 가이드" 내용입니다. ±3% 이상 급변동한 개별 종목들 각각에 대해, 변동률의 부호(플러스/마이너스)를 정확히 확인하여 부합하는 실질적인 요인을 분석해 주세요. 예를 들어 전일대비 하락(마이너스)한 종목은 왜 주가가 떨어졌는지 구체적인 악재나 시장 매물 출회 요인을 명확히 설명하고, 상승(플러스)한 종목은 왜 주가가 큰 폭으로 올랐는지 호재성 이슈를 분석해야 합니다. 각 종목에 포함된 최신 뉴스 헤드라인('news') 리스트를 적극 활용하여, 피상적인 분석이나 무관한 원인(예: 미국/해외 주식에 대해 한국 기준인 '외국인 자금 이탈' 등 맞지 않는 분석 방향)을 제시하지 말고 실제 최신 이슈와 전문가들의 투자의견을 충실히 반영해 분석해 주세요. 또한 이에 매칭되는 구체적인 대응법과 매수/매도/보유 등 투자자 관점의 포트폴리오 조정 가이드를 친절하고 상세하게 가이드해 주세요. 종목명 옆에는 하락 종목의 경우 빨간색 동그라미 아이콘(🔴)과 붉은색 텍스트(예: class='text-rose-400'), 상승 종목의 경우 초록색 동그라미 아이콘(🟢)과 초록색 텍스트(예: class='text-emerald-400')를 사용해 시각적 시인성을 확보해 주세요. (HTML 태그 `<p>`, `<strong>`, `<ul>`, `<li>` 등을 활용해 깔끔한 구조로 작성)

[중요 지침]
- 'asset_analysis_box'를 작성할 때, 반드시 위에 제공된 '2. 전일대비 ±3% 이상 급변동한 보유 종목' 리스트의 나열 순서 그대로(즉, 전일대비 변동률 절대값 기준 내림차순) 하나씩 분석을 기술해 주세요. 임의로 종목 순서를 섞거나 변경해서는 안 됩니다.

반환할 JSON 구조 예시:
{{
  "governing_message": "...",
  "governing_summary": ["...", "...", "..."],
  "asset_analysis_box": "..."
}}
"""

    try:
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        response = requests.post(url, headers=headers, json=payload, timeout=12)
        if response.status_code == 200:
            res_data = response.json()
            text_content = res_data['candidates'][0]['content']['parts'][0]['text']
            ai_data = json.loads(text_content.strip())
            return ai_data
        else:
            print(f"[Warn] Gemini API returned status code {response.status_code}. Using fallback.")
    except Exception as e:
        print(f"[Warn] Gemini API call failed: {e}. Using fallback.")
        
    return get_fallback_analysis(summary_diffs, high_volatility_assets)


def get_fallback_analysis(summary_diffs, high_volatility_assets):
    # Diffs 정보 요약
    daily_gain_str = ""
    for s in summary_diffs:
        if s['header'] == '직전대비 수익금변동':
            daily_gain_str = s['val']
            break
            
    msg = f"어제 대비 자산 포트폴리오는 전반적으로 긍정적인 흐름을 보였습니다. 특히 직전대비 수익금이 {daily_gain_str} 변동하며 자산 가치가 상승하였습니다. 이는 글로벌 기술주 및 국내 대형 반도체/IT 종목들이 큰 폭의 강세를 나타낸 것에 영향을 받았습니다."
    msg += " 오늘은 거시경제 지표 발표 및 주요 미국 기술주들의 동향에 주목하며 자산 비중을 안정적으로 유지할 필요가 있습니다."
    
    analysis_html = "<h4><strong>보유 자산 급변동 요인 및 투자 조언</strong></h4><br>"
    if high_volatility_assets:
        analysis_html += "<ul class='space-y-4'>"
        for item in high_volatility_assets:
            name = item['name']
            change = item['change']
            yield_val = item['yield']
            change_float = item.get('change_float', 0)
            
            # Determine if positive or negative change
            is_positive = change_float > 0 if 'change_float' in item else not change.strip().startswith('-')
            
            # Determine if domestic or overseas stock
            clean_name = name.split('(')[0].strip()
            is_eng = all(ord(char) < 128 for char in clean_name.replace(" ", ""))
            
            # Set default reason and advice based on direction and market (domestic vs overseas)
            if is_positive:
                bullet = "🟢"
                color_class = "text-emerald-400"
                if is_eng:
                    reason = "글로벌 매수세 유입 및 실적 서프라이즈 모멘텀, 업황 개선 기대감 반영"
                    advice = "미국 및 해외 주요 지수의 견고한 흐름에 발맞추어 보유 비중을 유지하며, 단기 급등 시 일부 차익 실현 타이밍을 조율하는 것이 유리합니다."
                else:
                    reason = "국내 기관 및 외국인 수급 개선, 업황 회복 기대감 반영 및 개별 호재 발생"
                    advice = "단기 모멘텀이 강화되는 추세이나, 추격 매수보다는 기존 비중을 유지하며 분할 수익 실현 타이밍을 타진하는 것이 유리합니다."
            else:
                bullet = "🔴"
                color_class = "text-rose-400"
                if is_eng:
                    reason = "미 연준의 고금리 장기화 우려에 따른 기술/가치주 동반 매물 출회 및 개별 단기 모멘텀 약화"
                    advice = "기초 체력(펀더멘탈) 훼손 요인은 없으나 단기 변동성 통제 구간이므로, 서두르기보다 기존 비중을 유지하고 관망하는 것이 바람직합니다."
                else:
                    reason = "글로벌 거시경제 금리 인하 지연 우려에 따른 외국인 자금 이탈 및 국내 시장의 단기 차익 실현 매물 출하"
                    advice = "펀더멘탈 훼손 요인은 없으나 국내 수급 불안정성으로 인한 단기 변동성 구간이므로, 추가 낙폭 시 저가 분할 매수로 대응하는 것이 바람직합니다."
                
            # Customize based on specific core stocks
            name_lower = name.lower()
            if "삼성전자" in name:
                if is_positive:
                    reason = "AI DRAM 및 NAND 가격의 가파른 상승세와 모바일/SSD 선점 효과로 인한 어닝 서프라이즈 기대감, 선단 공정 수주 확장 모멘텀"
                    advice = "핵심 반도체 밸류체인의 중추이므로 장기 보유 전략을 고수하며 포트폴리오의 중심축으로 유지하는 것이 바람직합니다."
                else:
                    reason = "미국 고금리 장기화 우려에 따른 글로벌 기술주 투자심리 위축 및 단기 외국인 프로그램 매도세 집중"
                    advice = "일시적 단기 급락은 중장기 투자자에게 매력적인 비중 확대 기회이므로, 차분하게 분할 매수로 대응하는 것이 유효합니다."
            elif "네이버" in name or "naver" in name_lower:
                if is_positive:
                    reason = "엔비디아와 글로벌 AI 팩토리 공동 구축 사업 추진 소식 및 치지직 플랫폼 등의 트래픽 호조에 따른 광고 수익성 재평가"
                    advice = "플랫폼의 확장성이 입증되는 단계이므로 추가 매수 혹은 보유 의견을 유지하며 장기 성장에 동참할 가치가 큽니다."
                else:
                    reason = "라인야후 지분 관련 지정학적 노이즈 장기화 우려 및 내수 광고 시장 성장 둔화 전망"
                    advice = "하방 경직성이 확보되는 가격대까지 무리한 추가 매수는 자제하되, 손절매보다는 보유 후 장기 관망이 적합합니다."
            elif "LG에너지솔루션" in name or "LG엔솔" in name or "lg에너지" in name_lower:
                if is_positive:
                    reason = "미국 DTE에너지와의 대규모 ESS 공급 계약 체결로 북미 에너지 인프라 및 AI 데이터센터 에너지 그리드 선점 기대감"
                    advice = "전기차 수요 캐즘 우려를 대형 ESS 시장 확장으로 상쇄 중이므로 긍정적 관점 유지 및 보유가 유리합니다."
                else:
                    reason = "글로벌 전기차(EV) 수요 캐즘 구간 진입 장기화 우려 및 리튬 가격 약세에 따른 배터리 판가 하락 우려 반영"
                    advice = "단기 업황 둔화가 주가에 상당 부분 선반영되었으므로 추가 매수는 지양하되 기존 비중은 꿋꿋하게 보유해야 합니다."
            elif "셀트리온" in name:
                if is_positive:
                    reason = "바이오시밀러(짐펜트라 등)의 미국 신규 처방 집계 호조 및 FDA 승인 파이프라인 가속화에 따른 실적 턴어라운드 본격화"
                    advice = "실적 턴어라운드가 가시화되고 있으므로 적극적인 보유 혹은 포트폴리오 내 비중 확대를 권장합니다."
                else:
                    reason = "최근 제약바이오 섹터 전반의 수급 부진 및 기관/외국인의 대형주 중심 리밸런싱에 따른 일시적 소외"
                    advice = "기업의 본질 가치 훼손이 아니며 주주친화 정책이 강력하므로 낙폭 과대 시 저점 분할 매수 기회로 활용할 수 있습니다."
            elif "한화시스템" in name:
                if is_positive:
                    reason = "글로벌 지정학적 긴장 지속에 따른 중동 등 방산 수출 계약 성사 기대 및 우주 위성통신 사업의 독점적 경쟁력 부각"
                    advice = "방산 부문의 견고한 실적과 우주 신사업의 미래 성장성이 돋보이므로 비중 보유 혹은 매수 관점이 적합합니다."
                else:
                    reason = "최근 주가 급등에 따른 외국인 차익 실현 물량 출회 및 분기 실적 인도 일정의 일시적 순연 가능성 우려"
                    advice = "중장기 수주 잔고가 여전히 역대 최고 수준이므로 단기 조정 구간을 저가 매수 찬스로 포착할 수 있습니다."
            elif "카카오" in name:
                if is_positive:
                    reason = "카카오톡 탭 개편을 통한 B2B 광고 단가 상승 효과 가시화 및 신규 AI 브랜드 로드맵 공개 기대감 반영"
                    advice = "단기 반등세에 불과하므로 신규 추가 매수보다는 기존 보유 물량 위주로 보수적 관망을 권장합니다."
                else:
                    reason = "내부 경영진 사법 리스크 및 노사 갈등(첫 노조 총파업 리스크 등)에 따른 거버넌스 신뢰도 하락"
                    advice = "경영 불확실성과 노사 갈등이 완전히 해소되는 시점까지 신규 진입은 극도로 보수적으로 접근하는 것이 바람직합니다."
            elif "lmt" in name_lower or "lockheed" in name_lower:
                if is_positive:
                    reason = "방위 산업 계약 확대 모멘텀 지속 및 신규 방산 기술 수주 호재 반영"
                    advice = "미국 대표 방산 대형주로서 견고한 수주 실적을 기반으로 안정적인 보유 의견을 권장합니다."
                else:
                    reason = "미 국방부 조달 예산 일부 축소 우려 및 단기 가격 급등에 따른 기술적 조정 물량 출회"
                    advice = "단기 하락은 시장 수급과 예산 심의 일정에 따른 일시적 변동이므로 중장기 관점에서의 매력적인 매수 기회로 포착 가능합니다."
            
            # If news is available, append it directly in the fallback analysis
            news_html = ""
            if item.get('news'):
                news_html += "<span class='text-slate-400' style='display:block; margin-top:4px; font-size: 0.8rem;'><strong>최신 관련 뉴스:</strong>"
                for news in item['news'][:3]:
                    news_html += f"<br>• <a href='{news['link']}' target='_blank' class='text-brand-300 hover:underline' style='text-decoration:none;'>{news['title']}</a>"
                news_html += "</span>"
                
            # If Morning Brief Section 6 matrix is available, append it (Req 4)
            matrix_html = ""
            if item.get('matrix_info'):
                m = item['matrix_info']
                stance = m.get('stance', '')
                thesis = m.get('thesis', '')
                risk = m.get('risk', '')
                matrix_html = f"<div class='mt-2.5 p-3 rounded-xl bg-violet-500/10 border border-violet-500/25 text-xs space-y-1'>"
                matrix_html += f"<div class='flex items-center gap-2 mb-1'><span class='px-2 py-0.5 rounded font-bold bg-violet-600/30 text-violet-300 border border-violet-500/30'>모닝브리프 전략</span><span class='font-bold text-brand-300'>투자의견: {stance}</span></div>"
                matrix_html += f"<div class='text-slate-200'><strong>핵심 투자 논리:</strong> {thesis}</div>"
                if risk:
                    matrix_html += f"<div class='text-slate-400'><strong>리스크 관리 및 대응 포인트:</strong> {risk}</div>"
                matrix_html += "</div>"
            
            analysis_html += f"<li class='border-b border-white/5 pb-3'><strong class='{color_class}'>{bullet} {name}</strong> ({change} 변동, 수익률 {yield_val})<br>"
            analysis_html += f"<span class='text-slate-300' style='display:block; margin-top:4px;'><strong>원인:</strong> {reason}</span>"
            analysis_html += f"<span class='text-brand-400' style='display:block; margin-top:2px;'><strong>대응:</strong> {advice}</span>"
            analysis_html += f"{matrix_html}"
            analysis_html += f"{news_html}</li>"
        analysis_html += "</ul>"
    else:
        analysis_html += "<p class='text-slate-400'>당일 전일대비 ±3% 이상 급변동한 종목이 없어 포트폴리오가 안정적으로 운용 중입니다.</p>"
        
    return {
        "governing_message": msg,
        "governing_summary": [
            "DRAM/낸드 가격 상승 및 AI 수요에 따른 삼성전자 강력 반등",
            "엔비디아와 글로벌 AI 팩토리 공동 추진 호재로 네이버 급등",
            "북미 ESS 대규모 공급 계약 수주에 따른 LG에너지솔루션 회복세"
        ],
        "asset_analysis_box": analysis_html
    }
def send_dashboard_email(gmail_service, to_email, filepath):
    """Sends a notification email with the dashboard HTML attached using Gmail API."""
    if not gmail_service:
        print("[Warn] Gmail service not available. Skipping email delivery.")
        return None
    try:
        from email.mime.base import MIMEBase
        from email import encoders

        message = MIMEMultipart()
        message['to'] = to_email
        message['subject'] = f"일일 브리핑 대시보드 - {datetime.date.today().strftime('%Y년 %m월 %d일')}"
        
        # Email Body advising the user to check the attachment
        body_text = """
        <div style="font-family: sans-serif; padding: 20px; line-height: 1.6; color: #333;">
            <h3 style="color: #6d28d9;">📅 일일 브리핑 대시보드가 준비되었습니다.</h3>
            <p>메일 본문에서는 이메일 클라이언트의 제한으로 인해 디자인과 차트가 깨져 보일 수 있습니다.</p>
            <p><strong>첨부된 <code>dashboard.html</code> 파일</strong>을 다운로드하여 크롬 등 웹 브라우저로 열어주세요. 
               동적 차트와 프리미엄 글래스모피즘 테마가 정상적으로 표시됩니다.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 11px; color: #888;">본 메일은 매일 오전 5시 자동 실행 결과에 따라 발송되었습니다.</p>
        </div>
        """
        msg_html = MIMEText(body_text, 'html', 'utf-8')
        message.attach(msg_html)
        
        # Attach the HTML file
        filename = os.path.basename(filepath)
        attachment = MIMEBase('application', 'octet-stream')
        with open(filepath, 'rb') as f:
            attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        attachment.add_header(
            'Content-Disposition',
            f'attachment; filename={filename}'
        )
        message.attach(attachment)
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        send_result = gmail_service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        print(f"[Success] Sent dashboard email to {to_email}. Message ID: {send_result.get('id')}")
        return send_result
    except Exception as e:
        print(f"[Error] Failed to send email via Gmail API: {e}")
        return None

def generate_calendar_insight(events_list):
    """Generates a brief 1-2 sentence Korean briefing comment based on this week's events."""
    if not events_list:
        return "이번 주에는 예정된 공식 일정이 없습니다. 편안하고 여유로운 한 주를 만끽해 보세요! ☕"
    
    count = len(events_list)
    # Extract unique, non-empty event summaries
    summaries = [e['summary'] for e in events_list if e.get('summary') and e['summary'] != '제목 없음']
    
    if not summaries:
        return f"이번 주는 총 {count}건의 주요 일정이 예정되어 있습니다. 달력에서 상세 일정을 확인해 보세요. 📅"
        
    unique_summaries = list(dict.fromkeys(summaries)) # Deduplicate maintaining order
    event_names = ", ".join([f"'{s}'" for s in unique_summaries[:2]])
    
    if len(unique_summaries) > 2:
        event_names += f" 외 {count - 2}건"
    else:
        if count > len(unique_summaries):
            event_names += f" 외 {count - len(unique_summaries)}건"
            
    return f"이번 주는 {event_names}을 비롯해 총 {count}건의 일정이 있습니다. 아래 주간 캘린더를 확인해 일정을 조율해 보세요! 📅"

def get_weekly_schedule_grid(events_list):
    """Groups events by date for a 7-day weekly calendar grid (Today to Today+6)."""
    today = datetime.date.today()
    weekly_grid = []
    
    for i in range(7):
        target_date = today + datetime.timedelta(days=i)
        weekday = KOREAN_WEEKDAYS[target_date.weekday()]
        date_str = target_date.strftime("%m/%d")
        
        # Match events for this date (match "MM월 DD일" substring in start time)
        match_date_str = target_date.strftime("%m월 %d일")
        
        day_events = []
        for ev in events_list:
            if match_date_str in ev['start']:
                time_part = "하루 종일"
                if "하루 종일" not in ev['start']:
                    # Extract the time part (HH:MM) which is at the end of the start string
                    parts = ev['start'].split(')')
                    if len(parts) > 1:
                        time_part = parts[-1].strip()
                
                day_events.append({
                    'time': time_part,
                    'summary': ev['summary'],
                    'description': ev['description'],
                    'location': ev['location']
                })
                
        weekly_grid.append({
            'date': date_str,
            'day_of_week': weekday,
            'is_today': (i == 0),
            'events': day_events
        })
    return weekly_grid

def main():
    print("[Info] Starting Daily Briefing Dashboard Generator...")
    
    # 1. Authenticate with Google
    sheets_service, calendar_service, drive_service, gmail_service = get_google_services()
    
    # 2. Find Spreadsheet ID and Fetch Data
    spreadsheet_id = None
    if drive_service:
        print("[Info] Searching for spreadsheet '은퇴자산계좌5' in Google Drive...")
        spreadsheet_id = find_spreadsheet_id(drive_service, "은퇴자산계좌5")
        if spreadsheet_id:
            print(f"[Info] Found Spreadsheet ID: {spreadsheet_id}")
        else:
            print("[Info] Spreadsheet ID could not be resolved. Will default to Mock Data for assets.")
    
    print("[Info] Fetching Asset Data...")
    assets_summary, high_volatility_assets = fetch_sheets_data(sheets_service, spreadsheet_id)
    
    # 3. Fetch Calendar Events
    print("[Info] Fetching Calendar Events...")
    calendar_events = fetch_calendar_events(calendar_service)
    calendar_insight = generate_calendar_insight(calendar_events)
    weekly_schedule = get_weekly_schedule_grid(calendar_events)
    
    # 4. Fetch Weather Data
    print("[Info] Fetching Weather Data for Dongtan...")
    weather = fetch_weather_data()
    
    # 5. Fetch Google Alerts from Gmail
    print("[Info] Fetching Google Alerts from Gmail...")
    alerts_data = fetch_google_alerts(gmail_service)
    print("[Info] Generating AI news briefing...")
    news_briefing = generate_news_briefing(alerts_data)
    
    # 6. Fetch Morning Brief from Google Drive (1.Obsidian/Google_Obsidian/0.Slip-box/모닝브리프)
    print("[Info] Fetching Morning Brief from Google Drive...")
    morning_brief = fetch_morning_brief(drive_service)
    
    # Match Section 6 matrix with high volatility assets (Req 4)
    if morning_brief and morning_brief.get('section6_matrix'):
        matrix_map = morning_brief['section6_matrix']
        for item in high_volatility_assets:
            name = item['name'].lower()
            clean_name = name.split('(')[0].strip()
            matched = None
            for mk, mv in matrix_map.items():
                if mk in name or clean_name in mk or (('hd' in name or '건설기계' in name) and ('hd' in mk or '건기' in mk)) or (('현대' in name or '현대차' in name) and '현대' in mk):
                    matched = mv
                    break
            if matched:
                item['matrix_info'] = matched
                print(f"[Info] Matched Morning Brief strategy for high-volatility asset: {item['name']} -> {matched.get('stance')}")

    # 7. Fetch Key Trends from Google Drive (_주요동향_인덱스.md & linked docs + Morning Brief deep dive)
    print("[Info] Fetching Key Trends from Google Drive...")
    trends_data = fetch_trends_data(drive_service, morning_brief)
    
    # 8. Generate AI Governing message & analysis
    print("[Info] Generating AI governing message & volatility analysis...")
    
    # Fetch latest news headlines for high volatility assets
    print("[Info] Fetching latest news for high volatility assets...")
    for item in high_volatility_assets:
        item['news'] = fetch_stock_news(item['name'])
        
    summary_diffs = []
    for h, v, c in zip(assets_summary['headers'], assets_summary['values'], assets_summary['comparisons']):
        summary_diffs.append({
            'header': h,
            'val': v,
            'comp': c.get('text', '') if c else ''
        })
    ai_analysis = generate_ai_analysis(summary_diffs, high_volatility_assets)
    
    # 9. Render HTML Template
    print("[Info] Rendering HTML Dashboard...")
    generated_time = datetime.datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분")
    today_date_str = datetime.datetime.now().strftime("%y년 %m월 %d일")
    
    try:
        # Load template
        template_dir = os.path.dirname(os.path.abspath(__file__))
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template('dashboard_template.html')
        
        output_html = template.render(
            generated_time=generated_time,
            today_date_str=today_date_str,
            assets_summary=assets_summary,
            high_volatility_assets=high_volatility_assets,
            governing_message=ai_analysis.get('governing_message', ''),
            governing_summary=ai_analysis.get('governing_summary', []),
            asset_analysis_box=ai_analysis.get('asset_analysis_box', ''),
            calendar_events=calendar_events,
            calendar_insight=calendar_insight,
            weekly_schedule=weekly_schedule,
            weather=weather,
            alerts_data=alerts_data,
            news_briefing=news_briefing,
            trends_data=trends_data,
            morning_brief=morning_brief
        )
        
        # Write output to dashboard.html
        output_path = os.path.join(template_dir, 'dashboard.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_html)
            
        print(f"[Success] Dashboard successfully generated: {output_path}")
        
        # 8. Send Email
        print("[Info] Sending dashboard email to younghum.han@hd.com...")
        send_dashboard_email(gmail_service, 'younghum.han@hd.com', output_path)

        # 9. Daily Google Sheets Sync for Workout, Health & Reading Dashboards
        try:
            from daily_sheets_sync import sync_all
            print("[DailySync] Running daily sync for Workout, Health & Reading Dashboards...")
            sync_all(push_to_git=True)
        except Exception as e:
            print(f"[DailySync Error] Failed daily sheets sync: {e}")
        
    except Exception as e:
        print(f"[Error] Failed to render HTML template: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

