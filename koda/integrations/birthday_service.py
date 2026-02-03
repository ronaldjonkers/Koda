"""Birthday reminder and wishes service."""

from datetime import date, datetime
from typing import Any, Callable

from loguru import logger

from koda.integrations.icloud_contacts import ICloudContactsClient


class BirthdayService:
    """
    Service for checking birthdays and sending wishes.
    
    Can be triggered via cron jobs or manually.
    """
    
    def __init__(
        self,
        contacts_client: ICloudContactsClient | None = None,
        send_callback: Callable[[str, str, str], Any] | None = None,
        default_template: str = "Gefeliciteerd met je verjaardag, {name}! 🎂🎉",
        owner_name: str = ""
    ):
        self.contacts_client = contacts_client or ICloudContactsClient(use_local=True)
        self.send_callback = send_callback
        self.default_template = default_template
        self.owner_name = owner_name
    
    def check_birthdays_today(self) -> list[dict[str, Any]]:
        """
        Check for contacts with birthdays today.
        
        Returns:
            List of contacts with birthdays today
        """
        return self.contacts_client.get_birthdays_on_date(date.today())
    
    def check_upcoming_birthdays(self, days: int = 7) -> list[dict[str, Any]]:
        """
        Check for upcoming birthdays.
        
        Args:
            days: Number of days to look ahead
        
        Returns:
            List of contacts with upcoming birthdays
        """
        return self.contacts_client.get_upcoming_birthdays(days=days)
    
    def generate_birthday_message(
        self,
        contact: dict[str, Any],
        template: str | None = None,
        personalized: bool = True
    ) -> str:
        """
        Generate a birthday message for a contact.
        
        Args:
            contact: Contact dictionary with name, age, etc.
            template: Custom message template (uses {name}, {age}, {owner})
            personalized: If True, add personal touches based on contact info
        
        Returns:
            Generated birthday message
        """
        template = template or self.default_template
        
        name = contact.get("name", "").split()[0] if contact.get("name") else "friend"
        age = contact.get("age")
        
        message = template.format(
            name=name,
            full_name=contact.get("name", ""),
            age=age if age else "",
            owner=self.owner_name
        )
        
        if personalized and age:
            if age in [18, 21, 30, 40, 50, 60, 65, 70, 75, 80]:
                message += f"\n\nWat een bijzondere mijlpaal - {age} jaar! 🌟"
        
        return message
    
    async def send_birthday_wish(
        self,
        contact: dict[str, Any],
        channel: str = "whatsapp",
        custom_message: str | None = None
    ) -> dict[str, Any]:
        """
        Send a birthday wish to a contact.
        
        Args:
            contact: Contact dictionary
            channel: Channel to send via (whatsapp, telegram, email)
            custom_message: Custom message (or auto-generate)
        
        Returns:
            Result of sending
        """
        message = custom_message or self.generate_birthday_message(contact)
        
        # Get contact info for the channel
        recipient = None
        
        if channel == "whatsapp":
            phones = contact.get("phones", [])
            if phones:
                recipient = phones[0] if isinstance(phones, list) else phones
        elif channel == "email":
            emails = contact.get("emails", [])
            if emails:
                recipient = emails[0] if isinstance(emails, list) else emails
        elif channel == "telegram":
            # Telegram needs username or chat_id, which we might not have
            recipient = contact.get("telegram_username")
        
        if not recipient:
            return {
                "success": False,
                "error": f"No {channel} contact info for {contact.get('name')}"
            }
        
        if self.send_callback:
            try:
                await self.send_callback(channel, recipient, message)
                logger.info(f"Sent birthday wish to {contact.get('name')} via {channel}")
                return {
                    "success": True,
                    "contact": contact.get("name"),
                    "channel": channel,
                    "recipient": recipient
                }
            except Exception as e:
                logger.error(f"Failed to send birthday wish: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }
        else:
            # No callback, just return the message
            return {
                "success": True,
                "contact": contact.get("name"),
                "channel": channel,
                "recipient": recipient,
                "message": message,
                "note": "No send callback configured - message not actually sent"
            }
    
    async def process_today_birthdays(
        self,
        channel: str = "whatsapp",
        dry_run: bool = False
    ) -> list[dict[str, Any]]:
        """
        Process all birthdays for today - check and optionally send wishes.
        
        Args:
            channel: Channel to send wishes via
            dry_run: If True, don't actually send messages
        
        Returns:
            List of results for each birthday
        """
        birthdays = self.check_birthdays_today()
        results = []
        
        for contact in birthdays:
            if dry_run:
                message = self.generate_birthday_message(contact)
                results.append({
                    "contact": contact.get("name"),
                    "message": message,
                    "dry_run": True
                })
            else:
                result = await self.send_birthday_wish(contact, channel=channel)
                results.append(result)
        
        return results
    
    def format_birthday_report(self, days: int = 7) -> str:
        """
        Generate a formatted report of upcoming birthdays.
        
        Args:
            days: Number of days to look ahead
        
        Returns:
            Formatted birthday report string
        """
        today_birthdays = self.check_birthdays_today()
        upcoming = self.check_upcoming_birthdays(days=days)
        
        # Filter out today's birthdays from upcoming
        upcoming = [b for b in upcoming if b.get("days_until", 0) > 0]
        
        report = "🎂 Birthday Report\n"
        report += "=" * 40 + "\n\n"
        
        if today_birthdays:
            report += "🎉 TODAY'S BIRTHDAYS:\n"
            for b in today_birthdays:
                age = f" (turns {b.get('age')})" if b.get("age") else ""
                report += f"  • {b.get('name')}{age}\n"
            report += "\n"
        else:
            report += "No birthdays today.\n\n"
        
        if upcoming:
            report += f"📅 UPCOMING ({days} days):\n"
            for b in upcoming:
                days_until = b.get("days_until", 0)
                when = "tomorrow" if days_until == 1 else f"in {days_until} days"
                age = f" (turns {b.get('age')})" if b.get("age") else ""
                report += f"  • {b.get('name')}{age} - {when}\n"
        else:
            report += f"No birthdays in the next {days} days.\n"
        
        return report
