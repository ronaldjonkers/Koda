---
name: whatsapp-assistant
description: AI assistant for WhatsApp - auto-respond to specific contacts
metadata: {"koda":{"emoji":"💬","always":true}}
---

# WhatsApp AI Assistant

Automatically handle WhatsApp conversations for specific contacts.

## Setup

Configure in `~/.koda/config.json`:

```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "allowFrom": ["+31612345678", "+31687654321"]
    }
  },
  "integrations": {
    "whatsapp_auto_reply": {
      "enabled": true,
      "contacts": ["+31612345678"],
      "owner_name": "Ronald",
      "greeting": "Hallo! Ik ben de AI-assistent van {owner}. Hoe kan ik je helpen?"
    }
  }
}
```

## How It Works

1. Messages from allowed contacts (`allowFrom`) are processed by the AI
2. Contacts in `whatsapp_auto_reply.contacts` get an AI-powered response
3. The AI can access calendar, email, and contacts to provide helpful answers

## Conversation Guidelines

When responding to WhatsApp messages:

1. **Be concise** - WhatsApp messages should be short and to the point
2. **Be friendly** - Use a casual, helpful tone
3. **Use the owner's context** - You represent the owner, answer as their assistant
4. **Handle common requests:**
   - Schedule questions → Check calendar
   - Contact info requests → Search contacts
   - Availability questions → Check calendar for free slots

## Example Interactions

**User:** "Is Ronald morgen beschikbaar voor een meeting?"
**Assistant:** *Checks calendar* "Ronald heeft morgen een meeting om 10:00 en 14:00. Hij is vrij van 11:00-13:30 en na 15:00. Zal ik een afspraak inplannen?"

**User:** "Kun je Ronald vragen om mij te bellen?"
**Assistant:** "Ik geef het door aan Ronald. Wat is je telefoonnummer en waar gaat het over?"

## Tips

- The AI maintains conversation context per contact
- Use cron jobs to send proactive messages (reminders, birthday wishes)
- Combine with contacts skill to personalize responses
