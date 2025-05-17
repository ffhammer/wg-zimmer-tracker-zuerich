import os
import subprocess

# --- Configuration ---
# Assume this script is run from the same directory as docker-compose.yml
SERVICE_NAME = "app"
# This is the base path *inside the container* where listings are mounted
CONTAINER_LISTINGS_BASE_PATH = "/app/listings"


def start_fetch_table_terminal_process() -> None:
    # Construct the docker-compose command
    docker_cmd_list = [
        "cd",
        os.getcwd(),
        "&&",
        "docker-compose",
        "run",
        "--build",
        "--service-ports",  # Keep this if you need ports, otherwise remove
        SERVICE_NAME,
    ]

    terminal_cmd_list = [
        "osascript",
        "-e",
        'tell application "Terminal" to activate',
        "-e",
        f'tell application "Terminal" to do script "{" ".join(docker_cmd_list)}"',
    ]
    _ = subprocess.Popen(terminal_cmd_list, cwd=os.getcwd(), start_new_session=True)
