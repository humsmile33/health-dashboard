#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shutil
import json
import subprocess
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

TARGET_EMAIL = "develon2023@gmail.com"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
BACKUP_PATH = os.path.join(BASE_DIR, "token_backup.json")

def main():
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"[Error] credentials.json not found at {CREDENTIALS_PATH}")
        return False

    if os.path.exists(TOKEN_PATH):
        shutil.copy2(TOKEN_PATH, BACKUP_PATH)
        print(f"[Info] Existing token backed up to {BACKUP_PATH}")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    
    print("=" * 60)
    print(f"  Google OAuth Re-Authentication for {TARGET_EMAIL}")
    print("=" * 60)
    print(f"브라우저에서 '{TARGET_EMAIL}' 계정으로 로그인 후 권한을 승인해 주세요.\n")
    
    # Run local server with login_hint and prompt to force account selection
    creds = flow.run_local_server(
        port=8080,
        login_hint=TARGET_EMAIL,
        prompt='consent select_account',
        access_type='offline'
    )
    
    with open(TOKEN_PATH, 'w') as token_file:
        token_file.write(creds.to_json())
    print(f"\n[Success] New token saved to {TOKEN_PATH}")
    
    # Verify account
    try:
        gmail = build('gmail', 'v1', credentials=creds, static_discovery=True)
        profile = gmail.users().getProfile(userId='me').execute()
        current_email = profile.get('emailAddress')
        print(f"[Verification] Connected Google account email: {current_email}")
        if current_email.lower() == TARGET_EMAIL.lower():
            print(f"[Success] Verified: Successfully connected to {TARGET_EMAIL}!")
            return True
        else:
            print(f"[Warn] Connected account ({current_email}) does not match target ({TARGET_EMAIL}).")
            return True
    except Exception as e:
        print(f"[Warn] Could not verify email address via Gmail API: {e}")
        return True

if __name__ == '__main__':
    main()
