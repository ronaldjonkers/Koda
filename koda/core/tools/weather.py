"""Weather tool for getting weather forecasts."""
from __future__ import annotations

import json
from typing import Any

from koda.core.tools.base import Tool


class WeatherTool(Tool):
    """Get weather forecasts for any location."""
    
    name = "weather"
    description = """Get current weather and forecasts for any location.

Actions:
- current: Get current weather conditions
- forecast: Get weather forecast for coming days
- hourly: Get hourly forecast for today

Examples:
- Current weather: {"action": "current", "location": "Amsterdam"}
- 5-day forecast: {"action": "forecast", "location": "New York", "days": 5}
- Hourly today: {"action": "hourly", "location": "London"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["current", "forecast", "hourly"],
                "description": "Type of weather info to get"
            },
            "location": {
                "type": "string",
                "description": "City name or location (e.g., 'Amsterdam', 'New York, US')"
            },
            "days": {
                "type": "integer",
                "description": "Number of forecast days (1-7)",
                "minimum": 1,
                "maximum": 7
            }
        },
        "required": ["location"]
    }
    
    async def execute(self, location: str, action: str = "current", days: int = 3, **kwargs: Any) -> str:
        from loguru import logger
        
        logger.info(f"🌤️ weather called: {action} for {location}")
        
        try:
            import python_weather
        except ImportError:
            return json.dumps({"error": "python-weather not installed. Run: pip install python-weather"})
        
        try:
            import asyncio
            
            async with python_weather.Client(unit=python_weather.METRIC) as client:
                weather = await client.get(location)
                
                if action == "current":
                    return self._format_current(weather, location)
                elif action == "forecast":
                    return self._format_forecast(weather, location, days)
                elif action == "hourly":
                    return self._format_hourly(weather, location)
                else:
                    return self._format_current(weather, location)
                    
        except Exception as e:
            logger.error(f"Weather error: {e}")
            return json.dumps({"error": str(e), "location": location})
    
    def _format_current(self, weather, location: str) -> str:
        """Format current weather conditions."""
        return json.dumps({
            "location": location,
            "temperature": f"{weather.temperature}°C",
            "feels_like": f"{weather.feels_like}°C" if hasattr(weather, 'feels_like') else None,
            "description": str(weather.description) if hasattr(weather, 'description') else None,
            "humidity": f"{weather.humidity}%" if hasattr(weather, 'humidity') else None,
            "wind_speed": f"{weather.wind_speed} km/h" if hasattr(weather, 'wind_speed') else None,
            "type": "current"
        }, ensure_ascii=False)
    
    def _format_forecast(self, weather, location: str, days: int) -> str:
        """Format multi-day forecast."""
        forecasts = []
        for i, daily in enumerate(weather.daily_forecasts):
            if i >= days:
                break
            forecasts.append({
                "date": str(daily.date),
                "high": f"{daily.highest_temperature}°C",
                "low": f"{daily.lowest_temperature}°C",
                "description": str(daily.description) if hasattr(daily, 'description') else None,
            })
        
        return json.dumps({
            "location": location,
            "forecasts": forecasts,
            "type": "forecast"
        }, ensure_ascii=False)
    
    def _format_hourly(self, weather, location: str) -> str:
        """Format hourly forecast for today."""
        hourly = []
        today = list(weather.daily_forecasts)[0] if weather.daily_forecasts else None
        
        if today and hasattr(today, 'hourly_forecasts'):
            for hour in today.hourly_forecasts:
                hourly.append({
                    "time": str(hour.time),
                    "temperature": f"{hour.temperature}°C",
                    "description": str(hour.description) if hasattr(hour, 'description') else None,
                })
        
        return json.dumps({
            "location": location,
            "hourly": hourly[:12],  # Limit to 12 hours
            "type": "hourly"
        }, ensure_ascii=False)
