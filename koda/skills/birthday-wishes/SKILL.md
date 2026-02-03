---
name: birthday-wishes
description: Automatic birthday detection and personalized wishes
metadata: {"koda":{"emoji":"🎂","always":true}}
---

# Birthday Wishes

Automatically detect birthdays from contacts and send personalized wishes.

## Setup

Configure in `~/.koda/config.json`:

```json
{
  "integrations": {
    "birthday": {
      "enabled": true,
      "reminder_days_before": 1,
      "send_via": "whatsapp",
      "default_message_template": "Gefeliciteerd met je verjaardag, {name}! 🎂🎉"
    }
  }
}
```

## Daily Birthday Check

Set up a cron job to check birthdays daily:

```bash
koda cron add --name "birthday-check" \
  --message "Check for birthdays today. For each birthday, generate a unique, personal birthday message and send it via WhatsApp. Use the contacts tool to get birthday info." \
  --cron "0 8 * * *"
```

## How to Use

### Check today's birthdays
Use the contacts tool:
```json
{"action": "birthdays_today"}
```

### Check upcoming birthdays
```json
{"action": "birthdays_upcoming", "days": 7}
```

### Send a birthday wish
After finding a birthday, compose a personal message and send via the message tool.

## Message Templates

The default template uses these variables:
- `{name}` - First name of the contact
- `{full_name}` - Full name
- `{age}` - Age they're turning (if known)
- `{owner}` - Your name (the owner)

## Personalization Tips

When generating birthday messages:

1. **Be unique** - Don't use the same message for everyone
2. **Consider the relationship** - Professional vs personal contacts
3. **Mention milestones** - 30, 40, 50 etc. are special
4. **Add emojis** - Makes messages more festive 🎉🎂🎁
5. **Use their language** - Dutch for Dutch contacts

## Example Messages

**Casual friend:**
"Hey {name}! Gefeliciteerd met je verjaardag! 🎉 Hopelijk wordt het een topdag. Proost! 🥳"

**Professional contact:**
"Beste {name}, van harte gefeliciteerd met je verjaardag. Ik wens je een fijne dag! Met vriendelijke groet"

**Milestone birthday:**
"Wauw, {name}! De grote {age}! 🎂 Gefeliciteerd met deze bijzondere mijlpaal. Dat er nog vele mooie jaren mogen volgen! 🌟"
