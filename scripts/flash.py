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

async def flash_file(ws, filename, address, progress=True):
    """Flash single file"""
    print(f"\nFlashing {filename} at {address}...")
    
    await ws.send(json.dumps({
        'action': 'flash',
        'file': filename,
        'addr': address
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

async def flash_files(files_to_flash, reset_after=True):
    """Flash multiple files"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(WSS_URI, ssl=ssl_context, ping_interval=None) as ws:
        print(f"Connected to bridge\n")
        
        # Enter bootloader before first flash
        await ws.send(json.dumps({'action': 'bootloader'}))
        await asyncio.sleep(2)
        
        success = True
        for filename, address in files_to_flash:
            if not await flash_file(ws, filename, address):
                success = False
                break
            await asyncio.sleep(0.5)
        
        if reset_after and success:
            print("\nResetting device...")
            await ws.send(json.dumps({'action': 'reset'}))
            await asyncio.sleep(1)
            print("✓ Device reset")
        
        return success

def main():
    parser = argparse.ArgumentParser(description='Flash binaries via bridge')
    parser.add_argument('--full', action='store_true', help='Flash all: bootloader, partition, app')
    parser.add_argument('--app', action='store_true', help='Flash only application')
    parser.add_argument('--bootloader', action='store_true', help='Flash only bootloader')
    parser.add_argument('--partition', action='store_true', help='Flash only partition table')
    parser.add_argument('--file', help='Custom file to flash')
    parser.add_argument('--addr', help='Address for custom file')
    parser.add_argument('--project', '-p', help='Project directory (for auto-discovering versioned binary)')
    args = parser.parse_args()
    
    # Determine what to flash
    if args.full:
        # Get app binary name, with auto-discovery if project provided
        if args.project:
            project_path = resolve_project_path(args.project)
            build_dir = project_path / 'build'
            # Find all .bin files directly in build/, not in subdirs
            bin_files = list(build_dir.glob('*.bin'))
            app_bins = [f for f in bin_files 
                        if f.name not in ['bootloader.bin', 'partition-table.bin']]
            
            if app_bins:
                app_bins.sort(key=lambda f: f.stat().st_size, reverse=True)
                app_name = app_bins[0].name
                print(f"Found versioned binary for full flash: {app_name}")
            else:
                app_name = 'app.bin'
        else:
            app_name = 'app.bin'
        
        files = [
            ('bootloader.bin', FLASH_ADDRESSES['bootloader']),
            ('partition-table.bin', FLASH_ADDRESSES['partition']),
            (app_name, FLASH_ADDRESSES['app'])
        ]
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
                # Sort by size, largest is likely the app
                app_bins.sort(key=lambda f: f.stat().st_size, reverse=True)
                versioned = app_bins[0].name
                files = [(versioned, FLASH_ADDRESSES['app'])]
                print(f"Found versioned binary: {versioned}")
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
    
    success = asyncio.run(flash_files(files))
    
    if success:
        print("\n✓ Flash complete!")
        print("Monitor with: esp32-p4 monitor")
    else:
        print("\n✗ Flash failed", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
