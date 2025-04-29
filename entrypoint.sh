#!/bin/bash
# Use bash for better signal handling and process management
set -euo pipefail # Exit on error, unset variable, or pipe failure

LOGFILE="/app/app.log"

# Ensure log file exists and is empty on start
rm -f "$LOGFILE"
touch "$LOGFILE"
# Ensure the user running the python script can write to it
# (Playwright might sometimes run as a different internal user, though unlikely here)
chmod 666 "$LOGFILE"

echo "[Entrypoint] Starting Python application in background..."
# Run the main application, redirecting its stdout/stderr is NOT needed
# because we configured Python logging to write directly to the file.
# Pass any arguments passed to the script ($@) to python
xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" \
    python src/fetch_new_user.py "$@" &

# Get the Process ID (PID) of the background application
APP_PID=$!
echo "[Entrypoint] Application PID: $APP_PID"

# Function to forward signals to the application process
cleanup() {
    echo "[Entrypoint] Caught signal! Forwarding SIGTERM to application (PID $APP_PID)..."
    # Send SIGTERM to the application process
    kill -TERM "$APP_PID" 2>/dev/null || echo "[Entrypoint] App process $APP_PID already gone."
    # Wait for the application process to exit
    echo "[Entrypoint] Waiting for application process $APP_PID to exit..."
    wait "$APP_PID" # Wait specifically for the background process
    APP_EXIT_CODE=$?
    echo "[Entrypoint] Application process $APP_PID exited with code $APP_EXIT_CODE."
    # No need to explicitly kill tail here, as the script will exit
    exit $APP_EXIT_CODE # Exit the entrypoint script with the app's exit code
}

# Trap common termination signals and call cleanup
trap cleanup INT TERM

echo "[Entrypoint] Tailing log file $LOGFILE to stdout..."
# Start tailing the log file in the foreground.
# --follow=name: Handle log rotation if it ever happens
# --retry: Keep trying if the file disappears momentarily
# --pid=$APP_PID: Exit tail when the application process exits (requires coreutils >= 7.5)
# The output of this tail command is what docker logs will show
tail --follow=name --retry --pid=$APP_PID "$LOGFILE" &
TAIL_PID=$!

# Wait for the application process to finish naturally OR for a signal to trigger cleanup
wait $APP_PID
APP_EXIT_CODE=$?
echo "[Entrypoint] Application process $APP_PID exited naturally with code $APP_EXIT_CODE."

# If we reach here, the app finished without a signal interrupting the script.
# We should ensure tail is stopped before exiting.
echo "[Entrypoint] Cleaning up tail (PID $TAIL_PID)..."
kill -TERM "$TAIL_PID" 2>/dev/null || true
wait "$TAIL_PID" 2>/dev/null || true # Wait for tail to finish

exit $APP_EXIT_CODE # Exit with the application's exit code