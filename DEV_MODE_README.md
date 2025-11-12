# FA11y Developer Mode

FA11y now includes a comprehensive developer mode with tools for debugging and development.

## Quick Start

### Windows

```batch
FA11y_dev.bat
```

or

```batch
FA11y_dev.bat pixel_inspector
```

### Python

```bash
python FA11y_dev.py
```

or

```bash
python FA11y_dev.py pixel_inspector
```

## Available Tools

### Pixel Inspector

The Pixel Inspector is a visual debugging tool that allows you to examine screenshots and pixel data that FA11y processes.

**Features:**
- Real-time display of FA11y's screenshot capture
- Zoomed pixel view (10x magnification by default)
- Displays exact RGB values that FA11y processes (not CV2's BGR interpretation)
- Click to save pixel information to a log file
- Grid overlay showing individual pixels in zoom view
- Crosshair for precise positioning

**Controls:**
- **Move mouse**: Inspect pixels under cursor
- **Left click**: Save pixel information to `pixel_inspector_log.txt`
- **Q or ESC**: Exit the tool

**Output File:**
All clicked pixels are saved to `pixel_inspector_log.txt` in the FA11y root directory with:
- Timestamp
- Coordinates (x, y)
- RGB values
- Hex color code

**Example Output:**
```
[2025-11-12 10:30:45]
Coordinates: (512, 384)
RGB: (255, 100, 50)
Hex: #FF6432
------------------------------------------------------------
```

## Technical Details

### Color Accuracy

The Pixel Inspector shows **EXACTLY** the same RGB colors that FA11y processes:

1. FA11y captures screenshots using MSS (via `screenshot_manager`)
2. MSS returns images in BGRA format
3. FA11y converts to RGB for processing
4. The Pixel Inspector displays this RGB data (not CV2's BGR interpretation)

This ensures that the colors you see in the inspector are identical to what FA11y's detection algorithms use.

### Display Windows

The Pixel Inspector opens three windows:

1. **Screenshot View**: Full screenshot with crosshair and zoom area indicator
2. **Zoomed View**: 10x magnified view of pixels under cursor with grid
3. **Info Panel**: Shows coordinates, RGB values, and controls

### Adding New Tools

To add a new developer tool:

1. Create a new class in `lib/dev/dev_mode.py`
2. Implement a `run()` method
3. Add to the `tools` dictionary in the `DevMode` class

Example:
```python
class MyNewTool:
    def __init__(self):
        print("[Dev Mode] My New Tool initialized")

    def run(self):
        print("[Dev Mode] Running My New Tool")
        # Your tool implementation here

# In DevMode.__init__:
self.tools = {
    'pixel_inspector': PixelInspector,
    'my_new_tool': MyNewTool,
}
```

## Architecture Changes

### POI Selector GUI Removal

The POI Selector GUI has been removed. All POI data management functionality has been extracted to:

**`lib/managers/poi_data_manager.py`**
- `POIData`: Manages POI loading from API and files
- `FavoritesManager`: Handles favorite POIs
- `CoordinateSystem`: Coordinate transformations
- `MapData`: Map data container

**Virtual POI Selector**
FA11y's built-in POI cycling system (accessed via keybinds) remains fully functional:
- Cycle through POIs
- Cycle through POI categories
- Cycle through maps

### FortniteManager Rewrite

The FortniteManager has been completely rewritten using FA11y's existing wxPython GUI framework (`lib/guis/gui_utilities.py`):

**Features:**
- Uses `AccessibleDialog` base class
- `BoxSizerHelper` for layout management
- Grouped sections (Management, Authentication, Launch)
- Improved error handling with logging
- Better process management with thread safety
- Comprehensive keyboard shortcuts
- Confirmation dialogs for destructive actions
- Real-time progress monitoring with configurable intervals

## Files Modified

### New Files
- `lib/dev/dev_mode.py` - Developer mode tools
- `lib/dev/__init__.py` - Dev module init
- `lib/managers/poi_data_manager.py` - POI data management
- `FortniteManager.py` - Rewritten Fortnite manager (wxPython)
- `FA11y_dev.py` - Dev mode launcher
- `FA11y_dev.bat` - Windows launcher
- `DEV_MODE_README.md` - This file

### Modified Files
- `FA11y.py` - Updated imports, removed POI selector GUI references
- `lib/guis/visited_objects_gui.py` - Updated imports
- `lib/guis/custom_poi_gui.py` - Updated imports
- `lib/detection/player_position.py` - Updated imports
- `.gitignore` - Added Python cache and dev mode exclusions

### Deleted Files
- `lib/guis/poi_selector_gui.py` - Replaced by poi_data_manager.py

## Troubleshooting

### "Module not found" errors

Make sure you're running from the FA11y root directory:
```bash
cd /path/to/FA11y
python FA11y_dev.py
```

### CV2 window not appearing

Ensure OpenCV is installed:
```bash
pip install opencv-python
```

### Colors look wrong

The Pixel Inspector shows RGB values. If you're used to seeing BGR (common in CV2), remember:
- RGB: Red, Green, Blue
- BGR: Blue, Green, Red

The inspector shows RGB because that's what FA11y processes.

## Support

For issues or questions:
1. Check the FA11y main README
2. Review the code comments in `lib/dev/dev_mode.py`
3. Create an issue on the FA11y GitHub repository

## Future Enhancements

Possible future tools for developer mode:
- OCR testing tool
- Template matching debugger
- Audio system tester
- Config validation tool
- Performance profiler
- Network request debugger

Contributions welcome!
