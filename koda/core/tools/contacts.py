"""Contacts tool for iCloud/macOS Contacts."""

from datetime import date, timedelta
from typing import Any

from koda.core.tools.base import Tool


class ContactsTool(Tool):
    """Tool for accessing contacts and birthdays."""
    
    name = "contacts"
    description = """Access iCloud/macOS Contacts to search contacts, get birthday info, and find contact details.
    
Actions:
- list: List all contacts
- search: Search contacts by name, email, or phone
- birthdays_today: Get contacts with birthdays today
- birthdays_upcoming: Get upcoming birthdays
- find_by_phone: Find contact by phone number

Examples:
- Search: {"action": "search", "query": "John"}
- Today's birthdays: {"action": "birthdays_today"}
- Upcoming birthdays: {"action": "birthdays_upcoming", "days": 7}
- Find by phone: {"action": "find_by_phone", "phone": "+31612345678"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search", "birthdays_today", "birthdays_upcoming", "find_by_phone"],
                "description": "Action to perform"
            },
            "query": {
                "type": "string",
                "description": "Search query (for search action)"
            },
            "phone": {
                "type": "string",
                "description": "Phone number to find (for find_by_phone action)"
            },
            "days": {
                "type": "integer",
                "description": "Days to look ahead (for birthdays_upcoming, default: 7)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results"
            },
        },
        "required": ["action"]
    }
    
    def __init__(self, use_local: bool = True, apple_id: str | None = None, password: str | None = None):
        self.use_local = use_local
        self.apple_id = apple_id
        self.password = password
        self._client = None
    
    def _get_client(self):
        if not self._client:
            from koda.integrations.icloud_contacts import ICloudContactsClient
            self._client = ICloudContactsClient(
                apple_id=self.apple_id,
                password=self.password,
                use_local=self.use_local
            )
        return self._client
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list")
        max_results = kwargs.get("max_results", 50)
        
        try:
            client = self._get_client()
            
            if action == "list":
                contacts = client.get_contacts()[:max_results]
                return self._format_contacts(contacts, "All contacts")
            
            elif action == "search":
                query = kwargs.get("query", "")
                if not query:
                    return "Error: Search query required"
                contacts = client.search_contacts(query)[:max_results]
                return self._format_contacts(contacts, f"Search: {query}")
            
            elif action == "birthdays_today":
                contacts = client.get_birthdays_on_date()
                if not contacts:
                    return "No birthdays today!"
                return self._format_birthdays(contacts, "Birthdays today")
            
            elif action == "birthdays_upcoming":
                days = kwargs.get("days", 7)
                contacts = client.get_upcoming_birthdays(days=days)
                if not contacts:
                    return f"No birthdays in the next {days} days."
                return self._format_birthdays(contacts, f"Upcoming birthdays (next {days} days)")
            
            elif action == "find_by_phone":
                phone = kwargs.get("phone", "")
                if not phone:
                    return "Error: Phone number required"
                contact = client.get_contact_by_phone(phone)
                if not contact:
                    return f"No contact found for {phone}"
                return self._format_contact_detail(contact)
            
            else:
                return f"Error: Unknown action: {action}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _format_contacts(self, contacts: list, title: str) -> str:
        if not contacts:
            return f"{title}: No contacts found."
        
        output = f"{title} ({len(contacts)}):\n\n"
        for c in contacts:
            output += f"• {c.get('name', '(No name)')}\n"
            if c.get("company"):
                output += f"  Company: {c['company']}\n"
            if c.get("phones"):
                phones = c["phones"] if isinstance(c["phones"], list) else [c["phones"]]
                output += f"  Phone: {', '.join(phones)}\n"
            if c.get("emails"):
                emails = c["emails"] if isinstance(c["emails"], list) else [c["emails"]]
                output += f"  Email: {', '.join(emails)}\n"
            output += "\n"
        
        return output
    
    def _format_birthdays(self, contacts: list, title: str) -> str:
        if not contacts:
            return f"{title}: No birthdays found."
        
        output = f"{title} ({len(contacts)}):\n\n"
        for c in contacts:
            days_until = c.get("days_until", 0)
            age = c.get("age")
            
            if days_until == 0:
                when = "TODAY! 🎂"
            elif days_until == 1:
                when = "tomorrow"
            else:
                when = f"in {days_until} days"
            
            age_str = f" (turns {age})" if age else ""
            
            output += f"• {c.get('name', '(No name)')}{age_str} - {when}\n"
            if c.get("phones"):
                phones = c["phones"] if isinstance(c["phones"], list) else [c["phones"]]
                output += f"  Phone: {', '.join(phones)}\n"
            output += "\n"
        
        return output
    
    def _format_contact_detail(self, contact: dict) -> str:
        output = f"Contact: {contact.get('name', '(No name)')}\n"
        output += "=" * 40 + "\n"
        
        if contact.get("firstName"):
            output += f"First name: {contact['firstName']}\n"
        if contact.get("lastName"):
            output += f"Last name: {contact['lastName']}\n"
        if contact.get("company"):
            output += f"Company: {contact['company']}\n"
        if contact.get("birthday"):
            output += f"Birthday: {contact['birthday']}\n"
        if contact.get("phones"):
            phones = contact["phones"] if isinstance(contact["phones"], list) else [contact["phones"]]
            for p in phones:
                output += f"Phone: {p}\n"
        if contact.get("emails"):
            emails = contact["emails"] if isinstance(contact["emails"], list) else [contact["emails"]]
            for e in emails:
                output += f"Email: {e}\n"
        
        return output
