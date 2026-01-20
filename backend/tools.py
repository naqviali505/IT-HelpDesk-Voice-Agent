import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import uuid

# Define the scope for calendar access
SCOPES = ['https://www.googleapis.com/auth/calendar']

def create_google_meet_meeting(summary, start_time_iso, end_time_iso, email):
    """
    Creates a Google Calendar event with a Google Meet link and sends an email invite.
    Args:
        summary (str): Title of the meeting.
        start_time_iso (str): Start time in ISO format (e.g., '2026-01-25T10:00:00Z').
        end_time_iso (str): End time in ISO format.
        email (str): An email string.
    """
    creds = None
    # Token file stores user's access/refresh tokens
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If no valid credentials, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)

    event = {
        'summary': summary,
        'description': 'IT Helpdesk Scheduled Meeting',
        'start': {'dateTime': start_time_iso, 'timeZone': 'UTC'},
        'end': {'dateTime': end_time_iso, 'timeZone': 'UTC'},
        'attendees': {'email': email},
        'conferenceData': {
            'createRequest': {
                'requestId': str(uuid.uuid4()), # Unique ID for Meet link generation
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        },
    }

    event = service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1,
        sendUpdates='all' 
    ).execute()

    return {
        "status": "success",
        "meeting_link": event.get('hangoutLink'),
        "event_id": event.get('id')
    }