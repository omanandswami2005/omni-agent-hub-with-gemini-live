## Notifications + Cron Jobs

### Why it's Confusing

You're mixing up two separate concepts:
1. **Scheduled actions** — "do X at time Y"
2. **Notification delivery** — "tell me about it via channel Z"

These should be independent. Not every scheduled action needs a notification. Not every notification comes from a scheduled action.

### Correct Mental Model

**A `ScheduledTask` has an optional `NotificationRule`:**

```
ScheduledTask
├── id
├── action           → what to actually DO  
├── schedule         → when (one-time or recurring)
└── notify_rule?     → optional: how/when to tell the user
    ├── channel      → "email" | "push" | "sms"
    ├── condition    → when to fire (always / on_result_condition)
    └── message      → template like "Your summary: {result.summary}"
```

### Voice Interaction Examples

**Example 1 — The reminder (task IS the notification):**
```
User: "Remind me of John's birthday on March 15"
→ ScheduledTask {
    action: "send_notification",
    schedule: "2026-03-15 09:00",
    message: "🎂 Today is John's birthday!"
  }
→ No separate notify_rule — the action itself IS the notification
```

**Example 2 — Task with result, user wants email:**
```
User: "Every Monday, fetch my portfolio and email me a summary"
→ ScheduledTask {
    action: "fetch_portfolio_and_summarize",
    schedule: "0 9 * * MON",
    notify_rule: {
      channel: "email",
      condition: "always",
      message: "Here's your weekly portfolio summary:\n{result.summary}"
    }
  }
```

**Example 3 — Task with conditional notification:**
```
User: "Check my server every 5 minutes, but only alert me if it's down"
→ ScheduledTask {
    action: "check_server_health",
    schedule: "*/5 * * * *",
    notify_rule: {
      channel: "email",
      condition: "result.status == 'error'",
      message: "⚠️ Server issue detected: {result.error}"
    }
  }
→ Runs silently every 5 min, email ONLY fires when condition is true
```

**Example 4 — Agent-triggered notification (no schedule):**
```
User: "Email me when the code execution finishes"
→ No cron needed — the execute_code tool's on_complete hook fires a notification
→ This is just a direct notification call, not a scheduled task
```

### Cloud Run vs Cloud Scheduler/Tasks

| Use case | Best option |
|---|---|
| **One-off, specific time** (birthday reminder, reminder in 2 hours) | **Cloud Tasks** — enqueue a task with a future ETA |
| **Recurring on a cron pattern** (every Monday, every 5 min) | **Cloud Scheduler** → triggers a Cloud Run endpoint |
| **Triggered by agent mid-conversation** (execute code then notify me) | **Direct call** — no scheduler needed |

Both Cloud Tasks and Cloud Scheduler just call your backend's `/internal/run-task/{task_id}` endpoint. Your backend then executes the action and optionally sends the notification.

### Courier Integration Design

User-managed, not you-managed:

```
User adds Courier API key in Settings (web dashboard)
  → Stored in Secret Manager under {user_id}/courier_api_key

When notification fires:
  → NotificationService.send(user_id, channel, message)
  → Loads correct key from Secret Manager
  → Calls Courier MCP / Resend API / etc.
```

This way YOUR backend code has zero hardcoded API keys. Each user brings their own Courier key. If they haven't set one, fallback to a default transport you control (e.g. your own SendGrid key for free-tier notifications, their key for custom channels).

---