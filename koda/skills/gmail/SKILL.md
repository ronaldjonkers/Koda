---
name: gmail
description: Read and send Gmail emails
metadata: {"koda":{"emoji":"📧","always":true}}
---

# Gmail

Read, search, and send emails via Gmail.

## Setup

1. Use same Google Cloud project as Calendar
2. Enable Gmail API in Google Cloud Console
3. Add Gmail scopes to OAuth consent screen
4. Uses same credentials file: `~/.koda/google_credentials.json`

## Available Actions

Use the `gmail` tool:

### Get inbox messages
```json
{"action": "inbox", "max_results": 10}
```

### Get unread messages
```json
{"action": "unread"}
```

### Search emails
```json
{"action": "search", "query": "from:boss@company.com is:unread"}
```

Gmail search operators:
- `from:` - sender
- `to:` - recipient
- `subject:` - subject line
- `is:unread` / `is:read`
- `has:attachment`
- `after:2024/01/01` / `before:2024/01/31`

### Read full email
```json
{"action": "read", "message_id": "abc123..."}
```

### Send email
```json
{
  "action": "send",
  "to": "recipient@example.com",
  "subject": "Hello!",
  "body": "This is the email content."
}
```

### Reply to email
```json
{
  "action": "reply",
  "message_id": "abc123...",
  "body": "Thank you for your message..."
}
```

## Tips

- Message IDs are shown in list results
- Use search to filter by date, sender, etc.
- Reply maintains the conversation thread
