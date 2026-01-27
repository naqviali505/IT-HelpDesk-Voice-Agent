tools = [
    {
        "type": "function",
        "function": {
            "name": "create_meeting",
            "description": "Finalize the booking. ONLY call this after checking availability, confirming a time with the user, and asking the user to spell their email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Subject of the meeting (e.g., Internet Issue)"},
                    "start_time_iso": {"type": "string", "description": "ISO 8601 format time (e.g., 2026-01-22T10:00:00Z)"},
                    "end_time_iso": {"type": "string", "description": "ISO 8601 format time (usually 30 mins after start)"},
                    "email": {"type": "string", "description": "The customer's email address"}
                },
                "required": ["summary", "start_time_iso", "end_time_iso", "email"]
            }
        }
    }
]