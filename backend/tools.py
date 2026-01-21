import os
import uuid
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = r'C:\Users\smali\Desktop\Langchain\IT Helpdesk Voice Agent\backend\gen-lang-client-0113695004-0ea6be6ac616.json'

def create_meeting(summary, start_time_iso, end_time_iso, email):
    """
    Creates a Google Calendar event with a Google Meet link using a Service Account.
    """
    # 1. Load the Service Account Credentials
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Missing {SERVICE_ACCOUNT_FILE}")

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, 
        scopes=SCOPES
    )

    # 2. Build the Service
    service = build('calendar', 'v3', credentials=creds)

    # 3. Define the Event
    event = {
        'summary': summary,
        'description': 'IT Helpdesk Scheduled Meeting',
        'start': {'dateTime': start_time_iso, 'timeZone': 'UTC'},
        'end': {'dateTime': end_time_iso, 'timeZone': 'UTC'},
        # 'attendees': [{'email': email}], # Must be a list of dictionaries
        'conferenceData': {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        },
    }

    calendar_id = 'naqviali505@gmail.com' 
    event = service.events().insert(
        calendarId=calendar_id,
        body=event,
        conferenceDataVersion=1,
        sendUpdates='none' 
    ).execute()
    return {
        "status": "success",
        "meeting_link": event.get('hangoutLink'),
        "event_id": event.get('id')
    }