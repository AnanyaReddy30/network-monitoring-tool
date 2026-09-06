A lightweight, multi-threaded Python tool that continuously monitors the uptime and latency of a list of hosts (IP addresses or domain names), displays live status in the console, and logs every check to a file for historical tracking.

Built as a hands-on networking project to practice core concepts relevant to Network Operations: host reachability, ICMP ping, latency measurement, and continuous monitoring.

## Features

- Monitors multiple hosts simultaneously using Python's `threading` module
- Pings each host at a configurable interval (default: every 10 seconds)
- Measures and displays round-trip latency (ms) for each successful check
- Live-updating console table showing UP/DOWN status for every host
- Persistent logging to `network_monitor.log` with timestamps for full history
- Cross-platform: works on macOS, Linux, and Windows
- No third-party dependencies — pure Python standard library

## How It Works

The tool spawns one background thread per host. Each thread runs the system's native `ping` command on a loop, parses the output to determine reachability and response time, and safely updates a shared status dictionary (protected by a thread lock to avoid race conditions). The main thread redraws a status table every couple of seconds while all checks continue running independently in the background.

## Requirements

- Python 3.7+
- The system `ping` command (pre-installed on macOS, Linux, and Windows)

No external packages or `pip install` needed.

## Usage

1. Clone this repository:

git clone https://github.com/AnanyaReddy30/network-monitoring-tool.git
cd network-monitoring-tool


2. (Optional) Edit the host list in `network_monitor.py` to monitor your own targets:
```python
   HOSTS = [
       "127.0.0.1",
       "8.8.8.8",
       "google.com",
       "192.168.1.1",   # replace with your router's IP
   ]
```

3. Run it:

python3 network_monitor.py


4. Press `Ctrl+C` to stop monitoring at any time.

## Sample Output
============================================================
NETWORK MONITOR (updated 14:32:07)
HOST STATUS LATENCY LAST CHECKED
127.0.0.1 🟢 UP 0.023 ms 2026-09-06 14:32:07
8.8.8.8 🟢 UP 12.4 ms 2026-09-06 14:32:05
google.com 🟢 UP 18.7 ms 2026-09-06 14:32:05
192.168.1.1 🔴 DOWN - 2026-09-06 14:32:01

Full history is being written to: network_monitor.log
Press Ctrl+C to stop monitoring.


## Possible Improvements

- Configuration via an external JSON/YAML file instead of editing source code
- Email/Slack alerts when a host goes down
- Track packet loss percentage across multiple pings per check
- Store history in a database or CSV for graphing uptime trends over time
- Web-based dashboard (e.g., Flask) instead of console output

## License

Free to use and modify for learning or personal projects.
