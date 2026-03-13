# Status: **RESOLVED** ✅

**Fixed in commit:** `f5eef4f`

**Date fixed:** March 13, 2026

---

## Original Issue

The `esp32-p4 iterate --project . --monitor` command builds the correct versioned binary but uploads a stale cached version, leading to confusing "changes don't appear on device" scenarios.

## Root Cause

Versioned binary discovery sorted files by **filename length**, not modification time:

```python
# BEFORE (bug):
versioned.sort(key=lambda f: len(f.name), reverse=True)
```

This could return an older cached file if it happened to have a longer name.

## Solution

Changed sort to use **modification time** (newest first):

```python
# AFTER (fixed):
versioned.sort(key=lambda f: os.path.getmtime(f), reverse=True)
```

## Files Modified

- `scripts/upload.py`
- `scripts/flash.py`
- `scripts/flash_batch.py`

## Test Results

After fix:
```bash
$ esp32-p4 build --project .
✓ Build successful!
  esp_brookesia_demo-bfed6de-dirty.bin (versioned)

$ esp32-p4 iterate --project . --monitor
✓ Uploading esp_brookesia_demo-bfed6de-dirty.bin (correct version!)
✓ Flash complete
Device running latest binary ✅
```

## Verification

To verify the fix works:
1. Build project: `esp32-p4 build --project .`
2. Note new versioned binary: `project-<hash>-dirty.bin`
3. Run iterate: `esp32-p4 iterate --project . --monitor`
4. Check that the correct (newest) binary is uploaded and flashed

---

**The marshmallow stands on solid foundation.** 🍡
