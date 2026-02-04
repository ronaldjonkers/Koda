"""Contacts tool for iCloud/macOS and Exchange Contacts."""

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from koda.core.tools.base import Tool

logger = logging.getLogger(__name__)


class ContactsTool(Tool):
    """Tool for accessing contacts from iCloud/macOS or Exchange accounts."""
    
    name = "contacts"
    description = """Access contacts from iCloud/macOS or Exchange accounts.
    
Actions:
- list: List all contacts
- search: Search contacts by name, email, or phone
- birthdays_today: Get contacts with birthdays today (iCloud only)
- birthdays_upcoming: Get upcoming birthdays (iCloud only)
- find_by_phone: Find contact by phone number

Use 'account' parameter to specify Exchange account (e.g., "gosettle").
Leave 'account' empty for iCloud/local contacts.

Examples:
- List iCloud: {"action": "list"}
- List Exchange: {"action": "list", "account": "gosettle"}
- Search Exchange: {"action": "search", "query": "John", "account": "gosettle"}
- Birthdays: {"action": "birthdays_upcoming", "days": 7}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search", "birthdays_today", "birthdays_upcoming", "find_by_phone"],
                "description": "Action to perform"
            },
            "account": {
                "type": "string",
                "description": "Account name for Exchange (e.g., 'gosettle'). Leave empty for iCloud/local."
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
        self._icloud_client = None
        self._exchange_clients = {}
    
    def _get_icloud_client(self):
        if not self._icloud_client:
            from koda.integrations.icloud_contacts import ICloudContactsClient
            self._icloud_client = ICloudContactsClient(
                apple_id=self.apple_id,
                password=self.password,
                use_local=self.use_local
            )
        return self._icloud_client
    
    def _get_exchange_client(self, account_name: str):
        """Get or create Exchange client for account."""
        if account_name in self._exchange_clients:
            return self._exchange_clients[account_name]
        
        # Load account from config
        try:
            from koda.config.loader import load_config
            config = load_config()
            for acc in config.integrations.accounts:
                if acc.name.lower() == account_name.lower() and acc.type == 'exchange':
                    from koda.integrations.exchange_client import ExchangeClient
                    client = ExchangeClient(
                        email=acc.email,
                        password=acc.password,
                        server=acc.server
                    )
                    self._exchange_clients[account_name] = client
                    return client
        except Exception as e:
            logger.error(f"Error loading account config: {e}")
            raise ValueError(f"Could not load account '{account_name}': {e}")
        
        raise ValueError(f"Exchange account '{account_name}' not found")
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list")
        account_name = kwargs.get("account", "")
        max_results = kwargs.get("max_results", 50)
        
        try:
            # Use Exchange if account specified, otherwise iCloud
            if account_name:
                return await self._execute_exchange(action, account_name, kwargs, max_results)
            else:
                return self._execute_icloud(action, kwargs, max_results)
                
        except Exception as e:
            logger.error(f"Contacts error: {e}")
            return f"Error: {str(e)}"
    
    async def _execute_exchange(self, action: str, account_name: str, kwargs: dict, max_results: int) -> str:
        """Execute action on Exchange contacts with timeout."""
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._exchange_action, action, account_name, kwargs, max_results),
                timeout=120.0
            )
            return result
        except asyncio.TimeoutError:
            logger.error("Timeout reading contacts from Exchange")
            return "Error: Timeout reading contacts from Exchange. The server may be slow to respond."
    
    def _exchange_action(self, action: str, account_name: str, kwargs: dict, max_results: int) -> str:
        """Synchronous Exchange action."""
        client = self._get_exchange_client(account_name)
        
        if action == "list":
            contacts = client.list_contacts(max_results=max_results)
            return self._format_contacts(contacts, f"Contacts from {account_name}")
        
        elif action == "search":
            query = kwargs.get("query", "")
            if not query:
                return "Error: Search query required"
            contacts = client.search_contacts(query, max_results=max_results)
            return self._format_contacts(contacts, f"Search '{query}' in {account_name}")
        
        elif action == "find_by_phone":
            phone = kwargs.get("phone", "")
            if not phone:
                return "Error: Phone number required"
            contacts = client.search_contacts(phone, max_results=5)
            if contacts:
                return self._format_contact_detail(contacts[0])
            return f"No contact found for {phone}"
        
        else:
            return f"Error: Action '{action}' not supported for Exchange (only list, search, find_by_phone)"
    
    def _execute_icloud(self, action: str, kwargs: dict, max_results: int) -> str:
        """Execute action on iCloud/local contacts."""
        client = self._get_icloud_client()
        
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
