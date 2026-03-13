#!/usr/bin/env python3
"""
esp32-p4 flash - Flash binaries via bridge WebSocket

Simple, reliable flashing with ground truth from ESP-IDF build output.
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

def resolve_project_path(path_str):
    """Resolve project path - handle relative paths and tilde expansion"""
    # Expand tilde first
    path_str = os.path.expanduser(path_str)
    path = Path(path_str)
    
    if path.is_absolute():
        return path.resolve()
    
    if str(path).startswith('./'):
        return Path.cwd() / str(path)[2:]
    else:
        return Path.cwd() / path

def get_build_files(build_dir, list_only=False):
    """Get list of flashable files from ESP-IDF build output"""
    flash_args = build_dir / 'flash_args'
    files = []
    
    if flash_args.exists():
        with open(flash_args) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) >= 2 and parts[0].startswith('0x'):
                    addr = parts[0]
                    filepath = parts[1]
                    filename = os.path.basename(filepath)
                    
                    # For app binaries, prefer versioned version
                    if not any(x in filename.lower() for x in ['bootloader', 'partition']):
                        name_base = filename.replace('.bin', '')
                        versioned = list(build_dir.glob(f"{name_base}-*.bin"))
                        versioned = [f for f in versioned if '-' in f.name and not f.name.startswith('.')]
                        if versioned:
                            versioned.sort(key=lambda f: len(f.name), reverse=True)
                            filename = versioned[0].name
                    
                    files.append((filename, addr))
    
    # Also scan for any .bin files in build dir
    for bin_file in sorted(build_dir.glob('*.bin')):
        if bin_file.name not in [f[0] for f in files]:  # Skip if already in list
            # Try to determine address from filename
            if 'bootloader' in bin_file.name.lower():
                files.append((bin_file.name, '0x2000'))
            elif 'partition' in bin_file.name.lower():
                files.append((bin_file.name, '0x8000'))
            elif 'storage' in bin_file.name.lower():
                files.append((bin_file.name, '0x910000'))
            else:
                files.append((bin_file.name, '0x10000'))  # Default app address
    
    if list_only:
        return files
    
    # Return just the app binary for default flash
    app_files = [f for f in files if f[0].endswith('.bin') and not any(x in f[0].lower() for x in ['bootloader', 'partition', 'storage'])]
    return app_files[:1] if app_files else files[:1] if files else []

async def flash_file(ws, filename, address, baud=1500000):
    """Flash single file"""
    print(f"\nFlashing {filename} at {address}...")
    
    await ws.send(json.dumps({
        'action': 'flash',
        'file': filename,
        'addr': address,
        'rate': baud
    }))
    
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=120.0)
            data = json.loads(msg)
            
            if data.get('type') == 'output':
                print(f"  {data['data']}", end='')
            
            if data.get('type') == 'flash':
                status = data.get('status')
                if status == 'complete':
                    print(f"✓ {filename} complete")
                    return True
                elif status == 'error':
                    print(f"✗ Flash failed: {data.get('message')}", file=sys.stderr)
                    return False
                    
        except asyncio.TimeoutError:
            print(f"✗ Timeout", file=sys.stderr)
            return False
    
    return True

async def do_flash(files, baud=921600, reset_after=True):
    """Flash files"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(WSS_URI, ssl=ssl_context, ping_interval=None) as ws:
        print(f"Connected to bridge\n")
        
        # Enter bootloader
        await ws.send(json.dumps({'action': 'bootloader', 'enter_bootloader': True}))
        await asyncio.sleep(2)
        
        success = True
        for filename, address in files:
            if not await flash_file(ws, filename, address, baud):
                success = False
                break
            # Longer delay to let bridge finish verify/reset
            await asyncio.sleep(3.0)
        
        if reset_after and success:
            print("\nResetting device...")
            await ws.send(json.dumps({'reset': True}))
            await asyncio.sleep(1)
            print("✓ Device reset")
        
        return success

def main():
    parser = argparse.ArgumentParser(description='Flash binaries via bridge')
    parser.add_argument('--project', '-p', required=True, help='Project directory')
    parser.add_argument('--file', '-f', help='Specific file to flash')
    parser.add_argument('--addr', '-a', help='Address for specific file')
    parser.add_argument('--baud', '-b', type=int, default=3000000, help='Baud rate (default: 3000000, ESP32-P4 native USB max stable)')
    parser.add_argument('--list-files-to-flash', '-l', action='store_true', help='List available binaries without flashing')
    parser.add_argument('--no-reset', action='store_true', help='Skip device reset after flash')
    args = parser.parse_args()
    
    project_path = resolve_project_path(args.project)
    build_dir = project_path / 'build'
    
    if not build_dir.exists():
        print(f"Error: Build directory not found: {build_dir}", file=sys.stderr)
        sys.exit(1)
    
    if args.list_files_to_flash:
        print(f"Flashable files in {build_dir}:")
        files = get_build_files(build_dir, list_only=True)
        for filename, addr in files:
            file_path = build_dir / filename
            if not file_path.exists():
                # Check subdirectories
                for subdir in ['bootloader', 'partition_table']:
                    alt_path = build_dir / subdir / filename
                    if alt_path.exists():
                        file_path = alt_path
                        break
            size = file_path.stat().st_size if file_path.exists() else 0
            print(f"  {filename:40s} at {addr:10s} ({size:,} bytes)")
        return
    
    # Determine what to flash
    if args.file:
        # Flash specific file
        if not args.addr:
            print("Error: --addr required with --file", file=sys.stderr)
            sys.exit(1)
        files = [(args.file, args.addr)]
    else:
        # Flash app binary (default)
        files = get_build_files(build_dir)
        if not files:
            print("Error: No app binary found in build directory", file=sys.stderr)
            sys.exit(1)
    
    print(f"ESP32-P4 Flash")
    print(f"Files: {len(files)}")
    for filename, addr in files:
        print(f"  {filename} at {addr}")
    print(f"Baud rate: {args.baud}")
    print()
    
    success = asyncio.run(do_flash(files, baud=args.baud, reset_after=not args.no_reset))
    
    if success:
        print("\n✓ Flash complete!")
        print(f"Monitor with: esp32-p4 monitor")
    else:
        print("\n✗ Flash failed", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
