class ChatMemory:
    def __init__(self, limit=10): # Increased limit to account for tool turns
        self.history = []
        self.limit = limit

    def add_message(self, role, content=None, **kwargs):
        # Build the message dictionary dynamically
        message = {"role": role, "content": content}
        
        # Add any extra fields (like tool_calls or tool_call_id)
        message.update(kwargs)
        
        self.history.append(message)
        
        # Keep only the most recent messages
        if len(self.history) > self.limit:
            self.history.pop(0)

    def get_messages(self):
        return self.history