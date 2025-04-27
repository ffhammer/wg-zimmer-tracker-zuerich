import argparse
import asyncio
import os
import sys
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

assert os.getenv("GEMINI_API_KEY"), "Missing GEMINI_API_KEY in environment."

logging.basicConfig(level=logging.INFO)

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


llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-preview-04-17")
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


async def main(max_price: int, region: str, nur_unbefristete: bool):
    global all_contents
    all_contents.clear()

    task = f"""
        First go to google.com and search 'test' manually.
        Then go to https://www.wgzimmer.ch/wgzimmer/search/mate.html and
        search for flats in {region} up to {max_price} CHF.
    """
    if nur_unbefristete:
        task += " Only show 'Nur Unbefristete' offers."
    task += " Skip through all pages and save contents."

    agent = Agent(task=task, llm=llm, browser=browser, controller=controller)
    res = await agent.run()

    final_result: ActionResult = res.history[-1].result[-1]
    logging.info(f"Final Result: {res.extracted_content}")
    if not final_result.success:
        raise ValueError("Agent failed.")

    contents = list(all_contents)
    all_contents.clear()
    return contents


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export_path", type=str, required=True)
    parser.add_argument("--max_price", type=int, default=800)
    parser.add_argument("--region", type=str, default="zürich stadt")
    parser.add_argument("--nur_unbefristete", action="store_true")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.export_path), exist_ok=True)

    vals = asyncio.run(
        main(
            max_price=args.max_price,
            region=args.region,
            nur_unbefristete=args.nur_unbefristete,
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
        f.write("\n".join(i.model_dump_json() for i in listings))

    logging.info(f"Successfully saved to {args.export_path}")
