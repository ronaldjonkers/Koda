"""Image generation tool with multiple provider support.

Supports:
- Pollinations.ai (free, no API key required)
- OpenRouter (uses existing API key, models like FLUX)
- Stability AI (optional, requires API key)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from loguru import logger

from koda.core.tools.base import BaseTool


class ImageProvider(str, Enum):
    """Available image generation providers."""
    POLLINATIONS = "pollinations"  # Free, no API key needed
    OPENROUTER = "openrouter"      # Uses existing OpenRouter key
    STABILITY = "stability"        # Requires Stability AI key
    TOGETHER = "together"          # Together AI (optional)


@dataclass
class GeneratedImage:
    """Represents a generated image."""
    url: str | None
    base64_data: str | None
    local_path: Path | None
    provider: str
    model: str
    prompt: str
    width: int
    height: int
    seed: int | None
    cost: float | None  # Cost in USD if applicable


class ImageGenerationTool(BaseTool):
    """
    Generate images using AI models from various providers.
    
    Providers:
    - pollinations: FREE, no API key needed. Uses Stable Diffusion / FLUX
    - openrouter: Uses your existing OpenRouter API key. Models like FLUX, DALL-E
    - stability: Requires Stability AI API key. High quality images
    
    The tool automatically selects the best available provider based on:
    1. Explicit provider choice
    2. Configured API keys
    3. Cost considerations
    4. Quality requirements
    
    Generated images are saved to ~/.koda/workspace/generated_images/
    
    Actions:
    - generate: Create an image from a text prompt
    - providers: List available providers and their status
    - models: List available models for a provider
    
    Parameters for 'generate':
    - prompt: Text description of the image to generate
    - provider: Which provider to use (auto-selected if not specified)
    - model: Specific model to use (provider-dependent)
    - width/height: Image dimensions (default: 1024x1024)
    - seed: Random seed for reproducibility (optional)
    - aspect_ratio: Alternative to width/height (1:1, 16:9, 4:3, etc.)
    
    Parameters for 'providers':
    - show_all: Include providers without API keys
    
    Examples:
    - "Generate an image of a cat wearing a space suit"
    - "Create a futuristic cityscape at sunset, use 16:9 aspect ratio"
    - "Draw a logo for a coffee shop called 'Bean There'"
    """
    
    name = "image_generation"
    description = """Generate images using AI models. Supports multiple providers including free options.

Use this to:
- Create illustrations, artwork, and concept art
- Generate logos and branding materials
- Create marketing images and social media content
- Visualize ideas and concepts

Providers (automatically selected):
- pollinations: FREE, no setup needed (Stable Diffusion, FLUX)
- openrouter: Uses your existing OpenRouter key (FLUX, DALL-E, etc.)
- stability: High quality, requires Stability AI API key

Actions:
- generate: Create an image from text description
- providers: Check which providers are available
- models: List models for a specific provider

