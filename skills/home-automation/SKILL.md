---
name: home-automation
description: Control smart home devices, lights, temperature, scenes
triggers: licht, light, lamp, hue, dim, brightness, scene, home, thuis, verlichting
priority: 9
---

# Home Automation Skill

You control smart home devices. Follow these guidelines.

## Available Devices

### Philips Hue (tool: hue)
- Control individual lights or groups
- Set brightness, color, scenes
- Turn on/off

## Common Commands

### Lights On/Off
```json
{"action": "on", "light": "Living Room"}
{"action": "off", "light": "all"}
{"action": "off", "group": "Bedroom"}
```

### Brightness
```json
{"action": "brightness", "light": "Desk Lamp", "value": 50}
```
Value: 0-100 (percentage)

### Colors
```json
{"action": "color", "light": "LED Strip", "color": "blue"}
{"action": "color", "light": "Accent", "color": "#FF5500"}
```
Colors: red, blue, green, yellow, orange, purple, pink, white, warm, cool

### Scenes
```json
{"action": "scene", "scene": "Relax", "group": "Living Room"}
```

### Status
```json
{"action": "lights"}  // List all lights
{"action": "groups"}  // List rooms/groups
{"action": "status", "light": "Kitchen"}  // Get specific light status
```

## Natural Language Mapping

| User says | Action |
|-----------|--------|
| "Doe het licht aan" | `{"action": "on", "light": "all"}` |
| "Dim de woonkamer" | `{"action": "brightness", "group": "Woonkamer", "value": 30}` |
| "Maak het blauw" | `{"action": "color", "light": "...", "color": "blue"}` |
| "Zet relaxstand aan" | `{"action": "scene", "scene": "Relax"}` |
| "Lichten uit" | `{"action": "off", "light": "all"}` |

## Best Practices

1. **Confirm Actions**: Tell user what you did
   - "Ik heb de woonkamerlampen gedimd naar 30%"
   
2. **Handle Errors**: If device not found, list available devices

3. **Group vs Individual**: 
   - Use groups for rooms ("Woonkamer", "Slaapkamer")
   - Use individual lights for specific lamps

4. **Smart Defaults**:
   - "Licht aan" without specifying → ask which room or use "all"
   - Evening dimming → suggest 30-50%
   - Night mode → very dim (10%) or off

## Setup Help

If Hue not configured:
1. Run `{"action": "discover"}` to find bridge
2. Press button on Hue bridge
3. Save bridge_ip and username to config
