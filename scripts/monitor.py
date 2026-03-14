#!/usr/bin/env python3
"""
esp32-p4 monitor - Stream serial output from bridge
"""

import asyncio
import websockets
import json
import ssl
import argparse
import sys
import re

WSS_URI = "wss://esp32-bridge.tailbdd5a.ts.net:5678"

async def monitor_serial(duration=None, grep=None, reset=False, stream=False):
    """Monitor serial output"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(WSS_URI, ssl=ssl_context, ping_interval=None) as ws:
        print(f"Connected to bridge", flush=stream)
        
        # Reset device if requested
        if reset:
            print("Resetting device...", flush=stream)
            await ws.send(json.dumps({'action': 'reset'}))
            await asyncio.sleep(1)
            print("Device reset complete\n", flush=stream)
        
        print(f"Monitoring serial for {duration}s...\n", flush=stream)
        
        start = asyncio.get_event_loop().time()
        
        while True:
            # Check duration
            if duration and (asyncio.get_event_loop().time() - start > duration):
                print(f"\n[Monitor complete - {duration}s elapsed]", flush=stream)
                break
            
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                
                try:
                    data = json.loads(msg)
                    if data.get('type') == 'serial':
                        text = data.get('text', '')
                        
                        # Apply grep filter
                        if grep and not re.search(grep, text):
                            continue
                        
                        # Clean output
                        text = re.sub(r'[^\x20-\x7E\n\r]', '', text)
                        if text.strip():
                            print(text, end='', flush=stream)
                            
                    elif data.get('type') == 'status':
                        status = data.get('connected', False)
                        port = data.get('port', 'none')
                        print(f"[BRIDGE] Connected: {status}, Port: {port}", flush=stream)
                        
                    elif data.get('type') == 'system':
                        msg_text = data.get('message', '')
                        if 'HTTP endpoint' not in msg_text:  # Skip noise
                            print(f"[SYSTEM] {msg_text}", flush=stream)
                            
                except json.JSONDecodeError:
                    # Raw serial output
                    text = msg
                    if grep and not re.search(grep, text):
                        continue
                    if text.strip():
                        print(text, flush=stream)
                        
            except asyncio.TimeoutError:
                continue

def main():
    parser = argparse.ArgumentParser(description='Monitor serial output')
    parser.add_argument('--duration', '-d', type=int, default=15, help='Monitor duration in seconds (default: 15)')
    parser.add_argument('--grep', '-g', help='Filter output by pattern')
    parser.add_argument('--forever', '-f', action='store_true', help='Monitor forever (Ctrl+C to stop)')
    parser.add_argument('--reset', '-r', action='store_true', help='Reset device before monitoring')
    parser.add_argument('--stream', '-s', action='store_true', help='Stream output without buffering (flush after each line)')
    args = parser.parse_args()
    
    print("ESP32-P4 Serial Monitor")
    print(f"Bridge: {WSS_URI}\n")
    
    duration = None if args.forever else args.duration
    
    try:
        asyncio.run(monitor_serial(duration, args.grep, args.reset, args.stream))
    except KeyboardInterrupt:
        print("\n[Stopped by user]")
    
    print("\nMonitor ended.")

if __name__ == '__main__':
    main()
