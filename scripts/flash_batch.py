#!/usr/bin/env python3
"""
esp32-p4 flash-batch - Flash multiple binaries in one atomic operation

Uses esptool's native multi-file write_flash command for reliability.
Reads flash list from ESP-IDF build/flash_args manifest by default.
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
    path_str = os.path.expanduser(path_str)
    path = Path(path_str)
    
    if path.is_absolute():
        return path.resolve()
    
    if str(path).startswith('./'):
        return Path.cwd() / str(path)[2:]
    else:
        return Path.cwd() / path


def get_flash_files_from_manifest(build_dir, full_flash=False):
    """Get ordered list of files to flash from ESP-IDF manifest"""
    flash_args = build_dir / 'flash_args'
    files = []
    
    if not flash_args.exists():
        return []
    
    with open(flash_args) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('--'):
                continue
            
            parts = line.split(maxsplit=1)
            if len(parts) >= 2 and parts[0].startswith('0x'):
                addr = parts[0]
                filepath = parts[1]
                filename = os.path.basename(filepath)
                
                # For app binaries, prefer versioned version
                if not any(x in filename.lower() for x in ['bootloader', 'partition', 'storage']):
                    name_base = filename.replace('.bin', '')
                    versioned = list(build_dir.glob(f"{name_base}-*.bin"))
                    versioned = [f for f in versioned if '-' in f.name and not f.name.startswith('.')]
                    if versioned:
                        versioned.sort(key=lambda f: len(f.name), reverse=True)
                        filename = versioned[0].name
                
                # Determine file category for reset logic
                category = 'app'
                if 'bootloader' in filename.lower():
                    category = 'bootloader'
                elif 'partition' in filename.lower():
                    category = 'partition'
                elif 'storage' in filename.lower():
                    category = 'storage'
                
                files.append({
                    'filename': filename,
                    'addr': addr,
                    'category': category
                })
    
    return files


def scan_for_storage(build_dir):
    """Scan for storage.bin if not in manifest"""
    storage = build_dir / 'storage.bin'
    if storage.exists():
        return {'filename': 'storage.bin', 'addr': '0x910000', 'category': 'storage'}
    return None


async def flash_batch(ws, files, baud=1500000, reset_after=True):
    """Send batch flash command to bridge"""
    
    await ws.send(json.dumps({
        'action': 'flash_batch',
        'files': files,
        'rate': baud,
        'reset_after': reset_after
    }))
    
    file_count = len(files)
    current_file = 0
    current_file_name = None
    
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=180.0)
            data = json.loads(msg)
            
            if data.get('type') == 'output':
                print(f"  {data['data']}", end='')
            
            if data.get('type') == 'flash_batch':
                status = data.get('status')
                
                if status == 'file_start':
                    current_file = data.get('file_num', 0)
                    current_file_name = data.get('file', 'unknown')
                    total = data.get('total', file_count)
                    print(f"\n[{current_file}/{total}] Flashing {current_file_name}...")
                
                elif status == 'progress':
                    pct = data.get('pct', 0)
                    sys.stdout.write(f"\r  Progress: {pct}%")
                    sys.stdout.flush()
                
                elif status == 'file_complete':
                    print(f"\r  ✓ {current_file_name} complete     ")
                
                elif status == 'complete':
                    print(f"\n✓ Batch flash complete ({data.get('time', '?')}s)")
                    if data.get('reset_performed'):
                        print("✓ Device reset")
                    return True
                
                elif status == 'error':
                    failed_file = data.get('file', 'unknown')
                    message = data.get('message', 'Unknown error')
                    print(f"\n✗ Flash failed on {failed_file}: {message}", file=sys.stderr)
                    return False
                    
        except asyncio.TimeoutError:
            print(f"\n✗ Timeout waiting for flash response", file=sys.stderr)
            return False
    
    return True


async def do_flash_batch(files, baud=1500000, reset_after=True):
    """Execute batch flash via WebSocket"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(WSS_URI, ssl=ssl_context, ping_interval=None) as ws:
        print(f"Connected to bridge")
        print(f"Flashing {len(files)} files:")
        for f in files:
            print(f"  {f['filename']:40s} at {f['addr']} ({f.get('category', 'app')})")
        print(f"Baud rate: {baud}")
        print()
        
        return await flash_batch(ws, files, baud, reset_after)


