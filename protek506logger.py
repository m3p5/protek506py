"""
Protek 506 Digital Multimeter Data Logger
Cross-platform version (macOS, Linux, Windows)

This script logs data from the Protek 506 DMM via its RS-232 interface
(1200 baud, 7N2). Supports both USB-to-serial adapters and native
physical serial ports (e.g., COM1–COM9 on Windows).

Key features:
- Optional command-line options:
  -p, --port     : Manual serial port override (e.g., COM3, /dev/ttyUSB0)
  -f, --file     : Output CSV filename (default: Protek-506-log.txt)
  -d, --delay    : Polling interval in seconds (default: 0.2)
  -v, --version  : Show program's version number and exit
- Robust parsing tuned to real output (preserves leading zeros, handles OL/OPEN/SHORT,
  logic level High/Low/----, overload variants)
- CSV with header added only on new/empty file
- Columns: date, time, mode (short), reading, units

Note for physical RS-232 ports on Microsoft Windows:
- Direct connection to the Protek 506's DB-9 port typically requires a
  null-modem (crossover) cable (Tx/Rx swapped). Straight-through cables may not work.
- Physical ports appear as COM1, COM2, etc., just like USB adapters.

Requirements:
    pip install pyserial

Ctrl+C to stop logging and exit the program.
"""

import serial
import serial.tools.list_ports
import signal
import datetime
import time
import sys
import csv
import re
import argparse
import os

# Program version
VERSION = "1.0.0"

# ==================== CUSTOMIZABLE TIMESTAMP FORMATS ====================
DATE_FORMAT = "%Y-%m-%d"                   # CSV 'date' column
TIME_FORMAT = "%H:%M:%S.%f"                 # CSV 'time' column and console (ms)
# =======================================================================

# Short mode names matching observed output
MODE_MAP = {
    'A': 'AC',
    'B': 'DIO',    # Continuity/buzzer (if seen)
    'C': 'CAP',
    'D': 'DC',
    'F': 'FR',
    'I': 'IND',
    'L': 'DIO',    # Diode/continuity/logic
    'R': 'RES',
    'T': 'TEMP',
}

# Command-line arguments with short options
parser = argparse.ArgumentParser(
    description="Protek 506 serial logger"
)
parser.add_argument(
    '-p', '--port',
    type=str,
    help="Manual serial port override (e.g., COM3, /dev/ttyUSB0)"
)
parser.add_argument(
    '-f', '--file',
    type=str,
    default="Protek-506-log.txt",
    help="Output CSV filename (default: Protek-506-log.txt)"
)
parser.add_argument(
    '-d', '--delay',
    type=float,
    default=0.2,
    help="Polling delay in seconds (default: 0.2)"
)
parser.add_argument(
    '-v', '--version',
    action='store_true',
    help="Show program's version number and exit"
)
args = parser.parse_args()

# If --version/-v is specified, print version and quit
if args.version:
    print(VERSION)
    sys.exit(0)

# Input validation for arguments
if args.delay <= 0:
    parser.error("--delay must be a positive number greater than 0")

if args.file:
    dir_path = os.path.dirname(os.path.abspath(args.file))
    if not os.path.exists(dir_path):
        parser.error(f"Directory for --file '{args.file}' does not exist: {dir_path}")
    # Test writability by attempting to open in append mode
    try:
        with open(args.file, 'a') as test_file:
            pass
    except Exception as e:
        parser.error(f"Cannot write to --file '{args.file}': {e}")

