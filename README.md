# ESP32-P4 Skill

A complete workflow tool for ESP32-P4 development with ESP-IDF, featuring container-to-hardware build, flash, and monitor capabilities.

## Overview

The ESP32-P4 skill provides a streamlined workflow for developing on the ESP32-P4 (720×720 MIPI DSI display). It bridges container-based development with hardware flashing via a WebSocket bridge.

**Container (VS Code)** → **Tailscale** → **Bridge (MacBook)** → **USB** → **ESP32-P4**

## Installation

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/studioalight/esp32-p4-skill.git esp32-p4
```

## Quick Start

### 1. Create a New Project

```bash
cd ~/.openclaw/workspace/skills/esp32-p4
./esp32-p4 new-project --name my-display
```

Creates a project at `~/.openclaw/workspace/projects/esp32-p4-projects/my-display/`

### 2. Build, Upload, Flash, Monitor — One Command

```bash
./esp32-p4 iterate --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-display
```

This runs the complete workflow:
1. **Build** — Compiles with ESP-IDF, generates versioned binary
2. **Upload** — Transfers binaries to bridge via HTTP
3. **Flash** — Writes to ESP32-P4 via WebSocket (default: 1500000 baud)
4. **Monitor** — 15 seconds of serial output

**Total time:** ~45 seconds for full cycle

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| `new-project` | Create project from template | `./esp32-p4 new-project --name my-project` |
| `build` | Compile project | `./esp32-p4 build --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project` |
| `upload` | Upload to bridge | `./esp32-p4 upload --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project` |
| `flash` | Flash app binary | `./esp32-p4 flash --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project` |
| `flash --list-files-to-flash` | List available binaries | `./esp32-p4 flash --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project --list-files-to-flash` |
| `iterate` | Full workflow | `./esp32-p4 iterate --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project` |
| `monitor` | Watch serial | `./esp32-p4 monitor --duration 30` |

## Project Structure

```
~/.openclaw/workspace/projects/esp32-p4-projects/my-project/
├── CMakeLists.txt          # Project configuration
├── sdkconfig              # ESP-IDF configuration (auto-generated)
├── main/
│   ├── main.c             # Your application code
│   └── CMakeLists.txt
├── components/
│   └── version/           # Auto-generated version header
│       ├── version.h     # Git commit, build time
│       └── CMakeLists.txt
└── build/
    ├── my-project.bin                 # Standard binary
    ├── my-project-abc123-dirty.bin    # Versioned binary (preferred)
    ├── bootloader/bootloader.bin
    └── partition_table/partition-table.bin
```

## Version Tracking

Builds automatically include version metadata:

**Version Header (auto-generated):**
```c
#define PROJECT_NAME "my-project"
#define GIT_COMMIT "abc123-dirty"
#define BUILD_TIME "2026-03-11 08:15:32"
```

**Serial Output on Boot:**
```
Project: my-project
Commit: abc123-dirty
Built: 2026-03-11 08:15:32
```

## Configuration

### Flash Baud Rate

Default: 1500000 (fast flashing)

```bash
./esp32-p4 flash --full --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project --baud 921600
```

Options: `460800`, `921600`, `1500000`, `2000000`

### Project Location

Default: `~/.openclaw/workspace/projects/esp32-p4-projects/`

Override with `--workspace`:
```bash
./esp32-p4 new-project --name my-project --workspace ~/custom/projects
```

## Serial Output

**USB Serial/JTAG interface outputs at 115200 baud** by default.

Monitor serial:
```bash
./esp32-p4 monitor --duration 30
```

## Chip Compatibility

**Automatic v1.0 Support:**

Early ESP32-P4 samples (revision v1.0) require special configuration. The build script automatically adds:

```
CONFIG_ESP32P4_REV_MIN_100=y
CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y
```

This prevents "bootloader requires chip revision v3.1" errors.

## Troubleshooting

### Flash Fails

**Check bridge is running:**
```bash
curl https://esp32-bridge.tailbdd5a.ts.net:5679/files
```

**Verify binaries uploaded:**
```bash
./esp32-p4 upload --list
```

### Slow Flashing

Default is 1500000 baud (fast). If issues, try lower:
```bash
./esp32-p4 flash --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project --baud 921600
```

### Flash Specific File

```bash
./esp32-p4 flash --project ~/.openclaw/workspace/projects/esp32-p4-projects/my-project \
  --file storage.bin --addr 0x910000
```

### Versioned Binary Not Used

Check both binaries exist:
```bash
ls -la ~/.openclaw/workspace/projects/esp32-p4-projects/my-project/build/*.bin
```

Should see:
- `my-project.bin` (generic)
- `my-project-abc123-dirty.bin` (versioned, preferred)

## Architecture

```
esp32-p4 (main entry)
├── scripts/
│   ├── new_project.py     # Clone template, init git
│   ├── build.py          # Compile with ESP-IDF
│   ├── upload.py         # HTTP upload to bridge
│   ├── flash.py          # WebSocket flash to hardware
│   ├── monitor.py        # Serial monitoring
│   └── iterate.py        # Full workflow orchestration
└── config/
    └── esp32-p4.yaml     # Bridge URL, defaults
```

## Development

**Template Repository:**
https://github.com/studioalight/esp32-p4-display-template

**Skill Repository:**
https://github.com/studioalight/esp32-p4-skill

**Bridge Repository:**
https://github.com/studioalight/esp32-bridge

The bridge runs on your MacBook and provides WebSocket/HTTP endpoints for flashing and monitoring ESP32 devices over USB Serial/JTAG.

## Requirements

- ESP-IDF 5.4+ installed at `~/esp-idf-v5.4`
- **Bridge running on MacBook** (`esp32-bridge.py` from [esp32-bridge repo](https://github.com/studioalight/esp32-bridge))
  - WebSocket server at `wss://esp32-bridge.tailbdd5a.ts.net:5678`
  - HTTP upload at `https://esp32-bridge.tailbdd5a.ts.net:5679`
  - Requires ESP32-P4 connected via USB Serial/JTAG
- Python 3.9+
- Dependencies: `websockets`, `aiohttp`

## License

Part of the Studio Alight collective.

---

*"The Marshmallow Stands" — iterate incrementally, build on solid foundation.* 🍡
