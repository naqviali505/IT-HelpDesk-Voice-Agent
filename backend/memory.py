class ChatMemory:
    def __init__(self, limit=6):
        self.history = []
        self.limit = limit

    def add_message(self, role, content):
        self.history.append({"role": role, "content": content})
        # Keep only the most recent messages
        if len(self.history) > self.limit:
            self.history.pop(0)

    def get_messages(self):
        return self.history