def find_protek_port():
    ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)
    
    candidates = []
    
    for p in ports:
        device_lower = p.device.lower()
        if ('usb' in device_lower or 
            'acm' in device_lower or 
            'serial' in device_lower or 
            device_lower.startswith('com')):
            if (p.manufacturer and 'FTDI' in p.manufacturer) or \
               (p.description and 'FTDI' in p.description):
                candidates.insert(0, p)  # FTDI first
            else:
                candidates.append(p)
    
    if not candidates:
        print("No USB/serial port detected. Available ports:")
        for p in ports:
            print(f"  {p.device} - {p.description} ({p.manufacturer or 'Unknown'})")
        sys.exit("Plug in the adapter (or use -p/--port to specify manually) and rerun.")
    
    selected = candidates[0]
    print(f"Auto-selected port: {selected.device}")
    print(f"  Description: {selected.description}")
    print(f"  Manufacturer: {selected.manufacturer or 'Unknown'}")
    
    if len(candidates) > 1:
        print("\nOther candidate ports (ignored):")
        for p in candidates[1:]:
            print(f"  {p.device} - {p.description} ({p.manufacturer or 'Unknown'})")
    
    return selected.device

# Determine port: manual override first, then auto-detect
if args.port:
    port = args.port
    # Validate manual port: check if it exists in available ports
    available_ports = [p.device for p in serial.tools.list_ports.comports()]
    if port not in available_ports:
        parser.error(f"Specified --port '{port}' not found. Available ports: {', '.join(available_ports)}")
    print(f"Using manually specified port: {port}")
else:
    port = find_protek_port()

# Open serial connection
ser = serial.Serial(
    port=port,
    baudrate=1200,
    bytesize=7,
    stopbits=2,
    parity='N',
    timeout=1.0,
    exclusive=True
)

# Set delay from args
delay = args.delay

# Ctrl+C handler
def signal_handler(sig, frame):
    print("\nCtrl+C pressed - closing port and exiting...")
    if ser.is_open:
        ser.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Function to read data from serial (improved from old snippet)
def read_data_from_serial(ser):
    ser.write(b'\n')  # Send trigger once, outside the loop
    line = ser.read_until(b'\r')  # Efficient read until terminator
    if not line or line[-1] != ord('\r'):
        return None  # Timeout or incomplete
    data = line[:-1].decode('ascii', errors='ignore').strip()
    return data

print("\nPort open. Ensure RS-232 mode is enabled on the meter.")
print(f"Logging to: {args.file}")
print("Started — press Ctrl+C to stop.\n")

# Open log file with header logic
with open(args.file, 'a', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    
    # Only write header if file is empty
    csvfile.seek(0, 2)
    if csvfile.tell() == 0:
        writer.writerow(['date', 'time', 'mode', 'reading', 'units'])
    
    first_byte_chars = set(MODE_MAP.keys())
    
    # Updated regex: includes logic levels (High/Low/----) per manual
    reading_pattern = re.compile(
        r'([\-+]?[0-9]*\.?[0-9]+[kmuz]?|\.OL|-OL|OL|OPEN|SHORT|High|Low|----)',
        re.IGNORECASE
    )
    
    try:
        while True:
            data = read_data_from_serial(ser)
            if data is None:
                time.sleep(delay)
                continue
            
            if not data or data[0] not in first_byte_chars:
                time.sleep(delay)
                continue
            
            now = datetime.datetime.now()
            
            date_str = now.strftime(DATE_FORMAT)
            time_str = now.strftime(TIME_FORMAT)[:-3]  # ms precision
            
            # Live view on console
            console_line = f"{time_str} {data}"
            print(console_line)
            
            mode_code = data[0]
            mode = MODE_MAP.get(mode_code, 'UNKNOWN')
            
            rest = data[1:].strip()
            
            match = reading_pattern.search(rest)
            if match:
                reading = match.group(1)
                units_start = match.end()
                units = rest[units_start:].strip()
            else:
                reading = ''
                units = rest.strip()
            
            # Fix mangled degree symbol if present
            if '^C' in units:
                units = units.replace('^C', '°C')
            
            # Write structured row
            writer.writerow([date_str, time_str, mode, reading, units])
            csvfile.flush()
            
            time.sleep(delay)
            
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        # Explicit cleanup
        if ser.is_open:
            ser.close()