def main():
    parser = argparse.ArgumentParser(
        description='Flash multiple binaries in one atomic operation'
    )
    parser.add_argument('--project', '-p', required=True, 
                       help='Project directory (contains build/ folder)')
    parser.add_argument('--baud', '-b', type=int, default=1500000, 
                       help='Baud rate (default: 1500000)')
    parser.add_argument('--no-reset', action='store_true',
                       help='Skip device reset after all files flashed')
    parser.add_argument('--files', '-f', nargs='+', metavar=('FILE', 'ADDR'),
                       help='Manual file list: file1.bin 0x10000 file2.bin 0x2000...')
    parser.add_argument('--skip-storage', action='store_true',
                       help='Skip storage.bin (useful for quick test cycles)')
    parser.add_argument('--dry-run', '-n', action='store_true',
                       help='Show what would be flashed without flashing')
    args = parser.parse_args()
    
    project_path = resolve_project_path(args.project)
    build_dir = project_path / 'build'
    
    if not build_dir.exists():
        print(f"Error: Build directory not found: {build_dir}", file=sys.stderr)
        sys.exit(1)
    
    files = []
    
    # Manual file list mode
    if args.files:
        if len(args.files) % 2 != 0:
            print("Error: --files requires pairs of (filename address)", file=sys.stderr)
            sys.exit(1)
        
        for i in range(0, len(args.files), 2):
            filename = args.files[i]
            addr = args.files[i + 1]
            category = 'app'
            if 'bootloader' in filename.lower():
                category = 'bootloader'
            elif 'partition' in filename.lower():
                category = 'partition'
            elif 'storage' in filename.lower():
                category = 'storage'
            
            files.append({
                'filename': filename,
                'addr': addr,
                'category': category
            })
    else:
        # Auto mode: read from manifest
        files = get_flash_files_from_manifest(build_dir)
        
        # Add storage.bin if found and not already included
        storage = scan_for_storage(build_dir)
        if storage and not any(f.get('category') == 'storage' for f in files):
            files.append(storage)
    
    # Filter out storage if requested
    if args.skip_storage:
        files = [f for f in files if f.get('category') != 'storage']
    
    if not files:
        print("Error: No files to flash", file=sys.stderr)
        sys.exit(1)
    
    # Dry run: just show what would be flashed
    if args.dry_run:
        print(f"\n=== Flash Plan (dry run) ===")
        print(f"Project: {project_path}")
        print(f"Baud: {args.baud}")
        print(f"Reset after: {not args.no_reset}")
        print(f"\nFiles to flash ({len(files)}):")
        total_size = 0
        for i, f in enumerate(files, 1):
            filepath = build_dir / f['filename']
            # Check subdirectories
            if not filepath.exists():
                for subdir in ['bootloader', 'partition_table']:
                    alt_path = build_dir / subdir / f['filename']
                    if alt_path.exists():
                        filepath = alt_path
                        break
            size = filepath.stat().st_size if filepath.exists() else 0
            total_size += size
            print(f"  {i}. {f['filename']:40s} @ {f['addr']} ({size:,} bytes)")
        print(f"\n  Total: {total_size:,} bytes ({total_size / (1024*1024):.1f} MB)")
        print(f"\n✓ Dry run complete - use without --dry-run to flash")
        return
    
    success = asyncio.run(do_flash_batch(files, baud=args.baud, reset_after=not args.no_reset))
    
    if success:
        print(f"\n✓ Flash batch complete!")
        print(f"Monitor with: esp32-p4 monitor")
    else:
        print(f"\n✗ Flash batch failed", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
