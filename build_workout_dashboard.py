#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script to compile workout_dashboard.html & index.html embedding real Google Sheets data.
Embeds:
1. workout_data.json (__INITIAL_WORKOUT_DATA__)
2. health_data.json (__INITIAL_HEALTH_DATA__)
3. reading_data.json (__INITIAL_READING_DATA__)
Uses standard string replacement to avoid f-string escaping issues.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "workout_data.json")
HEALTH_FILE = os.path.join(BASE_DIR, "health_data.json")
READING_FILE = os.path.join(BASE_DIR, "reading_data.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "workout_dashboard.html")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    workout_data_json = f.read().strip()

health_data_json = "[]"
if os.path.exists(HEALTH_FILE):
    with open(HEALTH_FILE, "r", encoding="utf-8") as f:
        health_data_json = f.read().strip()

reading_data_json = "[]"
if os.path.exists(READING_FILE):
    with open(READING_FILE, "r", encoding="utf-8") as f:
        reading_data_json = f.read().strip()

# Template with placeholders
template_path = os.path.join(BASE_DIR, "workout_dashboard_template.html")
with open(template_path, "r", encoding="utf-8") as f:
    template = f.read()

output = template.replace("__INITIAL_WORKOUT_DATA__", workout_data_json)
output = output.replace("__INITIAL_HEALTH_DATA__", health_data_json)
output = output.replace("__INITIAL_READING_DATA__", reading_data_json)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(output)

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    f.write(output)

print(f"Successfully generated {OUTPUT_FILE} and {INDEX_FILE} ({len(output)} bytes)")
