---
name: google-calendar
description: Manage Google Calendar - view, create, and manage events
metadata: {"koda":{"emoji":"📅","always":true}}
---

# Google Calendar

Access and manage Google Calendar events.

## Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Calendar API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download credentials and save as `~/.koda/google_credentials.json`
5. First use will open browser for authentication

## Available Actions

Use the `google_calendar` tool:

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
  "summary": "Team Meeting",
  "start": "2024-01-15T10:00:00",
  "end": "2024-01-15T11:00:00",
  "location": "Conference Room A",
  "description": "Weekly sync"
}
```

### List all calendars
```json
{"action": "calendars"}
```

## Tips

- Default calendar is "primary" (your main calendar)
- Use ISO format for dates: `YYYY-MM-DDTHH:MM:SS`
- Time zone defaults to Europe/Amsterdam
