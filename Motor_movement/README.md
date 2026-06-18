# SciGlob Motor Control GUI

A simple GUI application for controlling motors using the SciGlob library.

## Features

✅ **Port Selection** - Automatic detection of available serial ports  
✅ **Connect/Disconnect** - Easy connection management  
✅ **Motor Control** - Clockwise and counter-clockwise movement  
✅ **Step Size Adjustment** - Control movement precision (10-1000 steps)  
✅ **Speed Control** - Adjust motor speed (1-100%)  
✅ **Real-time Position** - Live position display  
✅ **Motor Selection** - Choose between Azimuth or Zenith motor  

---

## Installation

### Step 1: Install SciGlob Library

```bash
pip install sciglob
```

### Step 2: Run the Application

```bash
python motor_control_gui.py
```

Or make it executable (Linux/Mac):

```bash
chmod +x motor_control_gui.py
./motor_control_gui.py
```

---

## Usage Guide

### 1. Connect to Device

1. **Select Port**: Choose your device's serial port from the dropdown
   - Click "🔄 Refresh" if your device isn't listed
2. **Click "🔌 Connect"** to establish connection
3. Wait for "Connected" status

### 2. Select Motor

- **Azimuth Motor**: Horizontal rotation (pan)
- **Zenith Motor**: Vertical rotation (tilt)

### 3. Control Motor

- **◀ CCW Button**: Move counter-clockwise
- **CW ▶ Button**: Move clockwise

### 4. Adjust Settings

**Step Size** (10-1000 steps):
- Small values (10-100): Fine control, small movements
- Large values (500-1000): Fast movements

**Speed** (1-100%):
- Low speed: Precise, smooth movements
- High speed: Fast movements

### 5. Monitor Status

- **Position Display**: Shows current Azimuth and Zenith angles
- **Status Bar**: Shows connection status and current action

### 6. Disconnect

Click "⏻ Disconnect" to safely disconnect from the device

---

## GUI Layout

```
┌─────────────────────────────────────────────────┐
│       🔧 SciGlob Motor Control                  │
├─────────────────────────────────────────────────┤
│ Connection                                      │
│   Port: [COM3      ▼] [🔄 Refresh]             │
│   [🔌 Connect]  [⏻ Disconnect]                 │
├─────────────────────────────────────────────────┤
│ Motor Selection                                 │
│   ○ Azimuth Motor (Horizontal Rotation)        │
│   ○ Zenith Motor (Vertical Rotation)           │
├─────────────────────────────────────────────────┤
│ Motor Control                                   │
│                                                 │
│    [◀ CCW]      Motor       [CW ▶]             │
│                 Control                         │
│                                                 │
├─────────────────────────────────────────────────┤
│ Movement Settings                               │
│   Step Size:  [====|==========] 100 steps      │
│   Speed:      [==========|====] 50%            │
├─────────────────────────────────────────────────┤
│ Status                                          │
│   Position: Azimuth=180.50°, Zenith=45.25°     │
│   Status: Connected to COM3                    │
└─────────────────────────────────────────────────┘
```

---

## Requirements

- **Python**: 3.9 or higher
- **SciGlob Library**: 0.1.5 or higher (installed via pip)
- **Hardware**: SciGlob Head Sensor with Tracker
- **OS**: Windows, Linux, or macOS

---

## Troubleshooting

### Port Not Showing

**Problem**: Device port doesn't appear in the dropdown

**Solutions**:
1. Check USB cable connection
2. Click "🔄 Refresh" button
3. Install USB-to-Serial drivers if needed
4. Check device is powered on

### Connection Failed

**Problem**: "Failed to connect" error message

**Solutions**:
1. Verify correct port is selected
2. Close other applications using the port
3. Check device is powered and responding
4. Try different USB port

### Motor Not Moving

**Problem**: Buttons click but motor doesn't move

**Solutions**:
1. Check motor is powered
2. Verify motor cables are connected
3. Try smaller step sizes first (10-50 steps)
4. Check for motor alarms (see status)

### Position Not Updating

**Problem**: Position display shows old values

**Solutions**:
1. Disconnect and reconnect
2. Check serial communication
3. Verify tracker firmware is responding

---

## Technical Details

### Motor Control

The application uses the SciGlob library's `HeadSensor` and `Tracker` classes:

- **Azimuth Motor**: Controlled with `move_azimuth_steps(steps)`
  - Positive steps → Clockwise
  - Negative steps → Counter-clockwise

- **Zenith Motor**: Controlled with `move_zenith_steps(steps)`
  - Positive steps → Clockwise
  - Negative steps → Counter-clockwise

### Step Size

- 1 step ≈ 0.01 degrees (typical configuration)
- 100 steps = 1 degree
- 1000 steps = 10 degrees

### Speed Control

Speed control adjusts the motor speed setting if supported by the tracker firmware. The actual implementation depends on the tracker type (Directed Perceptions or LuftBlickTR1).

---

## Code Structure

```
Motor_movement/
├── motor_control_gui.py    # Main application
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

### Main Components

**MotorControlGUI Class**:
- `connect()` - Establish serial connection
- `disconnect()` - Close connection
- `move_cw()` - Move motor clockwise
- `move_ccw()` - Move motor counter-clockwise
- `update_position_loop()` - Background position updates

---

## Safety Notes

⚠️ **Important Safety Information**:

1. **Power Off First**: Always power off motors before connecting/disconnecting
2. **Start Small**: Begin with small step sizes (10-50 steps) to test
3. **Monitor Movement**: Watch the motor during operation
4. **Emergency Stop**: Close the application to stop all movement
5. **Position Limits**: Be aware of mechanical limits to prevent damage

---

## Advanced Usage

### Running from Command Line

```bash
# Windows
python motor_control_gui.py

# Linux/Mac
python3 motor_control_gui.py
```

### Creating Standalone Executable

Using PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "SciGlob Motor Control" motor_control_gui.py
```

The executable will be in the `dist/` folder.

---

## Examples

### Example 1: Fine Position Adjustment

1. Set Step Size: 10 steps (0.1°)
2. Set Speed: 20%
3. Click CW or CCW for precise movement

### Example 2: Fast Movement

1. Set Step Size: 500 steps (5°)
2. Set Speed: 80%
3. Click CW or CCW for quick positioning

### Example 3: Scanning Motion

1. Set Step Size: 100 steps (1°)
2. Click CW multiple times to scan
3. Watch position display for current angle

---

## Keyboard Shortcuts

Currently, the application uses mouse-only control. Future versions may include:
- `Left Arrow` - Move CCW
- `Right Arrow` - Move CW
- `Space` - Stop movement
- `Ctrl+C` - Connect
- `Ctrl+D` - Disconnect

---

## Version History

**v1.0** (2025-12-17)
- Initial release
- Basic motor control functionality
- Real-time position display
- Step size and speed adjustment

---

## Support

For issues or questions:
- **SciGlob Library**: https://github.com/ashutoshjoshi1/SciGlob-Library
- **Library Documentation**: See docs/ folder in main repository

---

## License

This application uses the SciGlob library. See the library's LICENSE file for details.

---

## Credits

Built using:
- **SciGlob Library** by Ashutosh Joshi
- **Python Tkinter** for GUI
- **PySerial** for serial communication (via SciGlob)

---

**Happy Motor Controlling! 🎛️**
