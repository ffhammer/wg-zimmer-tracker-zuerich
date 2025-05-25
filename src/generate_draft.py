import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.database import load_saved_draft_listing_pairs
from src.logger import logger
from src.models import BaseListing

# Load environment variables
assert load_dotenv()


# Read personal background once
def get_personal_information():
    with open("info_about_me.md", "r") as f:
        personal_background: str = f.read()
    return personal_background


client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
)


STANDARD_SYSTEM_PROMPT: str = """
You are helping Felix write a personalized draft message for a housing listing in Zürich.
Write in the same language as the listing (German or English).
Emphasize Felix's strengths and suitability as a tenant, making sure to tailor the message to the unique aspects of each listing.
Carefully analyze Felix's style from the provided examples and mimic his tone, structure, and approach.
Even more importantly, deeply analyze how Felix adapts his responses to each listing and closely replicate this adaptive approach.
Really Try Copy his behaviour especially that of the drafts posts (by date).
Return only the draft message, without any extra explanation or commentary.
"""


def generate_draft(
    listing: BaseListing,
    system_prompt: str = STANDARD_SYSTEM_PROMPT,
    include_imgs: bool = True,
):
    logger.debug("starting to generate a draft")
    personal_info = get_personal_information()

    example_pairs = load_saved_draft_listing_pairs()
    examples = "Example Drafts:\n"
    for example_listing, example_draft in example_pairs:
        examples += (
            "\n"
            + ("-") * 100
            + f"\nListing: {json.dumps(example_listing.data_for_llm())}\nMessage: {example_draft.content}\n"
            + "-" * 100
        )

    prompt = [
        types.Content(role="user", parts=[types.Part(text=personal_info)]),
        types.Content(role="user", parts=[types.Part(text=examples)]),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text=json.dumps(
                        listing.to_llm_input(include_images=include_imgs), indent=4
                    )
                )
            ],
        ),
    ]

    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-05-20",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    logger.info("Draft generation complete")
    return response.text
