class ChatMemory:
    def __init__(self, limit=10): # Increased limit to account for tool turns
        self.history = []
        self.limit = limit

    def add_message(self, role, content=None, **kwargs):

        if content is None and role != "assistant":
            content = ""

        message = {"role": role, "content": content}
        message.update(kwargs)
        self.history.append(message)
        
        # Keep only the most recent messages
        while len(self.history) > self.limit:
            removed = self.history.pop(0)

            # If we removed a tool message, remove the next one too
            if removed.get("role") == "assistant" and removed.get("tool_calls"):
                if self.history and self.history[0].get("role") == "tool":
                    self.history.pop(0)

    def get_messages(self):
        return list(self.history)