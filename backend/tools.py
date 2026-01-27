import requests
from datetime import datetime, timezone
from helper import get_zoom_access_token
ZOOM_API_BASE ="https://api.zoom.us/v2"

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
            "type": 2,  # Scheduled meeting
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
