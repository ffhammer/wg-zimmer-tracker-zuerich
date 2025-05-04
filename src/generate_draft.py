import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

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
You are helping Felix generate a draft for a new listing in Zürich. 
First, incorporate his personal background, then include the listing details and images.
Match the language of the listing: German for German listings, English for English listings.
Emphasize Felix's key traits to appeal to landlords.
Only return the draft nothing else! 
Really stay close to my example draft, in terms of overall style and length!!!
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
    listing_msg = HumanMessage(
        content=listing.to_llm_input(include_images=include_imgs)
    )
    inputs_tokens, output_tokens = 0, 0
    for i in model.stream([system_msg, user_msg, listing_msg]):
        inputs_tokens += i.usage_metadata["input_tokens"]
        output_tokens += i.usage_metadata["output_tokens"]
        yield i.content

    logger.info(f"Took {inputs_tokens} input  and {output_tokens} ouput tokens")
