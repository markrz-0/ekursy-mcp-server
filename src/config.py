import os
import sys

# Environment Configuration
USERNAME = os.environ.get("MOODLE_USERNAME")
PASSWORD = os.environ.get("MOODLE_PASSWORD")
PORT = int(os.environ.get('PORT', '6969'))
API_BASE_URL = os.environ.get("MOODLE_API_BASE", "http://moodle-api:8080")

if not USERNAME or not PASSWORD:
    print("CRITICAL ERROR: MOODLE_USERNAME and MOODLE_PASSWORD are required.", file=sys.stderr)
    sys.exit(1)
