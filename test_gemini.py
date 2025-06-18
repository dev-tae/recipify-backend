# test_gemini.py
import os
import asyncio
from google import generativeai as genai # Corrected import
from dotenv import load_dotenv

load_dotenv() # This will load .env from the directory where you run the script,
              # or from a parent directory if your .env is there.

API_KEY = os.environ.get("GEMINI_API_KEY")

async def main():
    if not API_KEY:
        print("Error: GEMINI_API_KEY not found in environment variables or .env file.")
        print("Please ensure your .env file is in the same directory or a parent directory,")
        print("or that GEMINI_API_KEY is set in your system environment.")
        return

    print(f"Attempting to configure Gemini with API key (first 5 chars): {API_KEY[:5]}...")
    try:
        genai.configure(api_key=API_KEY)
        print("Gemini configured successfully.")
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        return

    # Use the model name you are targeting, e.g., "gemini-1.5-flash-latest"
    # or the one shown in your quota screenshot "gemini-1.5-flash"
    model_name_to_test = "gemini-1.5-flash-latest"
    print(f"Initializing Gemini model: {model_name_to_test}")
    try:
        model = genai.GenerativeModel(model_name=model_name_to_test)
        print("Model initialized.")
    except Exception as e:
        print(f"Error initializing model: {e}")
        return

    try:
        print("Sending simple request to Gemini ('Tell me a short joke.')...")
        response = await model.generate_content_async("Tell me a short joke.")
        print("\n--- Gemini Response ---")
        print("Response Text:", response.text)
        print("-----------------------\n")
        if response.prompt_feedback:
            print(f"Prompt Feedback: {response.prompt_feedback}")

    except genai.types.BlockedPromptException as bpe:
        print(f"ERROR: Prompt was blocked by Gemini. {bpe}")
    except Exception as e:
        print(f"ERROR during API call: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())