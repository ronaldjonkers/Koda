"""iCloud Contacts integration client."""

from __future__ import annotations

import glob
import os
import sqlite3
import subprocess
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

from loguru import logger


class ICloudContactsClient:
    """
    Client for accessing iCloud Contacts.
    
    On macOS, this reads the native Contacts SQLite database directly
    for fast local access, or pyicloud for remote access.
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
        self._db_paths = self._find_contacts_databases()
    
    def _find_contacts_databases(self) -> list[str]:
        """Find all macOS Contacts database files."""
        pattern = os.path.expanduser(
            "~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb"
        )
        return glob.glob(pattern)
    
    def _get_local_contacts(self) -> list[dict[str, Any]]:
        """
        Get contacts from macOS Contacts SQLite database.
        This is much faster than AppleScript for large contact lists.
        """
        contacts = []
        seen_names = set()
        
        for db_path in self._db_paths:
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                # Query contacts with their details
                cur.execute('''
                    SELECT 
                        ZFIRSTNAME as first_name,
                        ZLASTNAME as last_name,
                        ZORGANIZATION as company,
                        ZBIRTHDAYYEAR as birth_year,
                        ZBIRTHDAYYEARLESS as birth_yearless
                    FROM ZABCDRECORD 
                    WHERE ZFIRSTNAME IS NOT NULL OR ZLASTNAME IS NOT NULL
                ''')
                
                for row in cur.fetchall():
                    first_name = row['first_name'] or ''
                    last_name = row['last_name'] or ''
                    name = f"{first_name} {last_name}".strip()
                    
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    
                    # Parse birthday from CoreData timestamp
                    birthday = None
                    birth_yearless = row['birth_yearless']
                    birth_year = row['birth_year']
                    
                    if birth_yearless is not None:
                        try:
                            # CoreData stores as seconds since 2001-01-01
                            ref_date = datetime(2001, 1, 1)
                            bday_date = datetime.fromtimestamp(ref_date.timestamp() + birth_yearless)
                            if birth_year and birth_year > 1900:
                                birthday = f"{birth_year}-{bday_date.month:02d}-{bday_date.day:02d}"
                            else:
                                birthday = f"{bday_date.month:02d}-{bday_date.day:02d}"
                        except Exception:
                            pass
                    
                    contacts.append({
                        "name": name,
                        "firstName": first_name,
                        "lastName": last_name,
                        "company": row['company'],
                        "birthday": birthday,
                        "emails": [],
                        "phones": [],
                    })
                
                conn.close()
                
            except Exception as e:
                logger.debug(f"Error reading contacts from {db_path}: {e}")
                continue
        
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
