"""In-memory ConnectionManager — tracks connected WebSocket clients per user.

This is the Day 1 infra class (~100 lines) that replaces Socket.IO rooms.
Handles: user device registry, room broadcast, auth, disconnect cleanup.
"""

# TODO: Implement ConnectionManager with:
#   - register(user_id, client_type, ws) → add to registry
#   - unregister(user_id, client_type) → remove from registry
#   - get_clients(user_id) → list all connected clients for user
#   - broadcast(user_id, message) → send to all user's devices
#   - send_to(user_id, client_type, message) → send to specific device
#   - is_online(user_id, client_type) → check if specific client connected
