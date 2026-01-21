import datetime
import os
import uuid
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = r'C:\Users\smali\Desktop\Langchain\gen-lang-client-0113695004-0ea6be6ac616.json'
creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, 
            scopes=SCOPES
        )
def create_meeting(summary, start_time_iso, end_time_iso, email):
    """
    Creates a Google Calendar event with a Google Meet link using a Service Account.
    """
    # 1. Load the Service Account Credentials
    try:
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            raise FileNotFoundError(f"Missing {SERVICE_ACCOUNT_FILE}")

        # 2. Build the Service
        service = build('calendar', 'v3', credentials=creds)

        # 3. Define the Event
        event = {
            'summary': summary,
            'description': 'IT Helpdesk Scheduled Meeting',
            'start': {'dateTime': start_time_iso, 'timeZone': 'UTC'},
            'end': {'dateTime': end_time_iso, 'timeZone': 'UTC'},
            'attendees': [{'email': email}],
            'conferenceData': {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),
                    'conferenceSolutionKey': {'type': 'addOn'}
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
    except Exception as e:
        print(f"Error in function call {e}")

def check_availability():
    """
    Finds the first available 30-minute slot for the technician.
    Working hours: 09:00 - 17:00. Lunch: 13:00 - 14:00.
    """
    service = build('calendar', 'v3', credentials=creds)
    now = datetime.datetime.utcnow()
    
    # Get busy events for the next 7 days
    end_search = now + datetime.timedelta(days=7)
    events_result = service.events().list(
        calendarId='naqviali505@gmail.com',
        timeMin=now.isoformat() + 'Z',
        timeMax=end_search.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    busy_events = events_result.get('items', [])

    # Convert busy events to list of (start, end) datetime objects
    busy_intervals = []
    for event in busy_events:
        s = datetime.datetime.fromisoformat(event['start'].get('dateTime').replace('Z', '+00:00'))
        e = datetime.datetime.fromisoformat(event['end'].get('dateTime').replace('Z', '+00:00'))
        busy_intervals.append((s, e))

    # Search through the next 7 days
    for i in range(8):
        current_date = (now + datetime.timedelta(days=i)).date()
        
        # Define working day window
        day_start = datetime.datetime.combine(current_date, datetime.time(9, 0)).replace(tzinfo=datetime.timezone.utc)
        day_end = datetime.datetime.combine(current_date, datetime.time(17, 0)).replace(tzinfo=datetime.timezone.utc)
        lunch_start = datetime.datetime.combine(current_date, datetime.time(13, 0)).replace(tzinfo=datetime.timezone.utc)
        lunch_end = datetime.datetime.combine(current_date, datetime.time(14, 0)).replace(tzinfo=datetime.timezone.utc)

        # Iterate in 30-minute increments
        current_slot_start = day_start
        while current_slot_start + datetime.timedelta(minutes=30) <= day_end:
            current_slot_end = current_slot_start + datetime.timedelta(minutes=30)
            
            # Skip if it's in the past (for today's search)
            if current_slot_start < now.replace(tzinfo=datetime.timezone.utc):
                current_slot_start += datetime.timedelta(minutes=30)
                continue

            # Skip if it overlaps with lunch (1 PM - 2 PM)
            is_lunch = not (current_slot_end <= lunch_start or current_slot_start >= lunch_end)
            
            # Check if it overlaps with any busy event
            is_busy = any(not (current_slot_end <= b_start or current_slot_start >= b_end) 
                          for b_start, b_end in busy_intervals)

            if not is_lunch and not is_busy:
                # Found the first slot!
                return {
                    "available_slot_start": current_slot_start.isoformat(),
                    "available_slot_end": current_slot_end.isoformat(),
                    "readable_date": current_slot_start.strftime("%A, %B %d"),
                    "readable_time": current_slot_start.strftime("%I:%M %p")
                }
            
            current_slot_start += datetime.timedelta(minutes=30)

    return "No available slots found in the next 7 days."