---
name: exchange
description: Access Microsoft Exchange/Outlook calendar and email
metadata: {"koda":{"emoji":"📨"}}
---

# Microsoft Exchange

Access Exchange/Outlook 365 calendar and email.

## Setup

Configure in `~/.koda/config.json`:

```json
{
  "integrations": {
    "exchange": {
      "enabled": true,
      "email": "you@company.com",
      "password": "your-password-or-app-password",
      "server": "outlook.office365.com"
    }
  }
}
```

For Office 365, use `outlook.office365.com`. For on-premise Exchange, use your server address or leave empty for autodiscover.

**Security note:** Use app-specific passwords when possible.

## Calendar Actions

Use the `exchange_calendar` tool:

### List upcoming events
```json
{"action": "list", "days": 7}
```

### Get today's events
```json
{"action": "today"}
```

### Create an event
```json
{
  "action": "create",
  "subject": "Project Meeting",
  "start": "2024-01-15T14:00:00",
  "end": "2024-01-15T15:00:00",
  "location": "Teams",
  "body": "Discuss Q1 goals"
}
```

## Email Actions

Use the `exchange_email` tool:

### Get inbox
```json
{"action": "inbox", "max_results": 10}
```

### Get unread emails
```json
{"action": "unread"}
```

### Read full email
```json
{"action": "read", "message_id": "..."}
```

### Send email
```json
{
  "action": "send",
  "to": ["recipient@company.com"],
  "subject": "Update",
  "body": "Here is the update..."
}
```

### Reply to email
```json
{
  "action": "reply",
  "message_id": "...",
  "body": "Thanks for the information..."
}
```
