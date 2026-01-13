# Protek 506 Digital Multimeter Data Logger

## This is a cross-platform (macOS, Linux, Windows) Python program to read, display, and log data from a Protek 506 Digital Multimeter

## Current Release

* Initial Stable Release v1.0.0

## Description

This Python program logs data from the Protek 506 DMM via its RS-232 interface (1200 baud, 7N2). Supports both USB-to-serial adapters and native physical serial ports (e.g., COM1–COM9 on Windows).

## Key Features

* Attempts to auto-detect the USB-to-serial adapter connected to the Protek 506 DMM
* Upin detection, starts polling, displaying, and logging the readings
* Optional command-line options to:
  * Manually serial port override (e.g., COM3, /dev/ttyUSB0)
  * Change output filename (default: Protek-506-log.txt)
  * Change polling interval in seconds (default: 0.2)
  * Show program's version number and then exit
* Robust parsing tuned to real output (preserves leading zeros, handles OL/OPEN/SHORT,
  logic level High/Low/----, overload variants)
* CSV with header added only on new/empty file
* Columns: date, time, mode (short), reading, units
