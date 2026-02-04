"""Smart Home integrations: Philips Hue lights."""
from __future__ import annotations

import json
from typing import Any, Optional

from koda.core.tools.base import Tool


class PhilipsHueTool(Tool):
    """Control Philips Hue lights."""
    
    name = "hue"
    description = """Control Philips Hue smart lights.

Actions:
- discover: Find Hue bridge on network
- lights: List all lights
- on: Turn light(s) on
- off: Turn light(s) off
- brightness: Set brightness (0-100%)
- color: Set color (by name or hex)
- scene: Activate a scene
- groups: List rooms/groups
- status: Get light status

Examples:
- List lights: {"action": "lights"}
- Turn on: {"action": "on", "light": "Living Room"}
- Set brightness: {"action": "brightness", "light": "Bedroom", "value": 50}
- Set color: {"action": "color", "light": "Desk Lamp", "color": "blue"}
- Turn off all: {"action": "off", "light": "all"}

Note: Requires bridge IP and username in config. First time: use 'discover' and press bridge button.
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["discover", "lights", "on", "off", "brightness", "color", "scene", "groups", "status"],
                "description": "Action to perform"
            },
            "light": {
                "type": "string",
                "description": "Light name, ID, or 'all'"
            },
            "group": {
                "type": "string",
                "description": "Room/group name"
            },
            "value": {
                "type": "integer",
                "description": "Brightness value (0-100)",
                "minimum": 0,
                "maximum": 100
            },
            "color": {
                "type": "string",
                "description": "Color name (red, blue, etc.) or hex (#FF0000)"
            },
            "scene": {
                "type": "string",
                "description": "Scene name to activate"
            }
        },
        "required": ["action"]
    }
    
    # Common color name to xy coordinates mapping
    COLORS = {
        "red": [0.675, 0.322],
        "green": [0.409, 0.518],
        "blue": [0.167, 0.04],
        "yellow": [0.465, 0.465],
        "orange": [0.6, 0.38],
        "purple": [0.3, 0.15],
        "pink": [0.4, 0.2],
        "white": [0.323, 0.329],
        "warm": [0.5, 0.4],
        "cool": [0.28, 0.27],
    }
    
    def __init__(self, bridge_ip: Optional[str] = None, username: Optional[str] = None):
        self._bridge_ip = bridge_ip
        self._username = username
    
    def _get_config(self) -> tuple[str, str]:
        """Get Hue config from file."""
        if self._bridge_ip and self._username:
            return self._bridge_ip, self._username
        
        try:
            from koda.config.loader import load_config
            config = load_config()
            hue = config.integrations.hue
            return hue.bridge_ip, hue.username
        except:
            return "", ""
    
    async def _api_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> Any:
        """Make API request to Hue bridge."""
        import httpx
        
        bridge_ip, username = self._get_config()
        if not bridge_ip or not username:
            raise ValueError("Hue bridge not configured. Use 'discover' action first.")
        
        url = f"http://{bridge_ip}/api/{username}/{endpoint}"
        
        async with httpx.AsyncClient() as client:
            if method == "GET":
                r = await client.get(url, timeout=10)
            elif method == "PUT":
                r = await client.put(url, json=data, timeout=10)
            elif method == "POST":
                r = await client.post(url, json=data, timeout=10)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            return r.json()
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        from loguru import logger
        
        logger.info(f"💡 hue: {action}")
        
        try:
            if action == "discover":
                return await self._discover()
            elif action == "lights":
                return await self._list_lights()
            elif action == "groups":
                return await self._list_groups()
            elif action == "on":
                return await self._set_state(kwargs.get("light"), kwargs.get("group"), on=True)
            elif action == "off":
                return await self._set_state(kwargs.get("light"), kwargs.get("group"), on=False)
            elif action == "brightness":
                return await self._set_brightness(kwargs.get("light"), kwargs.get("group"), kwargs.get("value", 100))
            elif action == "color":
                return await self._set_color(kwargs.get("light"), kwargs.get("group"), kwargs.get("color", "white"))
            elif action == "scene":
                return await self._activate_scene(kwargs.get("scene", ""), kwargs.get("group"))
            elif action == "status":
                return await self._get_status(kwargs.get("light"))
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            logger.error(f"Hue error: {e}")
            return json.dumps({"error": str(e)})
    
    async def _discover(self) -> str:
        """Discover Hue bridge on network."""
        import httpx
        
        # Try mDNS/SSDP discovery
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get("https://discovery.meethue.com/", timeout=10)
                bridges = r.json()
                
                if bridges:
                    bridge = bridges[0]
                    return json.dumps({
                        "status": "found",
                        "bridge_ip": bridge.get("internalipaddress"),
                        "id": bridge.get("id"),
                        "instructions": "Press the button on your Hue bridge, then run 'register' action within 30 seconds."
                    })
        except:
            pass
        
        return json.dumps({
            "status": "not_found",
            "instructions": "Could not find Hue bridge. Make sure it's on the same network."
        })
    
    async def _list_lights(self) -> str:
        """List all lights."""
        lights = await self._api_request("GET", "lights")
        
        result = []
        for id, light in lights.items():
            result.append({
                "id": id,
                "name": light.get("name"),
                "on": light.get("state", {}).get("on"),
                "brightness": round(light.get("state", {}).get("bri", 0) / 254 * 100),
                "reachable": light.get("state", {}).get("reachable")
            })
        
        return json.dumps({"lights": result})
    
    async def _list_groups(self) -> str:
        """List all groups/rooms."""
        groups = await self._api_request("GET", "groups")
        
        result = []
        for id, group in groups.items():
            result.append({
                "id": id,
                "name": group.get("name"),
                "type": group.get("type"),
                "lights": group.get("lights", []),
                "on": group.get("state", {}).get("any_on")
            })
        
        return json.dumps({"groups": result})
    
    async def _find_light_id(self, name: str) -> Optional[str]:
        """Find light ID by name."""
        if name.isdigit():
            return name
        
        lights = await self._api_request("GET", "lights")
        for id, light in lights.items():
            if light.get("name", "").lower() == name.lower():
                return id
        return None
    
    async def _find_group_id(self, name: str) -> Optional[str]:
        """Find group ID by name."""
        if name and name.isdigit():
            return name
        
        groups = await self._api_request("GET", "groups")
        for id, group in groups.items():
            if group.get("name", "").lower() == (name or "").lower():
                return id
        return None
    
    async def _set_state(self, light: Optional[str], group: Optional[str], on: bool) -> str:
        """Turn light(s) on/off."""
        state = {"on": on}
        
        if light == "all" or (not light and not group):
            # All lights via group 0
            await self._api_request("PUT", "groups/0/action", state)
            return json.dumps({"status": "ok", "all_lights": "on" if on else "off"})
        
        if group:
            group_id = await self._find_group_id(group)
            if group_id:
                await self._api_request("PUT", f"groups/{group_id}/action", state)
                return json.dumps({"status": "ok", "group": group, "on": on})
        
        if light:
            light_id = await self._find_light_id(light)
            if light_id:
                await self._api_request("PUT", f"lights/{light_id}/state", state)
                return json.dumps({"status": "ok", "light": light, "on": on})
        
        return json.dumps({"error": "Light or group not found"})
    
    async def _set_brightness(self, light: Optional[str], group: Optional[str], value: int) -> str:
        """Set brightness (0-100)."""
        bri = max(1, min(254, int(value * 254 / 100)))
        state = {"on": True, "bri": bri}
        
        if group:
            group_id = await self._find_group_id(group)
            if group_id:
                await self._api_request("PUT", f"groups/{group_id}/action", state)
                return json.dumps({"status": "ok", "group": group, "brightness": value})
        
        if light:
            light_id = await self._find_light_id(light)
            if light_id:
                await self._api_request("PUT", f"lights/{light_id}/state", state)
                return json.dumps({"status": "ok", "light": light, "brightness": value})
        
        return json.dumps({"error": "Light or group not found"})
    
    async def _set_color(self, light: Optional[str], group: Optional[str], color: str) -> str:
        """Set color by name or hex."""
        # Get xy coordinates
        if color.lower() in self.COLORS:
            xy = self.COLORS[color.lower()]
        elif color.startswith("#"):
            xy = self._hex_to_xy(color)
        else:
            return json.dumps({"error": f"Unknown color: {color}. Use: {list(self.COLORS.keys())} or hex"})
        
        state = {"on": True, "xy": xy}
        
        if group:
            group_id = await self._find_group_id(group)
            if group_id:
                await self._api_request("PUT", f"groups/{group_id}/action", state)
                return json.dumps({"status": "ok", "group": group, "color": color})
        
        if light:
            light_id = await self._find_light_id(light)
            if light_id:
                await self._api_request("PUT", f"lights/{light_id}/state", state)
                return json.dumps({"status": "ok", "light": light, "color": color})
        
        return json.dumps({"error": "Light or group not found"})
    
    def _hex_to_xy(self, hex_color: str) -> list:
        """Convert hex color to xy coordinates."""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16) / 255
        g = int(hex_color[2:4], 16) / 255
        b = int(hex_color[4:6], 16) / 255
        
        # Apply gamma correction
        r = pow((r + 0.055) / 1.055, 2.4) if r > 0.04045 else r / 12.92
        g = pow((g + 0.055) / 1.055, 2.4) if g > 0.04045 else g / 12.92
        b = pow((b + 0.055) / 1.055, 2.4) if b > 0.04045 else b / 12.92
        
        # Convert to XYZ
        X = r * 0.649926 + g * 0.103455 + b * 0.197109
        Y = r * 0.234327 + g * 0.743075 + b * 0.022598
        Z = r * 0.0 + g * 0.053077 + b * 1.035763
        
        # Convert to xy
        total = X + Y + Z
        if total == 0:
            return [0.323, 0.329]  # Default white
        
        return [round(X / total, 4), round(Y / total, 4)]
    
    async def _activate_scene(self, scene: str, group: Optional[str]) -> str:
        """Activate a scene."""
        scenes = await self._api_request("GET", "scenes")
        
        for scene_id, s in scenes.items():
            if s.get("name", "").lower() == scene.lower():
                # Find group for this scene
                target_group = group or s.get("group", "0")
                group_id = await self._find_group_id(target_group) if not target_group.isdigit() else target_group
                
                await self._api_request("PUT", f"groups/{group_id}/action", {"scene": scene_id})
                return json.dumps({"status": "ok", "scene": scene})
        
        return json.dumps({"error": f"Scene '{scene}' not found"})
    
    async def _get_status(self, light: Optional[str]) -> str:
        """Get light status."""
        if light:
            light_id = await self._find_light_id(light)
            if light_id:
                data = await self._api_request("GET", f"lights/{light_id}")
                state = data.get("state", {})
                return json.dumps({
                    "name": data.get("name"),
                    "on": state.get("on"),
                    "brightness": round(state.get("bri", 0) / 254 * 100),
                    "reachable": state.get("reachable")
                })
        
        return await self._list_lights()
