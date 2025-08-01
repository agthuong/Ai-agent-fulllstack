import os
import google.generativeai as genai
from PIL import Image
import io
from dotenv import load_dotenv
import logging
from .prompts import VISION_PROMPT

# Set up basic logging to see the output in the console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# Configure the Gemini API key
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in .env file. Please add it.")

genai.configure(api_key=api_key)

# Initialize the Gemini Pro Vision model
vision_model = genai.GenerativeModel('gemini-2.5-flash')

# Mặc định prompt cho phân tích hình ảnh
# DEFAULT_VISION_PROMPT is now imported as VISION_PROMPT from prompts.py

async def get_gemini_vision_report(image_path_or_bytes, prompt=None):
    """
    Analyzes an image using the Gemini Pro Vision model and returns a textual report.

    This function takes an image (as a file path or bytes) and a text prompt, 
    sends them to the Gemini API, and returns the generated text description.

    Args:
        image_path_or_bytes: Either a path to an image file or the image data as bytes
        prompt: The text prompt to guide the analysis. If None, uses the default prompt.

    Returns:
        A string containing the report generated by the vision model.
        
    Raises:
        Exception: If the API call to Gemini fails.
    """
    try:
        logging.info("Preparing to call Gemini Vision API.")
        
        # Determine if input is a file path or bytes
        if isinstance(image_path_or_bytes, str):
            # It's a file path
            logging.info(f"Loading image from path: {image_path_or_bytes}")
            image = Image.open(image_path_or_bytes)
        else:
            # It's bytes data
            logging.info("Loading image from bytes data")
            image = Image.open(io.BytesIO(image_path_or_bytes))
        
        # Use default prompt if none provided
        if prompt is None:
            prompt = VISION_PROMPT
            logging.info("Using default vision prompt")
        
        # Prepare the content for the API call
        content = [prompt, image]
        
        logging.info(f"Sending prompt to Gemini: '{prompt[:150]}...'")
        
        # Call the Gemini API
        response = vision_model.generate_content(content)
        
        # Log the raw response for debugging
        logging.info("Received a successful response from Gemini.")
        logging.debug(f"Full Gemini response: {response.text}")
        
        # Return the generated text
        return response.text
    except Exception as e:
        # Log the full exception to the console
        logging.error(f"Error calling Gemini Vision API: {e}", exc_info=True)
        # Re-raise the exception so it can be caught by the Flask app and shown in the UI
        raise

# Example usage (for testing purposes)
if __name__ == '__main__':
    # This part will only run when the script is executed directly
    try:
        # Test with a file path
        sample_image_path = "room_images.jpg"
        if os.path.exists(sample_image_path):
            report = get_gemini_vision_report(sample_image_path)
            print("--- Gemini Vision Report (from file path) ---")
            print(report)
        else:
            print(f"Test image not found at {sample_image_path}")
            
        # Test with image bytes
        try:
            with open("another_test_image.jpg", "rb") as f:
                sample_image_bytes = f.read()
            
            sample_prompt = "Describe this image and suggest a question a user might ask about it."
            
            report = get_gemini_vision_report(sample_image_bytes, sample_prompt)
            
            print("--- Gemini Vision Report (from bytes) ---")
            print(report)
        except FileNotFoundError:
            print("Second test image not found.")
        
    except Exception as e:
        print(f"An error occurred during the test run: {e}") 