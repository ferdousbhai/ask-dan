import os
from google import genai


async def get_reasoning_response(
        prompt: str,
        model_name: str = os.getenv("REASONING_MODEL"),
        api_key: str = os.getenv("GOOGLE_API_KEY")
    ) -> str | Exception:    
    if not api_key or not model_name:
        raise ValueError("Environment variables are not set")

    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text
    except Exception as e:
        return e


if __name__ == "__main__":
    import asyncio
    import logging

    from dotenv import load_dotenv

    load_dotenv()
    
    logging.basicConfig(level=logging.INFO)
    
    # Test the reasoning function
    test_prompt = "Explain the concept of recursion in programming using a simple example."
    try:
        result = asyncio.run(get_reasoning_response(test_prompt))
        print(result)
    except Exception as e:
        print(f"Test failed with error: {e}")
