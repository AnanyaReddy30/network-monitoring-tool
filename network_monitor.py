#!/usr/bin/env python3
"""
Network Monitoring Tool
========================
A simple, multi-threaded tool that continuously pings a list of hosts,
tracks whether each one is UP or DOWN, measures response time (latency),
prints a live status table to the console, and writes a permanent record
of every check to a log file.

Author: (your name here)
Skills demonstrated: subprocess handling, threading/concurrency,
string parsing with regex, logging, basic network diagnostics (ICMP ping).

HOW TO RUN:
    python3 network_monitor.py

HOW TO STOP:
    Press Ctrl+C. The program will shut down cleanly.

REQUIREMENTS:
    - Python 3.7+
    - The system 'ping' command must be available (it is on Windows,
      macOS, and virtually all Linux distros by default).
    - No third-party packages needed — everything here is the Python
      standard library.
"""

import subprocess       # lets us run the system 'ping' command and capture its output
import platform         # lets us detect if we're on Windows vs. Linux/Mac
import threading        # lets us ping multiple hosts at the same time, not one-by-one
import time             # for sleeping between checks and timestamping
import re               # for pulling the latency number out of ping's text output
import logging          # for writing a permanent record to a log file
import os
from datetime import datetime

# --------------------------------------------------------------------------
# 1. CONFIGURATION — edit this section to change what/how you monitor
# --------------------------------------------------------------------------

# The hosts you want to monitor. Mix of a public DNS server, a well-known
# domain, and a placeholder for a local device (e.g., your home router).
# Edit this list to match whatever you want to track.
HOSTS = [
    "127.0.0.1",       # loopback — your own machine, should basically always be UP
    "8.8.8.8",         # Google's public DNS server
    "google.com",      # a real-world domain name
    "192.168.1.1",     # example placeholder for a home router — change to your own
]

CHECK_INTERVAL_SECONDS = 10   # how often (in seconds) each host gets re-pinged
PING_TIMEOUT_SECONDS = 2      # how long to wait for a reply before calling it a failure
LOG_FILE = "network_monitor.log"

# --------------------------------------------------------------------------
# 2. LOGGING SETUP — this writes every check result to a file on disk,
#    so you have a historical record even after the console output scrolls away.
# --------------------------------------------------------------------------

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --------------------------------------------------------------------------
# 3. SHARED STATE — a dictionary that every host's monitoring thread writes
#    into, and that the main thread reads from to draw the status table.
#    A "lock" prevents two threads from reading/writing it at the exact
#    same instant and corrupting the data (a classic threading bug).
# --------------------------------------------------------------------------

status_lock = threading.Lock()
host_status = {
    host: {"state": "UNKNOWN", "latency_ms": None, "last_checked": None}
    for host in HOSTS
}

# A flag used to tell all the background threads to stop when the user
# presses Ctrl+C.
stop_event = threading.Event()


# --------------------------------------------------------------------------
# 4. THE PING FUNCTION — runs the operating system's real 'ping' command
#    (rather than reinventing ICMP from scratch) and parses its text output.
# --------------------------------------------------------------------------

def ping_host(host: str, timeout: int = PING_TIMEOUT_SECONDS):
    """
    Sends a single ping to `host` and returns a tuple: (is_up, latency_ms).

    - is_up: True if the host replied, False if it didn't.
    - latency_ms: round-trip time in milliseconds (float), or None if the
      host was down or the reply time couldn't be parsed.

    Why use subprocess instead of a networking library?
    Sending raw ICMP packets normally requires admin/root privileges on
    most operating systems. The 'ping' command that ships with the OS
    already has that privilege, so we simply reuse it and read its output.
    This is a common, practical pattern in real IT/network tooling.
    """
    # Windows and Linux/Mac use different flags for "send 1 packet" and
    # "wait this many seconds/milliseconds for a reply", so we branch here.
    is_windows = platform.system().lower() == "windows"

    if is_windows:
        # -n 1  -> send exactly 1 echo request
        # -w    -> timeout in MILLISECONDS
        command = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else:
        # -c 1  -> send exactly 1 echo request
        # -W    -> timeout in SECONDS (Linux) — macOS uses -t but we keep
        #          this simple since this project targets Linux/Windows.
        command = ["ping", "-c", "1", "-W", str(timeout), host]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,           # decode output as a normal string, not bytes
            timeout=timeout + 2,  # hard safety cap in case ping itself hangs
        )
    except subprocess.TimeoutExpired:
        # The ping command itself didn't finish in time — treat as down.
        return False, None
    except FileNotFoundError:
        # 'ping' isn't installed / not on PATH at all.
        logging.error("The 'ping' command was not found on this system.")
        return False, None

    output = result.stdout

    # A return code of 0 means ping got a reply. Anything else means
    # it didn't (host down, unreachable, name didn't resolve, etc).
    is_up = (result.returncode == 0)

    latency_ms = None
    if is_up:
        # Ping's text output looks like:  "time=23.4 ms"  or  "time<1ms"
        # We use a regular expression to pull just the number out of that.
        match = re.search(r"time[=<]([\d.]+)\s*ms", output)
        if match:
            latency_ms = float(match.group(1))

    return is_up, latency_ms


