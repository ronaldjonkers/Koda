# 📅 Scheduler Guide - Automating Tasks with Koda

This guide explains how to use Koda's scheduler to automate tasks, including how the AI can generate scripts that run on a schedule.

## 🚀 Quick Start

### View Current Tasks
```bash
koda cron list
```

### Add a Daily Task
```bash
koda cron add -n "Morning Briefing" \
  -s "0 8 * * *" \
  -p "Get today's calendar events, check for birthdays, and send a summary to WhatsApp" \
  -d "whatsapp:+31612345678"
```

### Add an Hourly Task
```bash
koda cron add -n "Email Check" \
  -s "hourly" \
  -p "Check for important unread emails and notify if any high-priority ones exist"
```

### Run a Task Manually
```bash
koda cron run --id abc123
```

## 📖 Understanding Schedules

### Cron Expressions
Standard cron format: `minute hour day month weekday`

| Expression | Meaning |
|------------|---------|
| `0 8 * * *` | Daily at 8:00 AM |
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `0 */2 * * *` | Every 2 hours |
| `30 8 * * 1` | Mondays at 8:30 AM |
| `0 0 * * 0` | Weekly on Sundays at midnight |

### Shortcuts
- `daily` = Every day at 8:00 AM
- `hourly` = Every hour
- `every 30m` = Every 30 minutes
- `every 2h` = Every 2 hours

### One-time Tasks
Use ISO datetime format for one-time tasks:
```bash
koda cron add -n "Reminder" -s "2024-12-25T09:00:00" -p "Call mom"
```

## 🤖 AI-Generated Scripts on a Schedule

One of Koda's most powerful features is the ability to:
1. **Generate scripts** using the AI
2. **Save them** to the workspace
3. **Schedule them** to run automatically

### Example: Daily Sales Report

**Step 1:** Ask the AI to generate a script
```
Generate a Python script that:
1. Reads sales data from ~/data/sales.csv
2. Calculates daily totals
3. Sends a summary to my WhatsApp
```

**Step 2:** Save the script
The AI will use the `script` tool to save the generated code to `~/.koda/workspace/scripts/daily_sales_report.py`

**Step 3:** Create a scheduled task
```bash
koda cron add \
  -n "Daily Sales Report" \
  -s "0 9 * * *" \
  -p "Execute the script at ~/.koda/workspace/scripts/daily_sales_report.py and send the output to WhatsApp" \
  -d "whatsapp:+31612345678"
```

Or let the AI do it all:
```
Create a daily task at 9am that runs the sales report script and sends me the results on WhatsApp
```

## 📝 Common Automation Patterns

### 1. Daily Morning Briefing
```bash
koda cron add \
  -n "Morning Briefing" \
  -s "daily" \
  -p "Generate a morning briefing with today's agenda, birthdays, weather, and send via WhatsApp" \
  -d "whatsapp:+31612345678"
```

### 2. Birthday Reminders
```bash
koda cron add \
  -n "Birthday Check" \
  -s "0 9 * * *" \
  -p "Check contacts for birthdays today and send congratulatory message suggestions" \
  -d "whatsapp:+31612345678"
```

### 3. Email Digest
```bash
koda cron add \
  -n "Email Digest" \
  -s "0 8,13 * * 1-5" \
  -p "Check for important unread emails and send a summary" \
  -d "whatsapp:+31612345678"
```

### 4. Weekly Report Generation
```bash
koda cron add \
  -n "Weekly Report" \
  -s "0 17 * * 5" \
  -p "Generate a weekly activity report from calendar and email, save to ~/reports/"
```

### 5. Data Backup
```bash
koda cron add \
  -n "Daily Backup" \
  -s "0 2 * * *" \
  -p "Run backup script at ~/scripts/backup.sh"
```

## 🔧 Managing Tasks

### List All Tasks
```bash
koda cron list
```

Output:
```
Scheduled Tasks (3 total)

ID       Name              Schedule         Status      Next Run
abc123   Morning Briefing  cron: 0 8 * * *  ✅ Enabled  2024-12-25 08:00
def456   Email Check       every 60m        ✅ Enabled  2024-12-25 14:30
ghi789   Weekly Report     cron: 0 17 * * 5 ✅ Enabled  2024-12-27 17:00
```

### Check Scheduler Status
```bash
koda cron status
```

### Disable a Task (Keep but don't run)
```bash
koda cron disable --id abc123
```

### Re-enable a Task
```bash
koda cron enable --id abc123
```

### Remove a Task Permanently
```bash
koda cron remove --id abc123
```

### Run a Task Immediately (for testing)
```bash
koda cron run --id abc123
```

