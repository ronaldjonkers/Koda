"""iCloud Contacts integration client."""

import subprocess
from datetime import datetime, date
from pathlib import Path
from typing import Any

from loguru import logger


class ICloudContactsClient:
    """
    Client for accessing iCloud Contacts.
    
    On macOS, this uses the native Contacts database via AppleScript/sqlite
    for local access, or pyicloud for remote access.
    """
    
    def __init__(
        self,
        apple_id: str | None = None,
        password: str | None = None,
        use_local: bool = True
    ):
        self.apple_id = apple_id
        self.password = password
        self.use_local = use_local
        self._api = None
    
    def _get_local_contacts(self) -> list[dict[str, Any]]:
        """
        Get contacts from macOS Contacts app via AppleScript.
        This is the preferred method as it doesn't require iCloud credentials.
        """
        script = '''
        tell application "Contacts"
            set contactList to {}
            repeat with p in people
                set contactInfo to {|name|:name of p, |firstName|:first name of p, |lastName|:last name of p}
                
                -- Get birthday
                try
                    set bday to birth date of p
                    if bday is not missing value then
                        set contactInfo to contactInfo & {|birthday|:(bday as string)}
                    end if
                end try
                
                -- Get emails
                set emailList to {}
                repeat with e in emails of p
                    set end of emailList to value of e
                end repeat
                set contactInfo to contactInfo & {|emails|:emailList}
                
                -- Get phones
                set phoneList to {}
                repeat with ph in phones of p
                    set end of phoneList to value of ph
                end repeat
                set contactInfo to contactInfo & {|phones|:phoneList}
                
                -- Get company
                try
                    set org to organization of p
                    if org is not missing value then
                        set contactInfo to contactInfo & {|company|:org}
                    end if
                end try
                
                set end of contactList to contactInfo
            end repeat
            return contactList
        end tell
        '''
        
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"AppleScript error: {result.stderr}")
                return []
            
            # Parse AppleScript output
            return self._parse_applescript_output(result.stdout)
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout reading contacts")
            return []
        except Exception as e:
            logger.error(f"Error reading local contacts: {e}")
            return []
    
    def _parse_applescript_output(self, output: str) -> list[dict[str, Any]]:
        """Parse AppleScript record output into Python dicts."""
        contacts = []
        
        # AppleScript returns records in a specific format
        # This is a simplified parser - for production, consider using JSON export
        lines = output.strip().split("}, {")
        
        for line in lines:
            contact = {}
            line = line.replace("{", "").replace("}", "")
            
            # Parse key-value pairs
            parts = line.split(", ")
            for part in parts:
                if ":" in part:
                    key, value = part.split(":", 1)
                    key = key.strip().replace("|", "")
                    value = value.strip().strip('"')
                    contact[key] = value
            
            if contact.get("name"):
                contacts.append(contact)
        
        return contacts
    
    def _get_icloud_contacts(self) -> list[dict[str, Any]]:
        """Get contacts from iCloud using pyicloud."""
        try:
            from pyicloud import PyiCloudService
        except ImportError:
            raise ImportError("pyicloud not installed. Run: pip install pyicloud")
        
        if not self.apple_id or not self.password:
            raise ValueError("Apple ID and password required for iCloud access")
        
        if not self._api:
            self._api = PyiCloudService(self.apple_id, self.password)
            
            if self._api.requires_2fa:
                logger.warning("iCloud requires 2FA. Please authenticate manually first.")
                raise RuntimeError("2FA required - run 'icloud' CLI to authenticate")
        
        contacts = []
        for contact in self._api.contacts.all():
            contacts.append({
                "name": f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
                "firstName": contact.get("firstName"),
                "lastName": contact.get("lastName"),
                "emails": [e.get("field") for e in contact.get("emailAddresses", [])],
                "phones": [p.get("field") for p in contact.get("phones", [])],
                "birthday": contact.get("birthday"),
                "company": contact.get("companyName"),
            })
        
        return contacts
    
    def get_contacts(self) -> list[dict[str, Any]]:
        """
        Get all contacts.
        
        Returns:
            List of contact dictionaries
        """
        if self.use_local:
            return self._get_local_contacts()
        else:
            return self._get_icloud_contacts()
    
    def get_contacts_with_birthdays(self) -> list[dict[str, Any]]:
        """
        Get contacts that have birthday information.
        
        Returns:
            List of contacts with birthdays
        """
        contacts = self.get_contacts()
        return [c for c in contacts if c.get("birthday")]
    
    def get_birthdays_on_date(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """
        Get contacts whose birthday is on a specific date.
        
        Args:
            target_date: Date to check (default: today)
        
        Returns:
            List of contacts with birthdays on that date
        """
        if target_date is None:
            target_date = date.today()
        
        contacts = self.get_contacts_with_birthdays()
        matches = []
        
        for contact in contacts:
            birthday_str = contact.get("birthday", "")
            if not birthday_str:
                continue
            
            try:
                # Try to parse various date formats
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y"]:
                    try:
                        bday = datetime.strptime(birthday_str, fmt).date()
                        if bday.month == target_date.month and bday.day == target_date.day:
                            contact["age"] = target_date.year - bday.year
                            matches.append(contact)
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.debug(f"Could not parse birthday '{birthday_str}': {e}")
        
        return matches
    
    def get_upcoming_birthdays(self, days: int = 7) -> list[dict[str, Any]]:
        """
        Get contacts with birthdays in the next N days.
        
        Args:
            days: Number of days to look ahead
        
        Returns:
            List of contacts with upcoming birthdays
        """
        from datetime import timedelta
        
        today = date.today()
        upcoming = []
        
        for i in range(days + 1):
            check_date = today + timedelta(days=i)
            birthdays = self.get_birthdays_on_date(check_date)
            for b in birthdays:
                b["days_until"] = i
                upcoming.append(b)
        
        return upcoming
    
    def search_contacts(self, query: str) -> list[dict[str, Any]]:
        """
        Search contacts by name, email, or phone.
        
        Args:
            query: Search query
        
        Returns:
            Matching contacts
        """
        contacts = self.get_contacts()
        query = query.lower()
        
        matches = []
        for contact in contacts:
            searchable = " ".join([
                contact.get("name", ""),
                contact.get("company", ""),
                " ".join(contact.get("emails", [])),
                " ".join(contact.get("phones", [])),
            ]).lower()
            
            if query in searchable:
                matches.append(contact)
        
        return matches
    
    def get_contact_by_phone(self, phone: str) -> dict[str, Any] | None:
        """
        Find a contact by phone number.
        
        Args:
            phone: Phone number to search for
        
        Returns:
            Contact dict or None
        """
        # Normalize phone number (remove spaces, dashes, etc.)
        normalized = "".join(c for c in phone if c.isdigit() or c == "+")
        
        contacts = self.get_contacts()
        for contact in contacts:
            for p in contact.get("phones", []):
                p_normalized = "".join(c for c in p if c.isdigit() or c == "+")
                if normalized in p_normalized or p_normalized in normalized:
                    return contact
        
        return None
