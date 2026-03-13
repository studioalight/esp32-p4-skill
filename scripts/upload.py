#!/usr/bin/env python3
"""
esp32-p4 upload - Upload binaries to bridge via HTTP

Auto-discovers bridge's Tailscale IP via WebSocket for faster direct connection.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
import json
import asyncio
import websockets
import ssl

BRIDGE_URL = "https://esp32-bridge.tailbdd5a.ts.net:5679"
BRIDGE_WS = "wss://esp32-bridge.tailbdd5a.ts.net:5678"

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

async def discover_bridge_ip():
    """Connect via WebSocket and discover IPs for faster uploads
    
    Priority: local LAN IP > Tailscale IP > None (use service)
    """
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        async with websockets.connect(BRIDGE_WS, ssl=ssl_context, ping_interval=None) as ws:
            # Request status
            await ws.send(json.dumps({'action': 'status'}))
            
            # Wait for response with 5 second timeout
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                
                if data.get('type') == 'status':
                    # Prefer local LAN IP (same network, no Tailscale overhead)
                    local_ip = data.get('local_ip')
                    if local_ip:
                        return f"http://{local_ip}:5679", 'local'
                    
                    # Fall back to Tailscale IP
                    ts_ip = data.get('tailscale_ip')
                    if ts_ip:
                        return f"http://{ts_ip}:5679", 'tailscale'
            except asyncio.TimeoutError:
                pass
    except Exception as e:
        print(f"  [IP discovery fail: {e}]", file=sys.stderr) 
        
    return None, None

def get_bridge_url():
    """Get bridge URL - try to use cached/direct IP first"""
    cache_file = Path.home() / '.esp32-bridge' / 'direct_endpoint'
    
    # Try cached endpoint from previous discovery
    if cache_file.exists():
        try:
            cached = cache_file.read_text().strip()
            if cached:
                url, ip_type = cached.split('|') if '|' in cached else (cached, 'unknown')
                # Quick test if it's reachable
                result = subprocess.run(
                    ['curl', '-k', '-s', '--max-time', '2', f'{url}/files'],
                    capture_output=True, timeout=3
                )
                if result.returncode == 0:
                    return url, ip_type
        except:
            pass
    
    # Try WebSocket discovery
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    direct_url, ip_type = loop.run_until_complete(discover_bridge_ip())
    if direct_url:
        # Cache it for next time
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(f"{direct_url}|{ip_type}")
            return direct_url, ip_type
        except:
            pass
        return direct_url, ip_type
    
    # Fallback to MagicDNS
    return BRIDGE_URL, 'service'

def get_files_from_flash_manifest(build_dir):
    """Get list of files to upload from ESP-IDF build manifest"""
    flash_args = build_dir / 'flash_args'
    flasher_json = build_dir / 'flasher_args.json'
    
    files = []
    
    # Try flash_args file (ESP-IDF format: 0xADDR path/to/file.bin)
    if flash_args.exists():
        print("Found flash_args manifest")
        with open(flash_args) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Parse "0x2000 bootloader/bootloader.bin" format
                parts = line.split(maxsplit=1)
                if len(parts) >= 2 and parts[0].startswith('0x'):
                    filepath = parts[1]
                    filename = os.path.basename(filepath)
                    
                    # Check for versioned version of app binary (not bootloader/partition)
                    is_system = any(x in filename.lower() for x in ['bootloader', 'partition'])
                    if not is_system:
                        name_base = filename.replace('.bin', '')
                        versioned_files = list(build_dir.glob(f"{name_base}-*.bin"))
                        versioned_files = [f for f in versioned_files if '-' in f.name]
                        if versioned_files:
                            versioned_files.sort(key=lambda f: len(f.name), reverse=True)
                            filename = versioned_files[0].name
                            full_path = build_dir / filename
                            files.append((full_path, filename))
                            continue
                    
                    # Check if file exists in build dir
                    full_path = build_dir / filename
                    if full_path.exists():
                        files.append((full_path, filename))
                    else:
                        for subdir in ['bootloader', 'partition_table']:
                            alt_path = build_dir / subdir / filename
                            if alt_path.exists():
                                files.append((alt_path, filename))
                                break
    
    elif flasher_json.exists():
        print("Found flasher_args.json manifest")
        with open(flasher_json) as f:
            data = json.load(f)
            for entry in data.get('flash_files', []):
                filename = os.path.basename(entry['path'])
                full_path = build_dir / filename
                if full_path.exists():
                    files.append((full_path, filename))
                else:
                    for subdir in ['bootloader', 'partition_table']:
                        alt_path = build_dir / subdir / filename
                        if alt_path.exists():
                            files.append((alt_path, filename))
                            break
    
    # Fallback to pattern matching
    else:
        print("No flash manifest found, scanning for binaries...")
        bin_files = list(build_dir.glob('*.bin'))
        for subdir in ['bootloader', 'partition_table']:
            subdir_path = build_dir / subdir
            if subdir_path.exists():
                bin_files.extend(subdir_path.glob('*.bin'))
        for bin_file in bin_files:
            files.append((bin_file, bin_file.name))
    
    # Sort: bootloader first, partition table second
    def sort_key(item):
        path, name = item
        if 'bootloader' in name.lower():
            return (0, name)
        elif 'partition' in name.lower():
            return (1, name)
        else:
            return (2, name)
    
    return sorted(files, key=sort_key)

def upload_file(filepath, dest_name=None, bridge_url=None):
    """Upload single file to bridge"""
    filepath = Path(filepath)
    dest = dest_name if dest_name else filepath.name
    url = bridge_url if bridge_url else BRIDGE_URL
    cmd = [
        'curl', '-k', '-s',
        '-F', f'file=@{filepath};filename={dest}',
        f'{url}/upload'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            if data.get('success'):
                print(f"✓ Uploaded: {dest} ({data['size']:,} bytes)")
                return True
        except json.JSONDecodeError:
            pass
    
    print(f"✗ Upload failed: {filepath}", file=sys.stderr)
    print(f"  Response: {result.stdout}", file=sys.stderr)
    return False

def main():
    parser = argparse.ArgumentParser(description='Upload binaries to bridge')
    parser.add_argument('--project', '-p', help='Project directory')
    parser.add_argument('--file', '-f', help='Single file to upload')
    parser.add_argument('--list', '-l', action='store_true', help='List uploaded files')
    args = parser.parse_args()
    
    # Discover optimal bridge URL (prefer local LAN > Tailscale > Service)
    if not args.list:
        print("Discovering bridge...")
    bridge_url, ip_type = get_bridge_url()
    if bridge_url != BRIDGE_URL:
        url_display = bridge_url.replace('http://', '').replace(':5679', '')
        conn_type = 'local' if ip_type == 'local' else 'direct'
        print(f"  Using {conn_type} connection: {url_display}")
    
    if args.list:
        result = subprocess.run(['curl', '-k', '-s', f'{bridge_url}/files'], capture_output=True, text=True)
        try:
            data = json.loads(result.stdout)
            if 'files' in data:
                print(f"Files on bridge ({bridge_url.replace('http://', '').replace('https://', '').replace(':5679', '')}):")
                for f in data['files']:
                    print(f"  {f['name']:40s} {f['size']:,} bytes")
            else:
                print(result.stdout)
        except:
            print(result.stdout)
        return
    
    if args.file:
        upload_file(args.file, bridge_url=bridge_url)
    
    elif args.project:
        project_path = resolve_project_path(args.project)
        build_dir = project_path / 'build'
        
        # Get files from ESP-IDF flash manifest
        files = get_files_from_flash_manifest(build_dir)
        
        print(f"Uploading from: {project_path}")
        print(f"Files: {len(files)}")
        print()
        
        for filepath, filename in files:
            if filepath.exists():
                print(f"Uploading {filename}...")
                upload_file(filepath, filename, bridge_url=bridge_url)
            else:
                print(f"⚠ Not found: {filepath}")
        
        print("\nReady to flash: esp32-p4 flash")
    
    else:
        print("Error: Specify --project or --file", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
