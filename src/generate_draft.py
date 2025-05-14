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
    system_msg = SystemMessage(system_prompt)
    user_msg = HumanMessage(
        content=[{"type": "text", "text": get_personal_information()}]
    )

    example_pairs = load_saved_draft_listing_pairs()
    logger.debug(f"Incorporating {len(example_pairs)} examples")
    examples = "Example Drafts:\n"
    for example_listing, example_draft in example_pairs:
        examples += (
            "\n"
            + ("-") * 100
            + (
                f"""\nListing: {json.dumps(example_listing.data_for_llm())}
        Message: {example_draft.content}\n"""
                + "-" * 100
            )
        )

    examples = HumanMessage(content=examples)

    listing_msg = HumanMessage(
        content=listing.to_llm_input(include_images=include_imgs)
    )
    print("start")
    inputs_tokens, output_tokens = 0, 0
    for i in model.stream([system_msg, examples, user_msg, listing_msg]):
        inputs_tokens += i.usage_metadata["input_tokens"]
        output_tokens += i.usage_metadata["output_tokens"]
        yield i.content

    logger.info(f"Took {inputs_tokens} input  and {output_tokens} ouput tokens")
