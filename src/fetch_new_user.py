import argparse
import asyncio
import os
import logging
from typing import List
from browser_use import (
    Controller,
    ActionResult,
    Browser,
    Agent,
    BrowserConfig,
    BrowserContextConfig,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from parse import parse_wgzimmer_search_results
from pydantic import BaseModel
from dotenv import load_dotenv
import sys

load_dotenv()

LOG_FILE_PATH = "/app/app.log"  # Log file inside the container
LOG_LEVEL = logging.INFO

# --- Configure Logging to File ---
log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# File Handler
file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a")  # 'a' for append
file_handler.setFormatter(log_formatter)

# Get root logger and add the file handler
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
# Remove existing handlers if basicConfig was somehow called before or by libraries implicitly
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
# Add our file handler
root_logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

sys.stdout.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

assert os.getenv("GEMINI_API_KEY"), "Missing GEMINI_API_KEY in environment."


all_contents: List[str] = []


class PageParam(BaseModel):
    page_number: int


controller = Controller()


@controller.action("Saves Page Content", param_model=PageParam)
async def save_content(params: PageParam, browser: Browser):
    page = await browser.get_current_page()
    content = await page.content()
    all_contents.append(content)
    return ActionResult(extracted_content="page content saved")


browser = Browser(
    config=BrowserConfig(
        headless=False,
        disable_security=False,
        keep_alive=True,
        new_context_config=BrowserContextConfig(
            keep_alive=True,
            disable_security=False,
        ),
    )
)


async def main(
    max_price: int,
    region: str,
    nur_unbefristete: bool,
    llm,
):
    global all_contents
    all_contents.clear()

    task = f"""
        First go to google.com and search 'www.wgzimmer.ch' manually.
        Then click on www.wgzimmer.ch and navigate to 'ein freies zimmer suchen'
        Now search for flats in {region} up to {max_price} CHF.
    """
    if nur_unbefristete:
        task += " Only show 'Nur Unbefristete' offers."
    task += " Skip through all and save all via save_content result. You don't need to scroll through them."
    task += " When you encounter adds or pop ups, close them."

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        controller=controller,
    )
    res = await agent.run()

    final_result: ActionResult = res.history[-1].result[-1]
    logging.info(f"Final Result: {res.extracted_content}")
    if not final_result.success:
        raise ValueError("Agent failed.")

    contents = list(all_contents)
    all_contents.clear()
    return contents


if __name__ == "__main__":
    logging.info("Entering main execution block.")

    parser = argparse.ArgumentParser()
    parser.add_argument("--export_path", type=str, required=True)
    parser.add_argument("--max_price", type=int, default=800)
    parser.add_argument("--region", type=str, default="zürich stadt")
    parser.add_argument(
        "--gemini_model", type=str, default="gemini-2.5-flash-preview-04-17"
    )
    parser.add_argument(
        "--nur_unbefristete",
        action="store_true",
    )
    args = parser.parse_args()

    llm = ChatGoogleGenerativeAI(model=args.gemini_model)

    os.makedirs(os.path.dirname(args.export_path), exist_ok=True)

    vals = asyncio.run(
        main(
            max_price=args.max_price,
            region=args.region,
            nur_unbefristete=args.nur_unbefristete,
            llm=llm,
        )
    )

    listings = []
    for idx, content in enumerate(vals):
        logging.info(f"Attempting to parse page {idx}")
        try:
            listings.extend(parse_wgzimmer_search_results(content)[-1])
        except Exception as e:
            logging.error(f"Failed to parse page {idx}: {e}")

    with open(args.export_path, "w") as f:
        f.write("\n".join((i.model_dump_json() for i in listings)))

    logging.info(f"Successfully saved to {args.export_path}")
