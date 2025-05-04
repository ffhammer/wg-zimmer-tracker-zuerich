import json
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

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


# Initialize the AI model
model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-preview-04-17", api_key=os.environ["GEMINI_API_KEY"]
)

STANDARD_SYSTEM_PROMPT: str = """
You are assisting Felix in crafting a compelling draft for a new listing in Zürich.
Begin by incorporating his personal background, followed by the listing details and images.
Adapt the language to match the listing: use German for German listings and English for English listings.
Highlight Felix's key qualities to make a strong impression on landlords.
Ensure your response aligns with the style demonstrated in the provided examples, tailoring it to suit each specific listing.
Return only the draft, with no additional commentary or content.
"""


def generate_draft(
    listing: BaseListing,
    system_prompt: str = STANDARD_SYSTEM_PROMPT,
    include_imgs: bool = True,
):
    logger.debug("starting to generate a draft")
    system_msg = SystemMessage(system_prompt)
    user_msg = HumanMessage(
        content=[{"type": "text", "text": get_personal_information()}]
    )

    example_pairs = load_saved_draft_listing_pairs()
    logger.debug(f"Incorporating {len(example_pairs)} examples")
    examples = "Example Drafts:\n"
    for example_listing, example_draft in example_pairs:
        examples += (
            f"""\nListing: {json.dumps(example_listing.data_for_llm())}
        Message: {example_draft.content}\n"""
            + "-" * 100
        )

    examples = HumanMessage(content=examples)

    listing_msg = HumanMessage(
        content=listing.to_llm_input(include_images=include_imgs)
    )
    inputs_tokens, output_tokens = 0, 0
    for i in model.stream([system_msg, examples, user_msg, listing_msg]):
        inputs_tokens += i.usage_metadata["input_tokens"]
        output_tokens += i.usage_metadata["output_tokens"]
        yield i.content

    logger.info(f"Took {inputs_tokens} input  and {output_tokens} ouput tokens")
