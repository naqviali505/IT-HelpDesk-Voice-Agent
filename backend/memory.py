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

        while len(self.history) > self.limit:
            removed = self.history.pop(0)
            if removed.get("role") == "assistant" and removed.get("tool_calls"):
                tool_ids = {tc["id"] for tc in removed.get("tool_calls", [])}

                self.history = [
                    msg for msg in self.history
                    if not (
                        msg.get("role") == "tool" and
                        msg.get("tool_call_id") in tool_ids
                    )
                ]

    def get_messages(self):
        return list(self.history)