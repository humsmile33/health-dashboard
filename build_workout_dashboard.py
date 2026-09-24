#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script to compile workout_dashboard.html embedding real Google Sheets data.
Uses standard string replacement to avoid f-string escaping issues.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "workout_data.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "workout_dashboard.html")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    workout_data_json = f.read().strip()

# Template with placeholder __INITIAL_WORKOUT_DATA__
template_path = os.path.join(BASE_DIR, "workout_dashboard_template.html")
with open(template_path, "r", encoding="utf-8") as f:
    template = f.read()

output = template.replace("__INITIAL_WORKOUT_DATA__", workout_data_json)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(output)

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    f.write(output)

print(f"Successfully generated {OUTPUT_FILE} and {INDEX_FILE} ({len(output)} bytes)")
