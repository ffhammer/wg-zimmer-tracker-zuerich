import subprocess
import sys
import os
import shlex
from typing import Generator, Optional

# --- Configuration ---
# Assume this script is run from the same directory as docker-compose.yml
COMPOSE_PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)  # Or specify absolute path
SERVICE_NAME = "app"
# This is the base path *inside the container* where listings are mounted
CONTAINER_LISTINGS_BASE_PATH = "/app/listings"


def start_terminal_process(
    export_filename: str,  # Just the filename (e.g., "output.jsonl")
    max_price: int = 800,
    gemini_model: str = "gemini-2.5-flash-preview-04-17",
    nur_unbefristete: bool = False,
) -> Generator[str, None, bool]:
    """
    Runs the wgzimmer fetching container via docker-compose, yields logs live,
    and returns True if the success marker is found in logs and the container exits cleanly.

    Args:
        export_filename: The name of the file to save results to within the mapped volume (e.g., "output.jsonl").
        max_price: Maximum price filter for the search.
        region: Region filter for the search.
        gemini_model: The Gemini model to use.
        nur_unbefristete: If True, only search for 'Nur Unbefristete' offers.
        compose_file: Optional path to a specific docker-compose file.
        project_dir: The directory containing the docker-compose.yml file.

    Yields:
        str: Lines of log output (stdout/stderr merged) from the container.

    Returns:
        bool: True if the process completed successfully (success marker found, clean exit), False otherwise.

    Raises:
        DockerComposeRunnerError: If docker-compose command fails to start or returns a non-zero exit code
                                   without indicating successful completion within the logs.
        FileNotFoundError: If docker-compose is not found.
    """
    # Construct the container-internal export path
    container_export_path = os.path.join(CONTAINER_LISTINGS_BASE_PATH, export_filename)

    # Construct the docker-compose command
    docker_cmd_list = [
        "cd",
        COMPOSE_PROJECT_DIR,
        "&&",
        "docker-compose",
        "run",
        "--build",
        "--rm",  # Automatically remove the container on exit
        "--service-ports",  # Keep this if you need ports, otherwise remove
        SERVICE_NAME,
        # Arguments for the entrypoint.sh -> fetch_new_user.py script
        "--export_path",
        container_export_path,
        "--max_price",
        str(max_price),
        "--gemini_model",
        gemini_model,
    ]

    if nur_unbefristete:
        docker_cmd_list.append("--nur_unbefristete")

    terminal_cmd_list = [
        "osascript",
        "-e",
        'tell application "Terminal" to activate',
        "-e",
        f'tell application "Terminal" to do script "{' '.join(docker_cmd_list)}"',
    ]
    _ = subprocess.Popen(
        terminal_cmd_list, cwd=COMPOSE_PROJECT_DIR, start_new_session=True
    )


if __name__ == "__main__":
    # print(COMPOSE_PROJECT_DIR)
    start_terminal_process(export_filename="test.json")
