import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types
from app.config import settings

async def test_live_model():
    print(f"Testing model in Project: {settings.GOOGLE_CLOUD_PROJECT}, Location: {settings.GOOGLE_CLOUD_LOCATION}")
    
    # Needs to match the model we are requesting
    MODEL_ID = "gemini-live-2.5-flash-native-audio"
    
    try:
        print(f"\nAttempting LIVE connection to: {MODEL_ID}")
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            http_options={'api_version': 'v1beta1'}
        )
        
        async with client.aio.live.connect(model=MODEL_ID) as session:
            print(f"Success! Live connection established to {MODEL_ID}.")
            await session.send(input="Hello", end_of_turn=True)
            async for response in session.receive():
                if response.text:
                    print(f"Response: {response.text}")
                    break
        
    except Exception as e:
         print(f"❌ Failed to connect/generate: {e}")

if __name__ == "__main__":
    asyncio.run(test_live_model())
