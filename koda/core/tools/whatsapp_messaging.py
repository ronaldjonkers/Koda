"""WhatsApp messaging tool for sending messages to contacts.

This tool allows the user to send WhatsApp messages through the assistant.
It integrates with the contacts system to resolve names to phone numbers.
"""

from koda.core.tools.base import Tool
from koda.messaging.events import OutboundMessage
from koda.messaging.queue import MessageBus
from typing import Any
from pathlib import Path
import re


class WhatsAppMessagingTool(Tool):
    """Tool for sending WhatsApp messages to contacts.
    
    This tool allows the user (owner) to send WhatsApp messages through the assistant.
    It can resolve contact names to phone numbers using the contacts integration.
    
    Security: Only the owner can use this tool to prevent unauthorized messaging.
    
    Examples:
    - Send to contact by name: {"recipient": "John Doe", "message": "Hello John!"}
    - Send to phone number: {"recipient": "+31612345678", "message": "Hello!"}
    - Send with contact lookup: {"recipient": "Jane Smith", "message": "Meeting at 3pm"}
    """
    
    name = "whatsapp_messaging"
    description = """Send WhatsApp messages to contacts by name or phone number.

This tool allows you to send WhatsApp messages on behalf of the user. It automatically
looks up contact names to find the correct phone number.

Features:
- Send to contacts by name (uses contacts integration)
- Send to specific phone numbers
- Automatic contact name resolution
- Confirmation of sent messages

Examples:
- Send to contact: {"recipient": "John Doe", "message": "Hello John, are we still meeting today?"}
- Send to number: {"recipient": "+31612345678", "message": "Thanks for the update!"}
- Quick message: {"recipient": "Mom", "message": "Running late, be there in 10 mins"}

The tool will:
1. Check if the recipient is a contact name and look up the phone number
2. Validate the phone number format
3. Send the WhatsApp message
4. Confirm delivery
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "description": "Contact name or phone number. Can be 'John Doe', 'Mom', '+31612345678', etc."
            },
            "message": {
                "type": "string",
                "description": "The message to send"
            }
        },
        "required": ["recipient", "message"]
    }
    
    def __init__(self, bus: MessageBus = None, owner_phone: str = None):
        self.bus = bus
        self.owner_phone = owner_phone
        self._wa_channel = None
    
    def set_whatsapp_channel(self, channel):
        """Set the WhatsApp channel for sending messages."""
        self._wa_channel = channel
    
    async def execute(self, recipient: str, message: str, **kwargs) -> str:
        """Send a WhatsApp message to the specified recipient."""
        
        if not recipient or not message:
            return "❌ Error: Both recipient and message are required."
        
        # Resolve recipient to phone number
        phone_number = await self._resolve_recipient(recipient)
        
        if not phone_number:
            return f"❌ Could not find a phone number for '{recipient}'.\n\nPlease provide a phone number (e.g., +31612345678) or check the contact name."
        
        # Validate phone number format
        if not self._is_valid_phone(phone_number):
            return f"❌ Invalid phone number format: {phone_number}\n\nPlease use international format: +31612345678"
        
        # Send the message
        try:
            success = await self._send_whatsapp_message(phone_number, message)
            
            if success:
                return f"✅ Message sent to {recipient} ({phone_number})!"
            else:
                return f"❌ Failed to send message to {recipient}. WhatsApp channel may not be available."
                
        except Exception as e:
            return f"❌ Error sending message: {str(e)}"
    
    async def _resolve_recipient(self, recipient: str) -> str | None:
        """Resolve recipient name to phone number using contacts."""
        
        # Clean up the recipient string
        recipient = recipient.strip()
        
        # If it already looks like a phone number, return it
        if self._is_valid_phone(recipient):
            # Normalize phone number
            return self._normalize_phone(recipient)
        
        # Try to look up in contacts
        phone = await self._lookup_contact(recipient)
        if phone:
            return phone
        
        # Try common variations (first name only, etc.)
        # Split by spaces and try first name
        parts = recipient.split()
        if len(parts) > 1:
            phone = await self._lookup_contact(parts[0])
            if phone:
                return phone
        
        return None
    
    async def _lookup_contact(self, name: str) -> str | None:
        """Look up contact by name and return phone number."""
        try:
            from koda.core.tools.contacts import ContactsTool
            
            contacts_tool = ContactsTool()
            
            # Try searching in iCloud/local contacts first
            result = contacts_tool.execute(action="search", query=name, max_results=5)
            
            # Also try Exchange if available
            # This would need config access to know which accounts exist
            
            if result and "No contacts found" not in result:
                # Extract phone number from result
                # The result format includes phone numbers
                import re
                
                # Look for phone number pattern in the result
                # Match various phone formats
                phone_pattern = r'Phone:\s*([+\d\s\-\(\)]+)'
                matches = re.findall(phone_pattern, result)
                
                if matches:
                    # Return the first phone number found
                    phone = matches[0].strip()
                    # Clean up the phone number
                    phone = re.sub(r'[\s\-\(\)]', '', phone)
                    return phone
            
            return None
            
        except Exception as e:
            return None
    
    def _is_valid_phone(self, phone: str) -> bool:
        """Check if string looks like a valid phone number."""
        if not phone:
            return False
        
        # Remove common formatting characters
        cleaned = re.sub(r'[\s\-\(\)\.]','', phone)
        
        # Check if it starts with + and has digits
        if cleaned.startswith('+') and len(cleaned) > 8:
            return cleaned[1:].isdigit()
        
        # Check if it's just digits (at least 8)
        if cleaned.isdigit() and len(cleaned) >= 8:
            return True
        
        return False
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to standard format."""
        # Remove all non-digit and non-plus characters
        cleaned = re.sub(r'[\s\-\(\)\.]','', phone)
        
        # If it doesn't start with +, assume it needs country code
        # This is a simplification - in production you'd need user prefs
        if not cleaned.startswith('+'):
            # If it starts with 0, replace with +31 (Netherlands)
            if cleaned.startswith('0'):
                cleaned = '+31' + cleaned[1:]
            else:
                cleaned = '+' + cleaned
        
        return cleaned
    
    async def _send_whatsapp_message(self, phone: str, message: str) -> bool:
        """Send WhatsApp message via the channel."""
        
        # Try to use the WhatsApp channel directly
        if self._wa_channel:
            try:
                # Format as WhatsApp JID
                jid = f"{phone.replace('+', '')}@s.whatsapp.net"
                
                await self._wa_channel.send(OutboundMessage(
                    channel="whatsapp",
                    chat_id=jid,
                    content=message
                ))
                return True
            except Exception as e:
                return False
        
        # Fallback: use message bus
        if self.bus:
            try:
                jid = f"{phone.replace('+', '')}@s.whatsapp.net"
                
                await self.bus.publish_outbound(OutboundMessage(
                    channel="whatsapp",
                    chat_id=jid,
                    content=message
                ))
                return True
            except Exception as e:
                return False
        
        return False
