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
SUCCESS_MARKER = "Successfully saved to"
ENTRYPOINT_FINISHED_MARKER = (
    "[Entrypoint] Application process"  # Helps detect clean exit
)


class DockerComposeRunnerError(Exception):
    """Custom exception for errors during docker-compose execution."""

    pass


def run_wgzimmer_fetcher(
    export_filename: str,  # Just the filename (e.g., "output.jsonl")
    max_price: int = 800,
    region: str = "zürich stadt",
    gemini_model: str = "gemini-2.5-flash-preview-04-17",
    nur_unbefristete: bool = False,
    compose_file: Optional[str] = None,  # Optional: specify a different compose file
    project_dir: str = COMPOSE_PROJECT_DIR,
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
    cmd_list = ["docker-compose"]
    if compose_file:
        cmd_list.extend(["-f", compose_file])
    cmd_list.extend(
        [
            "-p",
            "wgzimmer_fetcher_sdk",  # Use a specific project name for isolation
            "run",
            "--rm",  # Automatically remove the container on exit
            "--service-ports",  # Keep this if you need ports, otherwise remove
            SERVICE_NAME,
            # Arguments for the entrypoint.sh -> fetch_new_user.py script
            "--export_path",
            container_export_path,
            "--max_price",
            str(max_price),
            "--region",
            region,
            "--gemini_model",
            gemini_model,
        ]
    )
    if nur_unbefristete:
        cmd_list.append("--nur_unbefristete")

    print(
        f"--- Running command: {' '.join(shlex.quote(c) for c in cmd_list)}",
        file=sys.stderr,
    )
    print(f"--- Working directory: {project_dir}", file=sys.stderr)
    print(
        f"--- Expecting output file inside container at: {container_export_path}",
        file=sys.stderr,
    )
    print("-" * 20, file=sys.stderr)

    success_detected = False
    clean_exit_detected = False
    process = None  # Initialize process variable

    try:
        # Start the process
        # Use Popen for streaming output
        # Combine stdout and stderr to see all logs/errors
        # text=True decodes output, bufsize=1 for line buffering
        process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=project_dir,  # Run docker-compose from the correct directory
            encoding="utf-8",  # Be explicit about encoding
        )

        # Read output line by line while the process is running
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                line_stripped = line.strip()
                yield line_stripped  # Yield the raw line
                if SUCCESS_MARKER in line_stripped:
                    print(
                        f"--- Success marker found: '{line_stripped}'", file=sys.stderr
                    )
                    success_detected = True
                if ENTRYPOINT_FINISHED_MARKER in line_stripped:
                    if (
                        "exited naturally with code 0" in line_stripped
                        or "exited with code 0" in line_stripped
                    ):
                        print(
                            f"--- Clean exit marker found: '{line_stripped}'",
                            file=sys.stderr,
                        )
                        clean_exit_detected = True

        process.wait()
        return_code = process.returncode

        print("-" * 20, file=sys.stderr)
        print(f"--- Process finished with exit code: {return_code}", file=sys.stderr)
        print(f"--- Success marker detected: {success_detected}", file=sys.stderr)
        print(
            f"--- Clean exit detected via log: {clean_exit_detected}", file=sys.stderr
        )

        # --- Geänderte Logik ---
        # Prüfe, ob ein Fehler aufgetreten ist
        # Fehler, wenn return_code != 0 ODER wenn der Success Marker fehlt
        # (Clean exit via log ist nur eine Zusatzinfo, wir verlassen uns primär auf den Code
        # UND den Marker aus dem Python-Skript)
        if return_code != 0:
            raise DockerComposeRunnerError(
                f"Docker Compose process failed with exit code {return_code}."
            )
        if not success_detected:
            raise DockerComposeRunnerError(
                f"Docker Compose process finished with exit code 0, "
                f"but the success marker '{SUCCESS_MARKER}' was not found in logs."
            )

        # Wenn wir hier ankommen, war alles erfolgreich.
        # Die Funktion endet einfach (implizites Return None).

    except FileNotFoundError:
        print("--- Error: 'docker-compose' command not found.", file=sys.stderr)
        raise DockerComposeRunnerError("docker-compose command not found.") from None
    except subprocess.CalledProcessError as e:  # Fängt Fehler direkt von Popen/wait ab
        print(f"--- Docker Compose execution failed: {e}", file=sys.stderr)
        raise DockerComposeRunnerError(f"Docker Compose execution failed: {e}") from e
    except Exception as e:
        print(f"--- An unexpected error occurred in SDK: {e}", file=sys.stderr)
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)  # Wait a bit for termination
            except:  # Catch potential errors during termination
                pass
        # Wrap unknown errors too
        if not isinstance(e, DockerComposeRunnerError):
            raise DockerComposeRunnerError(f"SDK wrapper failed: {e}") from e
        else:
            raise


# --- Example Usage ---
if __name__ == "__main__":
    print("Starting WG Zimmer Fetcher via SDK function...")

    output_filename = "sdk_test_output.jsonl"
    try:
        # Make sure the host directory exists
        host_listings_dir = os.path.join(COMPOSE_PROJECT_DIR, "listings")
        os.makedirs(host_listings_dir, exist_ok=True)
        print(
            f"Expecting output file on host at: {os.path.join(host_listings_dir, output_filename)}"
        )

        final_success = False
        # The function returns a generator, iterate through it to get logs
        log_generator = run_wgzimmer_fetcher(
            export_filename=output_filename,
            max_price=950,
            region="zürich kreis 6",
            nur_unbefristete=True,
        )
        for log_line in log_generator:
            print(f"SDK Log: {log_line}")

    except DockerComposeRunnerError as e:
        print(f"Error running fetcher: {e}", file=sys.stderr)
    except Exception as e:
        print(
            f"An unexpected error occurred in the example usage: {e}", file=sys.stderr
        )
