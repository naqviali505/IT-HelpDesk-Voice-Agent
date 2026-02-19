tools = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Find the first available 30-minute technician slot in the next 7 days.",
            "parameters": {
                "type": "object",
                "properties": {},
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_meeting",
            "description": "Finalize the booking. ONLY call this after checking availability, confirming time, and verifying email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start_time_iso": {"type": "string"},
                    "end_time_iso": {"type": "string"},
                    "email": {"type": "string"}
                },
                "required": ["summary", "start_time_iso", "end_time_iso", "email"]
            }
        }
    }
]