Examples:
- "Generate a logo for my bakery"
- "Create an image of a futuristic city at night"
- "Draw a cute robot reading a book"
- "Make a banner for my website, 16:9 aspect ratio"
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "providers", "models"],
                "description": "Action to perform"
            },
            "prompt": {
                "type": "string",
                "description": "Text description of the image to generate (for 'generate' action)"
            },
            "provider": {
                "type": "string",
                "enum": ["pollinations", "openrouter", "stability", "auto"],
                "description": "Provider to use (default: auto - picks best available)"
            },
            "model": {
                "type": "string",
                "description": "Specific model to use (provider-dependent)"
            },
            "width": {
                "type": "integer",
                "description": "Image width in pixels (default: 1024)",
                "default": 1024
            },
            "height": {
                "type": "integer",
                "description": "Image height in pixels (default: 1024)",
                "default": 1024
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Alternative to width/height: 1:1, 16:9, 4:3, 3:2, 9:16",
                "enum": ["1:1", "16:9", "4:3", "3:2", "9:16", "21:9"]
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducible results (optional)"
            },
            "style": {
                "type": "string",
                "description": "Image style: photo, digital-art, anime, cinematic, etc."
            },
            "negative_prompt": {
                "type": "string",
                "description": "Things to avoid in the image (optional)"
            }
        },
        "required": ["action"]
    }
    
    # Aspect ratio to dimensions mapping
    ASPECT_RATIOS = {
        "1:1": (1024, 1024),
        "16:9": (1344, 768),
        "4:3": (1184, 864),
        "3:2": (1248, 832),
        "9:16": (768, 1344),
        "21:9": (1536, 672),
    }
    
    def __init__(
        self,
        workspace: Path,
        openrouter_api_key: str | None = None,
        stability_api_key: str | None = None,
        together_api_key: str | None = None,
        on_image_generated: callable | None = None
    ):
        self.workspace = workspace
        self.output_dir = workspace / "generated_images"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.api_keys = {
            ImageProvider.OPENROUTER: openrouter_api_key,
            ImageProvider.STABILITY: stability_api_key,
            ImageProvider.TOGETHER: together_api_key,
            ImageProvider.POLLINATIONS: "free",  # No key needed
        }
        
        # Callback when image is generated
        self.on_image_generated = on_image_generated
        
        # Track usage
        self.usage_file = self.output_dir / "usage.json"
        self.usage = self._load_usage()
    
    def _load_usage(self) -> dict:
        """Load usage statistics."""
        if self.usage_file.exists():
            try:
                return json.loads(self.usage_file.read_text())
            except:
                pass
        return {
            "total_generations": 0,
            "total_cost_usd": 0.0,
            "by_provider": {},
            "history": []
        }
    
    def _save_usage(self):
        """Save usage statistics."""
        self.usage_file.write_text(json.dumps(self.usage, indent=2, default=str))
    
    def _get_provider_status(self) -> dict[str, dict]:
        """Get status of all providers."""
        status = {}
        
        for provider in ImageProvider:
            key = self.api_keys.get(provider)
            has_key = key is not None and key != ""
            
            status[provider.value] = {
                "available": provider == ImageProvider.POLLINATIONS or has_key,
                "requires_key": provider != ImageProvider.POLLINATIONS,
                "has_key": has_key,
                "cost": "free" if provider == ImageProvider.POLLINATIONS else "paid",
                "quality": "good" if provider == ImageProvider.POLLINATIONS else "excellent",
            }
        
        return status
    
    def _select_provider(self, preferred: str | None = None) -> ImageProvider:
        """Select the best available provider."""
        if preferred and preferred != "auto":
            provider = ImageProvider(preferred)
            if self.api_keys.get(provider):
                return provider
            raise ValueError(f"Provider '{preferred}' not available (no API key configured)")
        
        # Priority: Pollinations (free) > OpenRouter (existing key) > others
        if self.api_keys.get(ImageProvider.POLLINATIONS):
            return ImageProvider.POLLINATIONS
        
        if self.api_keys.get(ImageProvider.OPENROUTER):
            return ImageProvider.OPENROUTER
        
        if self.api_keys.get(ImageProvider.STABILITY):
            return ImageProvider.STABILITY
        
        if self.api_keys.get(ImageProvider.TOGETHER):
            return ImageProvider.TOGETHER
        
        raise ValueError("No image generation providers available. Configure an API key or use Pollinations (free).")
    
    async def execute(self, **kwargs) -> str:
        """Execute image generation action."""
        action = kwargs.get("action", "generate")
        
        try:
            if action == "generate":
                return await self._generate(**kwargs)
            elif action == "providers":
                return self._list_providers()
            elif action == "models":
                return self._list_models(kwargs.get("provider"))
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            return f"❌ Error: {str(e)}"
    
    async def _generate(
        self,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: str | None = None,
        seed: int | None = None,
        style: str | None = None,
        negative_prompt: str | None = None,
        **kwargs
    ) -> str:
        """Generate an image."""
        if not prompt:
            return "❌ Error: prompt is required to generate an image."
        
        # Handle aspect ratio
        if aspect_ratio and aspect_ratio in self.ASPECT_RATIOS:
            width, height = self.ASPECT_RATIOS[aspect_ratio]
        
        # Select provider
        try:
            selected_provider = self._select_provider(provider)
        except ValueError as e:
            return f"❌ {e}\n\nTo use image generation:\n1. Pollinations (free) - works immediately\n2. Configure API key: koda config image"
        
        # Generate based on provider
        logger.info(f"Generating image with {selected_provider.value}: {prompt[:50]}...")
        
        if selected_provider == ImageProvider.POLLINATIONS:
            result = await self._generate_pollinations(
                prompt, width, height, seed, style, negative_prompt
            )
        elif selected_provider == ImageProvider.OPENROUTER:
            result = await self._generate_openrouter(
                prompt, model, width, height, seed
            )
        elif selected_provider == ImageProvider.STABILITY:
            result = await self._generate_stability(
                prompt, model, width, height, seed, negative_prompt
            )
        else:
            return f"❌ Provider '{selected_provider.value}' not implemented yet."
        
        # Save and track
        if result.local_path:
            self._track_usage(result)
            
            # Trigger callback if set (for sending via WhatsApp)
            if self.on_image_generated:
                try:
                    await self.on_image_generated(result)
                except Exception as e:
                    logger.error(f"Error in image generated callback: {e}")
            
            return self._format_result(result)
        else:
            return f"❌ Failed to generate image. Please try again or use a different provider."
    
    async def _generate_pollinations(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
        style: str | None = None,
        negative_prompt: str | None = None
    ) -> GeneratedImage:
        """Generate image using Pollinations.ai (FREE)."""
        
        # Build URL with parameters
        # Pollinations format: https://image.pollinations.ai/prompt/{encoded_prompt}?width=&height=&seed=&nologo=true
        encoded_prompt = quote(prompt)
        
        params = {
            "width": width,
            "height": height,
            "nologo": "true",
            "seed": seed if seed else int(datetime.now().timestamp()),
            "enhance": "true",
        }
        
        if negative_prompt:
            params["negative_prompt"] = quote(negative_prompt)
        
        if style:
            # Add style hint to prompt
            params["seed"] = seed if seed else int(datetime.now().timestamp())
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query_string}"
        
        logger.info(f"Calling Pollinations API: {url[:100]}...")
        
        # Download the image
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                
                # Save to file
                image_data = response.content
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
                filename = f"pollinations_{timestamp}_{prompt_hash}.png"
                local_path = self.output_dir / filename
                local_path.write_bytes(image_data)
                
                # Convert to base64 for display
                base64_data = base64.b64encode(image_data).decode()
                
                return GeneratedImage(
                    url=url,
                    base64_data=f"data:image/png;base64,{base64_data}",
                    local_path=local_path,
                    provider="pollinations",
                    model="flux",  # Pollinations uses FLUX by default
                    prompt=prompt,
                    width=width,
                    height=height,
                    seed=params.get("seed"),
                    cost=0.0  # Free!
                )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Pollinations API error: {e.response.status_code} - {e.response.text}")
                raise ValueError(f"Pollinations API error: {e.response.status_code}")
            except Exception as e:
                logger.error(f"Pollinations request failed: {e}")
                raise
    
    async def _generate_openrouter(
        self,
        prompt: str,
        model: str | None = None,
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None
    ) -> GeneratedImage:
        """Generate image using OpenRouter (uses existing API key)."""
        
        api_key = self.api_keys.get(ImageProvider.OPENROUTER)
        if not api_key:
            raise ValueError("OpenRouter API key not configured")
        
        # Default to FLUX if no model specified
        model = model or "black-forest-labs/flux.2-pro"
        
        # Map aspect ratio to OpenRouter format
        aspect_map = {
            (1024, 1024): "1:1",
            (1344, 768): "16:9",
            (1184, 864): "4:3",
            (1248, 832): "3:2",
            (768, 1344): "9:16",
        }
        aspect_ratio = aspect_map.get((width, height), "1:1")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://koda.ai",
            "X-Title": "Koda AI Assistant"
        }
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate an image: {prompt}"
                }
            ],
            "modalities": ["image"],
            "image_config": {
                "aspect_ratio": aspect_ratio
            }
        }
        
        logger.info(f"Calling OpenRouter API with model: {model}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract image from response
                message = data.get("choices", [{}])[0].get("message", {})
                images = message.get("images", [])
                
                if not images:
                    raise ValueError("No image returned from OpenRouter")
                
                # Get first image (base64 data URL)
                image_data_url = images[0]
                
                # Parse base64 data
                if image_data_url.startswith("data:image"):
                    base64_part = image_data_url.split(",")[1]
                    image_data = base64.b64decode(base64_part)
                else:
                    # It's a URL, download it
                    img_response = await client.get(image_data_url)
                    img_response.raise_for_status()
                    image_data = img_response.content
                    base64_part = base64.b64encode(image_data).decode()
                    image_data_url = f"data:image/png;base64,{base64_part}"
                
                # Save to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
                filename = f"openrouter_{timestamp}_{prompt_hash}.png"
                local_path = self.output_dir / filename
                local_path.write_bytes(image_data)
                
                # Estimate cost (varies by model)
                cost = 0.04  # Approximate for FLUX
                
                return GeneratedImage(
                    url=None,
                    base64_data=image_data_url,
                    local_path=local_path,
                    provider="openrouter",
                    model=model,
                    prompt=prompt,
                    width=width,
                    height=height,
                    seed=seed,
                    cost=cost
                )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"OpenRouter API error: {e.response.status_code}")
                raise ValueError(f"OpenRouter API error: {e.response.status_code}")
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                raise
    
    async def _generate_stability(
        self,
        prompt: str,
        model: str | None = None,
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
        negative_prompt: str | None = None
    ) -> GeneratedImage:
        """Generate image using Stability AI (requires API key)."""
        
        api_key = self.api_keys.get(ImageProvider.STABILITY)
        if not api_key:
            raise ValueError("Stability AI API key not configured")
        
        # Use Stability AI's API
        engine_id = model or "stable-diffusion-xl-1024-v1-0"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "cfg_scale": 7,
            "samples": 1,
            "steps": 30,
            "width": width,
            "height": height,
        }
        
        if seed:
            payload["seed"] = seed
        
        if negative_prompt:
            payload["text_prompts"].append({"text": negative_prompt, "weight": -1.0})
        
        logger.info(f"Calling Stability AI API with engine: {engine_id}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"https://api.stability.ai/v1/generation/{engine_id}/text-to-image",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract image
                artifacts = data.get("artifacts", [])
                if not artifacts:
                    raise ValueError("No image returned from Stability AI")
                
                image_data = base64.b64decode(artifacts[0]["base64"])
                base64_data = f"data:image/png;base64,{artifacts[0]['base64']}"
                
                # Save to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
                filename = f"stability_{timestamp}_{prompt_hash}.png"
                local_path = self.output_dir / filename
                local_path.write_bytes(image_data)
                
                # Estimate cost
                cost = 0.02  # Approximate cost per image
                
                return GeneratedImage(
                    url=None,
                    base64_data=base64_data,
                    local_path=local_path,
                    provider="stability",
                    model=engine_id,
                    prompt=prompt,
                    width=width,
                    height=height,
                    seed=artifacts[0].get("seed"),
                    cost=cost
                )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Stability AI API error: {e.response.status_code}")
                raise ValueError(f"Stability AI API error: {e.response.status_code}")
            except Exception as e:
                logger.error(f"Stability AI request failed: {e}")
                raise
    
    def _format_result(self, result: GeneratedImage) -> str:
        """Format the generation result for display."""
        cost_str = f" (${result.cost:.3f})" if result.cost and result.cost > 0 else " (free)"
        
        lines = [
            f"✅ **Image Generated**{cost_str}",
            "",
            f"🎨 **Prompt:** {result.prompt[:100]}{'...' if len(result.prompt) > 100 else ''}",
            f"📐 **Size:** {result.width}x{result.height}",
            f"🔧 **Provider:** {result.provider}",
            f"🤖 **Model:** {result.model}",
        ]
        
        if result.seed:
            lines.append(f"🎲 **Seed:** {result.seed}")
        
        lines.extend([
            "",
            f"📁 **Saved to:** `{result.local_path}`",
        ])
        
        if result.url:
            lines.append(f"🔗 **URL:** {result.url[:80]}...")
        
        return "\n".join(lines)
    
    def _track_usage(self, result: GeneratedImage):
        """Track usage statistics."""
        self.usage["total_generations"] += 1
        if result.cost:
            self.usage["total_cost_usd"] += result.cost
        
        provider_key = result.provider
        if provider_key not in self.usage["by_provider"]:
            self.usage["by_provider"][provider_key] = {
                "count": 0,
                "cost": 0.0
            }
        self.usage["by_provider"][provider_key]["count"] += 1
        if result.cost:
            self.usage["by_provider"][provider_key]["cost"] += result.cost
        
        # Add to history
        self.usage["history"].append({
            "timestamp": datetime.now().isoformat(),
            "provider": result.provider,
            "model": result.model,
            "prompt": result.prompt[:100],
            "cost": result.cost
        })
        
        # Keep only last 100 entries
        self.usage["history"] = self.usage["history"][-100:]
        
        self._save_usage()
    
    def _list_providers(self) -> str:
        """List available providers."""
        status = self._get_provider_status()
        
        lines = ["🎨 **Image Generation Providers**\n"]
        
        for name, info in status.items():
            available = "✅" if info["available"] else "❌"
            cost = "FREE" if info["cost"] == "free" else "Paid"
            
            lines.append(f"{available} **{name.title()}** ({cost})")
            lines.append(f"   Quality: {info['quality']}")
            
            if info["requires_key"]:
                key_status = "✓ Configured" if info["has_key"] else "✗ Not configured"
                lines.append(f"   API Key: {key_status}")
            
            lines.append("")
        
        # Add usage summary
        lines.append(f"\n📊 **Usage This Month:**")
        lines.append(f"   Total images: {self.usage['total_generations']}")
        lines.append(f"   Total cost: ${self.usage['total_cost_usd']:.3f}")
        
        lines.append("\n💡 **Tip:** Pollinations is free and works immediately!")
        lines.append("   For higher quality, configure Stability AI or OpenRouter.")
        
        return "\n".join(lines)
    
    def _list_models(self, provider: str | None = None) -> str:
        """List available models for providers."""
        models = {
            "pollinations": [
                "flux (default, high quality)",
                "turbo (faster, lower quality)",
            ],
            "openrouter": [
                "black-forest-labs/flux.2-pro (best quality)",
                "black-forest-labs/flux.2-flex (faster)",
                "google/gemini-2.5-flash-image-preview",
                "sourceful/riverflow-v2-fast",
            ],
            "stability": [
                "stable-diffusion-xl-1024-v1-0 (default)",
                "stable-diffusion-v1-6",
            ]
        }
        
        if provider and provider in models:
            lines = [f"🤖 **Available Models for {provider.title()}:**\n"]
            for model in models[provider]:
                lines.append(f"• {model}")
            return "\n".join(lines)
        else:
            lines = ["🤖 **Available Models:**\n"]
            for prov, model_list in models.items():
                lines.append(f"\n**{prov.title()}:**")
                for model in model_list[:3]:  # Show first 3
                    lines.append(f"  • {model}")
            return "\n".join(lines)