## 🛠️ How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Koda Gateway                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Cron Service │  │  Agent Loop  │  │  Scheduler   │      │
│  │              │  │              │  │    Tool      │      │
│  │ • Timer      │──│ • Execute    │  │              │      │
│  │ • Jobs.json  │  │   jobs       │  │ • Create     │      │
│  │ • Persistence│  │ • Callback   │  │ • List       │      │
│  └──────────────┘  └──────────────┘  │ • Manage     │      │
│          │                           └──────────────┘      │
│          │                                   ▲              │
│          └───────────────────────────────────┘              │
│                     (AI invokes tool)                        │
└─────────────────────────────────────────────────────────────┘
```

### Job Storage
Jobs are stored in `~/.koda/data/cron/jobs.json`:

```json
{
  "version": 1,
  "jobs": [
    {
      "id": "abc123",
      "name": "Morning Briefing",
      "enabled": true,
      "schedule": {
        "kind": "cron",
        "expr": "0 8 * * *",
        "tz": "Europe/Amsterdam"
      },
      "payload": {
        "message": "Generate morning briefing...",
        "deliver": true,
        "channel": "whatsapp",
        "to": "+31612345678"
      },
      "state": {
        "nextRunAtMs": 1703491200000,
        "lastRunAtMs": 1703404800000,
        "lastStatus": "ok"
      }
    }
  ]
}
```

## 🐛 Troubleshooting

### Tasks Not Running

1. **Check if gateway is running**
   ```bash
   koda gateway
   ```
   The scheduler only runs when the gateway is active.

2. **Check scheduler status**
   ```bash
   koda cron status
   ```

3. **Verify job is enabled**
   ```bash
   koda cron list
   ```
   Look for "✅ Enabled" status.

4. **Check logs**
   Look for cron-related messages in the gateway output:
   - `⏰ X job(s) due for execution`
   - `🚀 Executing cron job '...'`
   - `✅ Cron job '...' completed`
   - `❌ Cron job '...' failed`

5. **Test manually**
   ```bash
   koda cron run --id <task_id>
   ```

### Common Issues

**Issue:** "No on_job callback configured"
- **Cause:** The gateway isn't running or the scheduler wasn't initialized properly
- **Solution:** Restart the gateway

**Issue:** Jobs show next run in the past
- **Cause:** The scheduler was stopped and missed the scheduled time
- **Solution:** The scheduler will automatically reschedule on next tick

**Issue:** High CPU usage
- **Cause:** Too many jobs scheduled with very short intervals
- **Solution:** Reduce frequency or consolidate jobs

## 💡 Advanced Usage

### Script + Schedule Combo

Let the AI create a complete automation:

```
Create a Python script that monitors my email for messages from 
important clients and sends me a WhatsApp alert. Then schedule 
it to run every 30 minutes during business hours (9-17 on weekdays).
```

The AI will:
1. Generate the script
2. Save it to `~/.koda/workspace/scripts/email_monitor.py`
3. Create a cron job with schedule `*/30 9-17 * * 1-5`

### Chained Tasks

Create tasks that depend on each other:

```bash
# Task 1: Generate report at 8am
koda cron add -n "Generate Report" -s "0 8 * * *" \
  -p "Generate daily report and save to ~/reports/daily_$(date +%Y%m%d).txt"

# Task 2: Email report at 8:30am  
koda cron add -n "Email Report" -s "30 8 * * *" \
  -p "Email the daily report from ~/reports/ to manager@company.com"
```

### Conditional Execution

Use the AI to make decisions:

```bash
koda cron add -n "Smart Email Check" -s "hourly" \
  -p "Check emails. If any high-priority emails from boss@company.com exist, send immediate WhatsApp alert. Otherwise, do nothing."
```

## 📊 Monitoring

### View Recent Executions
```bash
grep "Cron job" ~/.koda/logs/gateway.log
```

### Check Success Rate
```bash
koda cron list | grep -E "(✅|❌)"
```

### Get Detailed Job Info
```bash
# The AI can help analyze
koda agent -m "Analyze my scheduled tasks and suggest optimizations"
```

## 🔒 Security Considerations

1. **Scripts run with your user permissions**
   - Be careful with scripts that modify system files
   - Test scripts manually before scheduling

2. **Credentials in scripts**
   - Don't hardcode passwords in scheduled scripts
   - Use environment variables or the 1Password integration

3. **Network access**
   - Scripts can make network requests
   - Be mindful of rate limits when scheduling frequent tasks

## 🎯 Best Practices

1. **Name tasks descriptively**
   - Good: `Daily Sales Report`
   - Bad: `Task 1`

2. **Set appropriate intervals**
   - Don't check email every minute
   - Consider API rate limits

3. **Test before scheduling**
   - Run scripts manually first
   - Use `koda cron run --id <id>` to test

4. **Monitor and maintain**
   - Check logs periodically
   - Disable unused tasks
   - Update prompts as needs change

5. **Use the AI**
   - Let the AI help write complex scripts
   - Ask for suggestions on automation
   - Use natural language for scheduling

## 📚 Examples

### Development Automation
```bash
# Daily dependency check
koda cron add -n "Dependency Check" -s "daily" \
  -p "Check for outdated npm packages in ~/projects/ and notify if any critical updates exist"

# Weekly backup to S3
koda cron add -n "S3 Backup" -s "0 2 * * 0" \
  -p "Run aws s3 sync ~/important-docs/ s3://my-backup-bucket/"
```

### Business Automation
```bash
# Daily competitor price check
koda cron add -n "Price Check" -s "0 9 * * *" \
  -p "Scrape competitor prices and alert if any are lower than ours"

# Weekly team report
koda cron add -n "Team Report" -s "0 17 * * 5" \
  -p "Generate team activity report from calendar and email, save to ~/reports/team_$(date +%Y%m%d).pdf"
```

### Personal Automation
```bash
# Daily weather + outfit suggestion
koda cron add -n "Weather & Outfit" -s "0 7 * * *" \
  -p "Get weather for Amsterdam, suggest outfit, send to WhatsApp" \
  -d "whatsapp:+31612345678"

# Weekly meal planning
koda cron add -n "Meal Plan" -s "0 10 * * 6" \
  -p "Generate weekly meal plan based on calendar (busy days = quick meals), create shopping list"
```

---

**Need help?** Ask the AI:
- "Show me my scheduled tasks"
- "Help me create a daily automation for..."
- "Why isn't my scheduled task running?"
- "Generate a script to automate..."
