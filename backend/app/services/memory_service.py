"""Agent Engine Memory Bank — long-term memory across sessions.

Stores/retrieves personalized info from past conversations.
Agent remembers user preferences, past queries, and context across sessions.
"""

# TODO: Implement memory bank service:
#   - store_memory(user_id, facts) → persist key facts after session ends
#   - recall_memories(user_id, context) → retrieve relevant memories for new session
#   - Uses Vertex AI Agent Engine Memory Bank (GA)
#   - Inject recalled memories into agent system instructions at session start
