#!/usr/bin/env python3
"""
esp32-p4 flash - Flash binaries via bridge WebSocket
"""

import asyncio
import websockets
import json
import ssl
import argparse
import sys
import os
from pathlib import Path

WSS_URI = "wss://esp32-bridge.tailbdd5a.ts.net:5678"

# Get OpenClaw workspace root
OPENCLAW_WORKSPACE = Path(os.environ.get('OPENCLAW_WORKSPACE', os.path.expanduser('~/.openclaw/workspace')))

def resolve_project_path(path_str):
    """Resolve project path - handle relative paths"""
    path = Path(path_str)
    if not path.is_absolute():
        if str(path).startswith('./'):
            # ./projects/... means relative to current directory
            return Path.cwd() / str(path)[2:]
        else:
            # Relative without ./ - also relative to current directory
            return Path.cwd() / path
    return path.expanduser().resolve()

FLASH_ADDRESSES = {
    'bootloader': '0x2000',
    'partition': '0x8000',
    'app': '0x10000'
}

async def flash_file(ws, filename, address, baud=921600, progress=True):
    """Flash single file"""
    print(f"\nFlashing {filename} at {address}...")
    print(f"  [DEBUG] esptool equivalent: esptool.py --baud {baud} --port /dev/cu.usbmodem* write_flash {address} {filename}")
    
    await ws.send(json.dumps({
        'action': 'flash',
        'file': filename,
        'addr': address,
        'rate': baud  # Bridge expects 'rate', not 'baud'
    }))
    
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=60)
            data = json.loads(msg)
            
            if data.get('type') == 'flash':
                if data.get('status') == 'complete':
                    print(f"  ✓ {filename} complete")
                    return True
                elif data.get('status') == 'error':
                    print(f"  ✗ {filename} error: {data}", file=sys.stderr)
                    return False
                elif data.get('status') == 'progress' and progress:
                    pct = data.get('pct', 0)
                    print(f"  Progress: {pct}%", end='\r')
                elif data.get('status') == 'output':
                    if progress:
                        print(f"  {data.get('line', '')[:80]}")
                    
        except asyncio.TimeoutError:
            print("  ✗ Timeout", file=sys.stderr)
            return False

