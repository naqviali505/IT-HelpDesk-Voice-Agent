import requests
from datetime import datetime, timedelta, time, timezone
from google.oauth2 import service_account
import os
from googleapiclient.discovery import build
import logging
import re
from datetime import timezone
import pytz

LOCAL_TZ = pytz.timezone("Asia/Karachi")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = r'C:\Users\smali\Desktop\Langchain\google_service_account.json'
CALENDAR_ID = 'primary'
RECENT_MEETINGS = set()


def validate_email(email):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"

    if not re.match(pattern, email):
        return False

    invalid = [
        "user@example.com",
        "test@example.com",
        "example@example.com"
    ]

    if email.lower() in invalid:
        return False

    return True

def create_meeting(summary, slot, email):
    """
    Creates a Zoom meeting and returns the join link.
    """
    try:
        access_token = get_zoom_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        start_time_iso = slot["start_time_iso"]
        end_time_iso = slot["end_time_iso"]
        start_time = datetime.fromisoformat(start_time_iso).astimezone(timezone.utc)
        if not validate_email(email):
            return {
                "status": "error",
                "message": "Invalid email provided"
            }
        payload = {
            "topic": summary,
            "type": 2,
            "start_time": start_time.isoformat(),
            "duration": int(
                (datetime.fromisoformat(end_time_iso) -
                 datetime.fromisoformat(start_time_iso)).total_seconds() / 60
            ),
            "timezone": "UTC",
            "agenda": "IT Helpdesk Scheduled Meeting",
            "settings": {
                "join_before_host": False,
                "waiting_room": True,
                "meeting_authentication": False
            }
        }
        response = requests.post(f"https://api.zoom.us/v2/users/me/meetings",headers=headers,json=payload,timeout=10)
        response.raise_for_status()
        meeting = response.json()
        meeting_key = f"{email}_{start_time_iso}"

        if meeting_key in RECENT_MEETINGS:
            logger.warning("Duplicate meeting prevented")
            return {"status": "duplicate"}
        RECENT_MEETINGS.add(meeting_key)
        
        return {
            "status": "success",
            "meeting_link": meeting["join_url"],
            "meeting_id": meeting["id"],
            "host_email":meeting["host_email"],
            "topic":meeting["topic"],
            "start-time":meeting["start_time"],
            "duration":meeting["duration"],
            "agenda":meeting["agenda"]
        }

    except Exception as e:
        logger.exception("Error creating Zoom meeting")
        return {"status": "error", "message": str(e)}

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=creds)

def get_busy_times():
    service = get_calendar_service()

    now = datetime.now(timezone.utc)
    week_later = now + timedelta(days=7)

    body = {
        "timeMin": now.isoformat(),
        "timeMax": week_later.isoformat(),
        "timeZone": "UTC",
        "items": [{"id": CALENDAR_ID}]
    }

    events_result = service.freebusy().query(body=body).execute()

    return events_result['calendars'][CALENDAR_ID]['busy']

def check_availability():
    """
    Returns first 30-min available slot in next 7 days
    based on Google Calendar + working hours.
    """

    busy_times = get_busy_times()
    busy_ranges = [
        (
            datetime.fromisoformat(b['start']).astimezone(LOCAL_TZ),
            datetime.fromisoformat(b['end']).astimezone(LOCAL_TZ)
        )
        for b in busy_times
    ]

    now = datetime.now(LOCAL_TZ) + timedelta(minutes=10)
    for day_offset in range(7):
        day = now + timedelta(days=day_offset)
        if day.weekday() > 4:  # Skip weekends
            continue

        for hour in range(9, 17):
            if hour == 13:  # Skip lunch
                continue

            start_dt_utc = datetime.combine(day.date(),time(hour, 0),tzinfo=timezone.utc)
            start_dt = start_dt_utc.astimezone(LOCAL_TZ)
            end_dt = (start_dt_utc + timedelta(minutes=30)).astimezone(LOCAL_TZ)

            if start_dt < now:
                continue

            conflict = False
            for busy_start, busy_end in busy_ranges:
                if start_dt < busy_end and end_dt > busy_start:
                    conflict = True
                    break

            if not conflict:
                return {
                    "start_time_iso": start_dt.isoformat(),
                    "end_time_iso": end_dt.isoformat(),
                    "time": start_dt.strftime("%I:%M %p"),
                }

    return {"error": "No available slots found in next 7 days."}

def get_zoom_access_token():
    response = requests.post("https://zoom.us/oauth/token",
        params={"grant_type": "account_credentials", "account_id": os.getenv("ZOOM_ACCOUNT_ID")},
        auth=(os.getenv("ZOOM_CLIENT_ID"), os.getenv("ZOOM_CLIENT_SECRET")),
    )
    response.raise_for_status()
    return response.json()["access_token"]