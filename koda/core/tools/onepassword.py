"""1Password integration via CLI."""
from __future__ import annotations

import json
import subprocess
from typing import Any, Optional

from koda.core.tools.base import Tool


class OnePasswordTool(Tool):
    """Access 1Password secrets via CLI (requires 1Password CLI: op)."""
    
    name = "onepassword"
    description = """Securely access 1Password items (requires 1Password CLI installed).

Actions:
- search: Search for items
- get: Get item details (passwords, notes, etc.)
- list_vaults: List available vaults
- list_items: List items in a vault

SECURITY: Never expose passwords in responses unless explicitly asked.
Instead, describe what was found without revealing sensitive values.

Examples:
- Search: {"action": "search", "query": "gmail"}
- Get login: {"action": "get", "item": "Gmail", "field": "password"}
- List vaults: {"action": "list_vaults"}

Note: User must be signed into 1Password CLI (`op signin`).
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "get", "list_vaults", "list_items"],
                "description": "Action to perform"
            },
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "item": {
                "type": "string",
                "description": "Item name or ID"
            },
            "vault": {
                "type": "string",
                "description": "Vault name (optional)"
            },
            "field": {
                "type": "string",
                "description": "Specific field to retrieve (e.g., 'password', 'username', 'otp')"
            }
        },
        "required": ["action"]
    }
    
    def _run_op(self, args: list[str]) -> dict:
        """Run 1Password CLI command."""
        cmd = ["op"] + args + ["--format=json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error = result.stderr.strip()
            if "not signed in" in error.lower():
                raise RuntimeError("Not signed into 1Password. Run: eval $(op signin)")
            raise RuntimeError(error)
        
        return json.loads(result.stdout) if result.stdout.strip() else {}
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        from loguru import logger
        
        logger.info(f"🔐 onepassword: {action}")
        
        # Check if op CLI is available
        try:
            subprocess.run(["op", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return json.dumps({
                "error": "1Password CLI not installed",
                "instructions": "Install from: https://1password.com/downloads/command-line/"
            })
        
        try:
            if action == "search":
                return self._search(kwargs.get("query", ""), kwargs.get("vault"))
            elif action == "get":
                return self._get_item(
                    kwargs.get("item", ""),
                    kwargs.get("field"),
                    kwargs.get("vault")
                )
            elif action == "list_vaults":
                return self._list_vaults()
            elif action == "list_items":
                return self._list_items(kwargs.get("vault"))
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            logger.error(f"1Password error: {e}")
            return json.dumps({"error": str(e)})
    
    def _search(self, query: str, vault: Optional[str] = None) -> str:
        """Search for items."""
        if not query:
            return json.dumps({"error": "Query required"})
        
        args = ["item", "list"]
        if vault:
            args.extend(["--vault", vault])
        
        items = self._run_op(args)
        
        # Filter by query
        results = []
        query_lower = query.lower()
        for item in items:
            title = item.get("title", "").lower()
            if query_lower in title:
                results.append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "category": item.get("category"),
                    "vault": item.get("vault", {}).get("name")
                })
        
        return json.dumps({
            "query": query,
            "results": results[:20],  # Limit results
            "total": len(results)
        })
    
    def _get_item(self, item: str, field: Optional[str] = None, vault: Optional[str] = None) -> str:
        """Get item details or specific field."""
        if not item:
            return json.dumps({"error": "Item name or ID required"})
        
        args = ["item", "get", item]
        if vault:
            args.extend(["--vault", vault])
        
        if field:
            # Get specific field value
            args.extend(["--fields", field])
            try:
                result = self._run_op(args)
                # For OTP, result is different
                if field.lower() == "otp":
                    return json.dumps({
                        "item": item,
                        "field": field,
                        "value": result.get("totp") if isinstance(result, dict) else result
                    })
                return json.dumps({
                    "item": item,
                    "field": field,
                    "value": result.get("value") if isinstance(result, dict) else result
                })
            except:
                # Try direct field access
                cmd = ["op", "read", f"op://{vault or 'Private'}/{item}/{field}"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return json.dumps({
                        "item": item,
                        "field": field,
                        "value": result.stdout.strip()
                    })
                raise
        
        # Get full item (hide sensitive fields)
        data = self._run_op(args)
        
        # Sanitize output - don't expose passwords directly
        safe_data = {
            "id": data.get("id"),
            "title": data.get("title"),
            "category": data.get("category"),
            "vault": data.get("vault", {}).get("name"),
            "fields": []
        }
        
        for field_data in data.get("fields", []):
            field_info = {
                "label": field_data.get("label"),
                "type": field_data.get("type"),
            }
            # Only show values for non-sensitive fields
            if field_data.get("type") not in ["CONCEALED", "OTP"]:
                field_info["value"] = field_data.get("value")
            else:
                field_info["value"] = "[HIDDEN - use field parameter to retrieve]"
            safe_data["fields"].append(field_info)
        
        return json.dumps(safe_data)
    
    def _list_vaults(self) -> str:
        """List all vaults."""
        vaults = self._run_op(["vault", "list"])
        
        result = []
        for vault in vaults:
            result.append({
                "id": vault.get("id"),
                "name": vault.get("name")
            })
        
        return json.dumps({"vaults": result})
    
    def _list_items(self, vault: Optional[str] = None) -> str:
        """List items in a vault."""
        args = ["item", "list"]
        if vault:
            args.extend(["--vault", vault])
        
        items = self._run_op(args)
        
        result = []
        for item in items[:50]:  # Limit to 50
            result.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "category": item.get("category")
            })
        
        return json.dumps({
            "vault": vault or "all",
            "items": result,
            "total": len(items)
        })