async def flash_files(files_to_flash, baud=921600, reset_after=True):
    """Flash multiple files"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(WSS_URI, ssl=ssl_context, ping_interval=None) as ws:
        print(f"Connected to bridge\n")
        print(f"Using baud rate: {baud}")
        
        # Enter bootloader before first flash
        await ws.send(json.dumps({'action': 'bootloader'}))
        await asyncio.sleep(2)
        
        success = True
        for filename, address in files_to_flash:
            if not await flash_file(ws, filename, address, baud=baud):
                success = False
                break
            await asyncio.sleep(0.5)
        
        if reset_after and success:
            print("\nResetting device...")
            await ws.send(json.dumps({'action': 'reset'}))
            await asyncio.sleep(1)
            print("✓ Device reset")
        
        return success

def get_flash_files_from_build(build_dir, project_name):
    """Get list of files to flash from ESP-IDF build output"""
    # Check for flasher_args.json (ESP-IDF generated manifest)
    flasher_args = build_dir / 'flash_args'
    flasher_json = build_dir / 'flasher_args.json'
    
    files_to_flash = []
    
    # Try flash_args file (ESP-IDF format: 0xADDR path/to/file.bin)
    if flasher_args.exists():
        print("Found flash_args manifest")
        with open(flasher_args) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Parse "0x2000 bootloader/bootloader.bin" format
                parts = line.split(maxsplit=1)
                if len(parts) >= 2 and parts[0].startswith('0x'):
                    addr = parts[0]
                    filepath = parts[1]
                    filename = os.path.basename(filepath)
                    files_to_flash.append((filename, addr))
                    print(f"  Found: {filename} at {addr}")
    
    # Fallback to flasher_args.json
    elif flasher_json.exists():
        print("Found flasher_args.json manifest")
        import json
        with open(flasher_json) as f:
            data = json.load(f)
            for entry in data.get('flash_files', []):
                filename = os.path.basename(entry['path'])
                files_to_flash.append((filename, entry['offset']))
    
    # Final fallback: scan for known patterns
    else:
        print("No flash manifest found, using pattern matching...")
        bin_files = list(build_dir.glob('*.bin'))
        
        # Known partition types and their addresses
        for bin_file in bin_files:
            name = bin_file.name.lower()
            if 'bootloader' in name:
                files_to_flash.append((bin_file.name, FLASH_ADDRESSES['bootloader']))
            elif 'partition_table' in name or 'partition-table' in name:
                files_to_flash.append((bin_file.name, FLASH_ADDRESSES['partition']))
            elif 'storage' in name:
                # Storage partition typically at 0x110000
                files_to_flash.append((bin_file.name, '0x110000'))
            elif 'ota' in name:
                # OTA data at 0xe000
                files_to_flash.append((bin_file.name, '0xe000'))
        
        # Application binary (prefer versioned)
        app_bins = [f for f in bin_files 
                   if f.name not in ['bootloader.bin', 'partition-table.bin'] 
                   and not any(x in f.name.lower() for x in ['storage', 'ota'])]
        if app_bins:
            versioned_bins = [f for f in app_bins if '-' in f.name]
            if versioned_bins:
                versioned_bins.sort(key=lambda f: len(f.name), reverse=True)
                files_to_flash.append((versioned_bins[0].name, FLASH_ADDRESSES['app']))
            else:
                app_bins.sort(key=lambda f: f.stat().st_size, reverse=True)
                files_to_flash.append((app_bins[0].name, FLASH_ADDRESSES['app']))
    
    return files_to_flash

# Then in main(), replace the hardcoded files list for --full:
def main():
    parser = argparse.ArgumentParser(description='Flash binaries via bridge')
    parser.add_argument('--full', action='store_true', help='Flash all: bootloader, partition, app')
    parser.add_argument('--app', action='store_true', help='Flash only application')
    parser.add_argument('--bootloader', action='store_true', help='Flash only bootloader')
    parser.add_argument('--partition', action='store_true', help='Flash only partition table')
    parser.add_argument('--file', help='Custom file to flash')
    parser.add_argument('--addr', help='Address for custom file')
    parser.add_argument('--project', '-p', help='Project directory (for auto-discovering versioned binary)')
    parser.add_argument('--baud', '-b', type=int, default=921600, 
                        help='Flash baud rate (default: 921600, try 1500000 for faster flashing)')
    args = parser.parse_args()
    
    # Determine what to flash
    if args.full:
        # Use ground truth from ESP-IDF build output
        if args.project:
            project_path = resolve_project_path(args.project)
            build_dir = project_path / 'build'
            files = get_flash_files_from_build(build_dir, "project")
            if not files:
                print("Warning: No flash files found in build directory, using defaults")
                files = [
                    ('bootloader.bin', FLASH_ADDRESSES['bootloader']),
                    ('partition-table.bin', FLASH_ADDRESSES['partition']),
                    ('app.bin', FLASH_ADDRESSES['app'])
                ]
        else:
            # Fallback to defaults
            files = [
                ('bootloader.bin', FLASH_ADDRESSES['bootloader']),
                ('partition-table.bin', FLASH_ADDRESSES['partition']),
                ('app.bin', FLASH_ADDRESSES['app'])
            ]
        
        print(f"Will flash {len(files)} file(s):")
        for fname, addr in files:
            print(f"  {fname} at {addr}")
    elif args.app:
        # Discover versioned binaries in project
        if args.project:
            project_path = resolve_project_path(args.project)
            build_dir = project_path / 'build'
            # List only .bin files directly in build/, not in subdirs
            bin_files = list(build_dir.glob('*.bin'))
            app_bins = [f for f in bin_files
                        if f.name not in ['bootloader.bin', 'partition-table.bin']]
            
            if app_bins:
                # Prefer versioned binary (has git hash in name) over plain binary
                versioned_bins = [f for f in app_bins if '-' in f.name]
                if versioned_bins:
                    versioned_bins.sort(key=lambda f: len(f.name), reverse=True)
                    versioned = versioned_bins[0].name
                    files = [(versioned, FLASH_ADDRESSES['app'])]
                    print(f"Found versioned binary: {versioned}")
                else:
                    app_bins.sort(key=lambda f: f.stat().st_size, reverse=True)
                    versioned = app_bins[0].name
                    files = [(versioned, FLASH_ADDRESSES['app'])]
                    print(f"Found binary: {versioned}")
            else:
                files = [('app.bin', FLASH_ADDRESSES['app'])]
        else:
            files = [('app.bin', FLASH_ADDRESSES['app'])]
    elif args.bootloader:
        files = [('bootloader.bin', FLASH_ADDRESSES['bootloader'])]
    elif args.partition:
        files = [('partition-table.bin', FLASH_ADDRESSES['partition'])]
    elif args.file and args.addr:
        files = [(args.file, args.addr)]
    else:
        # Default to full flash
        files = [
            ('bootloader.bin', FLASH_ADDRESSES['bootloader']),
            ('partition-table.bin', FLASH_ADDRESSES['partition']),
            ('app.bin', FLASH_ADDRESSES['app'])
        ]
    
    print("ESP32-P4 Flash")
    print(f"Bridge: {WSS_URI}")
    print(f"Files: {len(files)}")
    print(f"Baud rate: {args.baud}")
    
    success = asyncio.run(flash_files(files, baud=args.baud))
    
    if success:
        print("\n✓ Flash complete!")
        print("Monitor with: esp32-p4 monitor")
    else:
        print("\n✗ Flash failed", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
