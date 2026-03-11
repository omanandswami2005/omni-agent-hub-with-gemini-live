import os
from dotenv import load_dotenv
load_dotenv()

from google import genai
from app.config import settings

def main():
    print(f"Project: {settings.GOOGLE_CLOUD_PROJECT}, Location: {settings.GOOGLE_CLOUD_LOCATION}")
    client = genai.Client(
        vertexai=True,
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_LOCATION
    )
    
    print("Listing all available models:")
    try:
        models = client.models.list()
        with open('models.txt', 'w') as f:
            for m in models:
                if "live" in m.name.lower() or "audio" in m.name.lower() or "flash" in m.name.lower():
                    f.write(f"*** MATCH: {m.name} --- {m.description} ***\n")
        print("Done. Saved to models.txt")
    except Exception as e:
        print(f"Failed to list models: {e}")

if __name__ == "__main__":
    main()
