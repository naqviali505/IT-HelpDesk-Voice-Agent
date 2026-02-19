import requests
from datetime import datetime, timedelta, time, timezone
from google.oauth2 import service_account
from googleapiclient.discovery import build
ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_TOKEN_URL ="https://zoom.us/oauth/token"

def create_meeting(summary, start_time_iso, end_time_iso, email):
    """
    Creates a Zoom meeting and returns the join link.
    """
    try:
        access_token = get_zoom_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        start_time = datetime.fromisoformat(start_time_iso).astimezone(timezone.utc)

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

        response = requests.post(
            f"{ZOOM_API_BASE}/users/me/meetings",
            headers=headers,
            json=payload
        )

        response.raise_for_status()
        meeting = response.json()

        return {
            "status": "success",
            "meeting_link": meeting["join_url"],
            "meeting_id": meeting["id"]
        }

    except Exception as e:
        print(f"Error creating Zoom meeting: {e}")
        return {"status": "error", "message": str(e)}

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'google_service_account.json'
CALENDAR_ID = 'primary'


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
            datetime.fromisoformat(b['start']),
            datetime.fromisoformat(b['end'])
        )
        for b in busy_times
    ]

    now = datetime.now(timezone.utc)

    for day_offset in range(7):
        day = now + timedelta(days=day_offset)

        if day.weekday() > 4:  # Skip weekends
            continue

        for hour in range(9, 17):

            if hour == 13:  # Skip lunch
                continue

            start_dt = datetime.combine(
                day.date(),
                time(hour, 0),
                tzinfo=timezone.utc
            )

            end_dt = start_dt + timedelta(minutes=30)

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
                    "day": start_dt.strftime("%A"),
                    "date": start_dt.strftime("%B %d, %Y"),
                    "time": start_dt.strftime("%I:%M %p UTC")
                }

    return {"error": "No available slots found in next 7 days."}
def get_zoom_access_token():
    response = requests.post(
        ZOOM_TOKEN_URL,
        params={"grant_type": "account_credentials", "account_id": os.getenv("ZOOM_ACCOUNT_ID")},
        auth=(os.getenv("ZOOM_CLIENT_ID"), os.getenv("ZOOM_CLIENT_SECRET")),
    )
    response.raise_for_status()
    return response.json()["access_token"]