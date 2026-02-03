---
name: contacts
description: Access iCloud/macOS Contacts for contact info and birthdays
metadata: {"koda":{"emoji":"👥","always":true}}
---

# Contacts & Birthdays

Access contacts from macOS Contacts app (synced with iCloud).

## Setup

**Local access (recommended):** No setup needed on macOS. Uses the native Contacts app via AppleScript.

**iCloud access (optional):** Configure in `~/.koda/config.json`:

```json
{
  "integrations": {
    "icloud": {
      "enabled": true,
      "apple_id": "your@icloud.com",
      "password": "app-specific-password"
    }
  }
}
```

Use an app-specific password from appleid.apple.com for security.

## Available Actions

Use the `contacts` tool:

### Search contacts
```json
{"action": "search", "query": "John"}
```

### Find contact by phone
```json
{"action": "find_by_phone", "phone": "+31612345678"}
```

### Get today's birthdays
```json
{"action": "birthdays_today"}
```

### Get upcoming birthdays
```json
{"action": "birthdays_upcoming", "days": 7}
```

### List all contacts
```json
{"action": "list", "max_results": 50}
```

## Birthday Reminders

Combine with cron jobs for automatic birthday reminders:

```bash
koda cron add --name "birthday-check" --message "Check for birthdays today and send wishes" --cron "0 8 * * *"
```

## Tips

- Phone numbers are normalized for matching
- Birthday ages are calculated automatically
- Works with contacts synced from iCloud, Google, or Exchange
