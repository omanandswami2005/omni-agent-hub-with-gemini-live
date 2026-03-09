"""ADK session management — Agent Engine Sessions (primary) + Firestore (fallback).

Uses Vertex AI Agent Engine Sessions for managed stateful persistence.
Survives Cloud Run restarts, scaling events, redeployments.
Falls back to Firestore-backed InMemorySessionService for local dev.
"""

# TODO: Implement session service:
#   - Production: Agent Engine Sessions (google.cloud.agent_engine)
#   - Dev: InMemorySessionService (google.adk.sessions)
#   - create_session(user_id) → new session
#   - get_session(user_id, session_id) → retrieve + resume
#   - list_sessions(user_id) → session history
#   - SessionResumptionConfig for WebSocket reconnection
