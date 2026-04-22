"""Vision client for image description using GPT-4o-mini.

This client provides image-to-text capabilities for agents that use
non-multimodal models like DeepSeek. It uses GPT-4o-mini to describe
images, which can then be processed by the main LLM.
"""

import base64
import logging
from typing import Optional

import httpx
from openai import AsyncOpenAI

from src.config import Settings

logger = logging.getLogger(__name__)


class VisionClient:
    """
    Client for image description using GPT-4o-mini.
    
    This client is used when the main LLM (e.g., DeepSeek) doesn't support
    vision capabilities. It downloads images and sends them to GPT-4o-mini
    for text description.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        # Use OpenAI for vision (GPT-4o-mini)
        # Support both direct OpenAI and OpenRouter
        if settings.openrouter_api_key:
            self.client = AsyncOpenAI(
                api_key=settings.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1"
            )
        else:
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        self.model = "gpt-4o-mini"  # Vision-capable, cost-effective
        logger.info(f"VisionClient initialized with model: {self.model}")
    
    async def describe_image(
        self, 
        image_url: str, 
        context: Optional[str] = None,
        max_tokens: int = 1000
    ) -> str:
        """
        Describe an image using GPT-4o-mini.
        
        Args:
            image_url: URL of the image to describe
            context: Optional context about what to look for (e.g., "lineup poster")
            max_tokens: Maximum tokens in response
            
        Returns:
            Text description of the image
        """
        try:
            # Download image
            image_base64 = await self._download_image(image_url)
            if not image_base64:
                logger.error(f"Failed to download image: {image_url}")
                return ""
            
            # Prepare prompt
            if context:
                prompt = f"Describe this {context} in detail. List all text, names, and important visual elements you can see."
            else:
                prompt = "Describe this image in detail. List all text and important visual elements you can see."
            
            # Call vision model
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=max_tokens
            )
            
            description = response.choices[0].message.content
            logger.debug(f"Image description ({len(description)} chars): {description[:100]}...")
            return description
            
        except Exception as e:
            logger.error(f"Vision description failed: {e}")
            return ""
    
    async def describe_lineup_image(
        self, 
        image_url: str,
        festival_context: Optional[str] = None
    ) -> str:
        """
        Specialized method for describing lineup images.
        
        Args:
            image_url: URL of lineup poster/image
            festival_context: Optional context about the festival
            
        Returns:
            Text description with all artist names and details
        """
        prompt_parts = [
            "This is a music festival lineup poster. Please:",
            "1. List ALL artist names you can see (headliners, support acts, DJs)",
            "2. Note the order they appear (usually headliners at top or in larger text)",
            "3. Include any stage names or scheduling info if visible",
            "4. Mention the visual style/design if relevant"
        ]
        
        if festival_context:
            prompt_parts.append(f"\nFestival context: {festival_context}")
        
        prompt = "\n".join(prompt_parts)
        
        try:
            # Download image
            image_base64 = await self._download_image(image_url)
            if not image_base64:
                logger.error(f"Failed to download lineup image: {image_url}")
                return ""
            
            # Call vision model
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1500  # More tokens for lineup lists
            )
            
            description = response.choices[0].message.content
            logger.info(f"Described lineup image: {len(description)} characters, {description.count(chr(10))} lines")
            return description
            
        except Exception as e:
            logger.error(f"Lineup image description failed: {e}")
            return ""
    
    async def _download_image(self, image_url: str) -> Optional[str]:
        """
        Download image and convert to base64.
        
        Args:
            image_url: URL of the image
            
        Returns:
            Base64 encoded image data or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(image_url)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.warning(f"URL is not an image: {content_type}")
                    return None
                
                # Convert to base64
                image_bytes = response.content
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                logger.debug(f"Downloaded image: {len(image_bytes)} bytes")
                return image_base64
                
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            return None
    
    async def close(self):
        """Cleanup resources."""
        await self.client.close()
