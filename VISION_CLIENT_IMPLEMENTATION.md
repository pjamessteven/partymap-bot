# Vision Client & Lineup Extraction Fix

## Summary
Fixed the lineup extraction tool to work with DeepSeek (non-multimodal) by implementing a two-step process:
1. GPT-4o-mini describes the image as text
2. DeepSeek extracts structured artist names from the description
3. MusicBrainz lookup for MBIDs

Also removed the redundant `browser_tools.py` file since Playwright toolkit is now used exclusively.

## Files Created

### 1. `apps/api/src/services/vision_client.py`
New VisionClient service using GPT-4o-mini for image description:

```python
class VisionClient:
    def __init__(self, settings):
        self.model = "gpt-4o-mini"
    
    async def describe_image(image_url, context=None) -> str:
        # Downloads image and sends to GPT-4o-mini
        
    async def describe_lineup_image(image_url, festival_context=None) -> str:
        # Specialized for lineup posters
```

## Files Modified

### 1. `apps/api/src/agents/research/tools_lineup.py`
Complete rewrite to use the two-step process:

**Old (didn't work with DeepSeek):**
```python
# Direct vision call to DeepSeek (FAILS)
response = await self.llm.chat_completion(messages=[{
    "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", ...}  # DeepSeek can't process this
    ]
}])
```

**New (works with DeepSeek):**
```python
# Step 1: Vision with GPT-4o-mini
description = await self.vision.describe_lineup_image(image_url, context)

# Step 2: Extraction with DeepSeek (text only)
artist_names = await self._extract_artists_from_description(description, context)

# Step 3: MusicBrainz lookup
artists = await self._lookup_artists(artist_names)
```

### 2. `apps/api/src/api/agents.py`
- Added VisionClient initialization
- Added vision client to LangGraph config
- Proper cleanup in finally block

### 3. `apps/api/src/agents/research/nodes.py`
- Removed browser_tools imports
- Added vision client to get_tools()
- Updated LineupExtractionTool instantiation

### 4. `apps/api/src/agents/research/tools.py`
- Removed browser_tools imports
- Added inline NavigateTool and ClickLinkTool definitions

## Files Deleted

### 1. `apps/api/src/agents/shared/browser_tools.py`
Removed as redundant - Playwright toolkit provides all needed functionality.

## Benefits

1. **DeepSeek Compatibility**: Lineup extraction now works with non-multimodal models
2. **Clear Separation**: Vision (GPT-4o-mini) and text processing (DeepSeek) are separate
3. **Cost Efficient**: GPT-4o-mini is cheaper than GPT-4o for vision tasks
4. **Cleaner Code**: Removed redundant browser_tools.py
5. **Better Error Handling**: Each step can fail independently with clear messages

## Usage

The lineup extraction tool is automatically available when both vision and musicbrainz clients are configured:

```python
# In api/agents.py
vision = VisionClient(settings)  # GPT-4o-mini
musicbrainz = MusicBrainzClient(settings)

config = {
    "vision": vision,
    "musicbrainz": musicbrainz,
    # ... other services
}

# Tool automatically created in get_tools() if both available
```

Agent just calls:
```
extract_lineup(image_url="https://example.com/lineup.jpg")
```

The tool handles:
1. Downloading the image
2. Describing with GPT-4o-mini
3. Extracting artists with DeepSeek
4. Looking up MBIDs with MusicBrainz
5. Returning structured data

All syntax checks pass! ✅
