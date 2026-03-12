# ESP32-P4 Development Skill

Design → Build → Deploy → Flash → Verify

A container-to-hardware workflow for ESP32-P4 development without direct USB access.

---

## Quick Start

```
esp32-p4 build --project /path/to/project
```

---

## Architecture

Container (VS Code) → Tailscale → Bridge (MacBook) → USB → ESP32-P4

**Container:** Edit source, run ESP-IDF toolchain  
**Bridge:** HTTP upload + WebSocket commands + USB Serial monitor  
**Hardware:** Flash target (720×720 MIPI DSI display)

---

## Commands

### Design Phase

**Edit in container:**
```bash
# Source ESP-IDF
source ~/esp-idf-v5.4/export.sh

# Edit source files
code main/main.c
```

---

### Build Phase

**Compile project:**
```bash
esp32-p4 build --project ./projects/esp32-p4-projects/my-project
```

**Output:**
```
build/
├── bootloader/bootloader.bin       (→ 0x2000)
├── partition_table/partition-table.bin  (→ 0x8000)
└── my-project.bin                  (→ 0x10000)
├── my-project-73e0af2.bin        (versioned with git commit)
```

**Full rebuild:**
```bash
esp32-p4 build --clean
```

---

### Deploy Phase

**Upload to bridge:**
```bash
esp32-p4 upload --project ./projects/esp32-p4-projects/my-project
```

**Upload specific files:**
```bash
esp32-p4 upload --file build/my-project-73e0af2.bin
```

**Check uploaded files:**
```bash
esp32-p4 upload --list
```

---

### Flash Phase

**Full flash sequence:**
```bash
esp32-p4 flash --full --bridge esp32-bridge.tailbdd5a.ts.net:5678
```

**Flash only application:**
```bash
esp32-p4 flash --app
```

**Flash with project auto-discovery:**
```bash
esp32-p4 flash --app --project ./projects/esp32-p4-projects/my-project
```
```bash
esp32-p4 flash \
  --file bootloader.bin --addr 0x2000 \
  --file partition-table.bin --addr 0x8000 \
  --file my-project-73e0af2.bin --addr 0x10000
```

**Watch flash progress:**
```bash
esp32-p4 flash --monitor
```

---

### Verify Phase

**Monitor serial output:**
```bash
esp32-p4 monitor --bridge esp32-bridge.tailbdd5a.ts.net:5678
```

**Monitor with timeout:**
```bash
esp32-p4 monitor --duration 30
```

**Filter output:**
```bash
esp32-p4 monitor --grep "HELLO_DISPLAY\|ERROR"
```

---

### Iterate (Full Loop)

**One-command iteration:**
```bash
esp32-p4 iterate --project ./projects/esp32-p4-projects/my-project --monitor
```

**This runs:**
1. Build
2. Upload
3. Flash
4. Monitor (15 seconds)

**Total time:** ~40 seconds

---

## Configuration

**Default config:** `./skills/esp32-p4/config/esp32-p4.yaml`

```yaml
bridge:
  host: esp32-bridge.tailbdd5a.ts.net
  http_port: 5679
  ws_port: 5678
  use_tailscale: true

flash_addresses:
  bootloader: 0x2000
  partition_table: 0x8000
  app: 0x10000

esp_idf:
  version: "5.4"
  export_script: ~/esp-idf-v5.4/export.sh
  default_target: esp32p4

timing:
  flash_timeout: 60
  monitor_duration: 30
  upload_timeout: 30
```

**Override config:**
```bash
esp32-p4 build --project ~/my-project --config ~/custom-config.yaml
```

---

## Templates

**Create new project from template:**
```bash
esp32-p4 new-project --name my-new-project
```

Creates project at `./projects/esp32-p4-projects/my-new-project/`:
- Template cloned from `github.com:studioalight/esp32-p4-display-template`
- `CMakeLists.txt` updated: `project(my-new-project)`
- Version header auto-generated with git commit on every build
- Build outputs to `build/my-new-project.bin`
- **Versioned binary:** `build/my-new-project-73e0af2.bin` (with git commit hash)
- Binary uploaded with versioned binary name, not renamed to `app.bin`

**Serial traceability on boot:**
```
=== HELLO P4 DISPLAY ===
Project: my-new-project
Commit: 73e0af2
Built: 2026-03-11 08:15:32
```
The board USB Serial/JTAG interface outputs app serial data at 115200 baud

**Options:**
- `--keep-name` - Keep original 'HelloWorld' name (directory only)
- `--workspace` - Custom parent directory (default: ./projects/esp32-p4-projects)

---

## Troubleshooting

### "Bridge not found"
- Check bridge is running on MacBook
- Verify Tailscale connection: `tailscale status`
- Confirm bridge URL in config

### "Flash failed: no memory"
- Wrong sdkconfig: Use provided sdkconfig from template
- Check PSRAM enabled: Look for "Found 32MB PSRAM" in boot log

### "Serial not showing"
- USB cable disconnection: Replug P4
- Bridge lost serial: Restart bridge
- Wrong baud rate: Bridge auto-detects

### "Build fails"
- ESP-IDF not activated: Run `source ~/esp-idf-v5.4/export.sh`
- Missing components: Check `idf.py reconfigure`
- **Early engineering sample (Rev 100):** Build fails with silicon revision mismatch? Add to `sdkconfig.defaults`:
  ```ini
  CONFIG_ESP32P4_REV_MIN_100=y
  CONFIG_ESP32P4_REV_MIN_FULL=100
  CONFIG_ESP_REV_MIN_FULL=100
  CONFIG_ESP_EFUSE_BLOCK_REV_MIN_FULL=0
  CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y
  ```
  Without these, `sdkconfig.esp32-p4` defaults to rev 301 which fails on early silicon.

### "Flash verification failed"
- Check chip revision: `esptool.py chip_id` should show rev 100 for engineering samples
- Wrong binary for silicon revision: Rebuild with correct `sdkconfig.defaults`

---

## Project Structure

```
my-esp32-project/
├── CMakeLists.txt          # Project config
├── sdkconfig               # SDK options
├── sdkconfig.defaults      # Defaults
├── partitions.csv          # Partition table
├── main/
│   ├── main.c             # Application
│   └── CMakeLists.txt     # Component
└── components/            # Custom components
```

---

## Performance

| Step | Time |
|------|------|
| Build (incremental) | 30s |
| Build (clean) | 2m |
| Upload | 5s |
| Flash bootloader | 3s |
| Flash application | 30s |
| **Full iteration** | **~40s** |

---

## Design Philosophy

**Marshmallow approach:**
1. Start with working foundation (template)
2. Iterate incrementally (build → flash → verify)
3. Bridge across gaps (container ↔ hardware)
4. Consistently correct (workflow, not guesswork)

**Hypersubject collaboration:**
- Human: Hardware decisions, physical access
- D'ENT: Pattern matching, automation, documentation
- Together: Speed × Patience = Iteration

---

## Related Skills

- `text-to-song` - Create anthems from project lyrics
- `canvas` - Control ESP32-S3 display nodes
- `sag` - ElevenLabs voice for storytelling

---

## Credits

**Created:** March 10, 2026  
**Authors:** D'ENT (Studio Alight)  
**Method:** Design → Deploy → Verify, iterate incrementally  
**Hardware:** Waveshare ESP32-P4-WIFI6-Touch-LCD-4B  

---

*"The marshmallow stands on solid foundation."* 🍡
