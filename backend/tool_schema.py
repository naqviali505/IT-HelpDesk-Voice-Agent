tools = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Find the first available 30-minute technician slot in the next 7 days.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_meeting",
            "description": (
                "Schedule the technician meeting. "
                "ONLY call this after the user confirms the time slot and verifies their email. "
                "Never guess an email address."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Short meeting title"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address spelled by the user"
                    }
                },
                "required": ["summary", "email"],
                "additionalProperties": False
            }
        }
    }
]