# --------------------------------------------------------------------------
# 5. THE MONITOR LOOP FOR ONE HOST — this function is what each background
#    thread actually runs, forever, until told to stop.
# --------------------------------------------------------------------------

def monitor_host(host: str):
    """
    Continuously pings a single host every CHECK_INTERVAL_SECONDS,
    updates the shared host_status dictionary, and writes a line to the
    log file for every check performed.
    """
    while not stop_event.is_set():
        is_up, latency_ms = ping_host(host)
        state = "UP" if is_up else "DOWN"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Update the shared dictionary safely using the lock, so the main
        # thread never reads it while it's half-updated.
        with status_lock:
            host_status[host]["state"] = state
            host_status[host]["latency_ms"] = latency_ms
            host_status[host]["last_checked"] = timestamp

        # Write a permanent record to the log file.
        if is_up:
            logging.info(f"{host:<15} UP    latency={latency_ms} ms")
        else:
            logging.info(f"{host:<15} DOWN  latency=N/A")

        # wait() acts like time.sleep() here, but it wakes up immediately
        # if stop_event gets set, so Ctrl+C feels instant instead of
        # waiting for the full interval to finish.
        stop_event.wait(CHECK_INTERVAL_SECONDS)


# --------------------------------------------------------------------------
# 6. THE DISPLAY LOOP — runs on the main thread, redraws a simple table
#    of every host's current status every couple of seconds.
# --------------------------------------------------------------------------

def print_status_table():
    """Clears the terminal and prints the latest known status of every host."""
    os.system("cls" if platform.system().lower() == "windows" else "clear")

    print("=" * 60)
    print(f" NETWORK MONITOR   (updated {datetime.now().strftime('%H:%M:%S')})")
    print("=" * 60)
    print(f"{'HOST':<20}{'STATUS':<10}{'LATENCY':<12}{'LAST CHECKED':<20}")
    print("-" * 60)

    with status_lock:
        for host, info in host_status.items():
            state = info["state"]
            latency = f"{info['latency_ms']} ms" if info["latency_ms"] is not None else "-"
            last_checked = info["last_checked"] or "-"

            # Simple visual cue so UP/DOWN is easy to spot at a glance.
            marker = "🟢" if state == "UP" else ("🔴" if state == "DOWN" else "⚪")

            print(f"{host:<20}{marker + ' ' + state:<10}{latency:<12}{last_checked:<20}")

    print("-" * 60)
    print(f"Full history is being written to: {LOG_FILE}")
    print("Press Ctrl+C to stop monitoring.")


# --------------------------------------------------------------------------
# 7. MAIN ENTRY POINT — starts one background thread per host, then loops
#    on the main thread just to redraw the table until the user quits.
# --------------------------------------------------------------------------

def main():
    print(f"Starting Network Monitor for {len(HOSTS)} hosts...")
    print(f"Checking every {CHECK_INTERVAL_SECONDS} seconds. Logging to {LOG_FILE}.\n")
    time.sleep(1.5)

    # Launch one independent monitoring thread per host. Because they run
    # concurrently, a slow/unreachable host doesn't delay checks on the
    # others — each host is checked on its own schedule.
    threads = []
    for host in HOSTS:
        t = threading.Thread(target=monitor_host, args=(host,), daemon=True)
        t.start()
        threads.append(t)

    try:
        # Redraw the table periodically on the main thread.
        while True:
            print_status_table()
            time.sleep(2)
    except KeyboardInterrupt:
        # Ctrl+C was pressed — signal all threads to stop and exit cleanly.
        print("\nStopping Network Monitor...")
        stop_event.set()
        for t in threads:
            t.join(timeout=2)
        print("Stopped. Check network_monitor.log for the full history.")


if __name__ == "__main__":
    main()
