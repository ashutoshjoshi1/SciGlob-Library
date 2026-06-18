# Troubleshooting Guide - Linear Motor Control

## ❌ Error: "Access is denied" / PermissionError

### Problem
```
Failed to open port 'COM29'
PermissionError(13, 'Access is denied', None, 5)
```

This error means another program is already using the COM port.

### Solutions (Try in order):

#### Solution 1: Close Other Programs Using the Port

**Common programs that hold COM ports:**
- ✅ **Arduino IDE** - Close it completely
- ✅ **PuTTY / Tera Term** - Close all sessions
- ✅ **Hyperterminal** - Close it
- ✅ **Previous instance** of this app - Close it
- ✅ **Device Manager** - If port properties are open
- ✅ **Other Python scripts** - Stop them

**How to check:**
1. Open **Task Manager** (Ctrl+Shift+Esc)
2. Look for these programs and close them:
   - `arduino.exe`
   - `putty.exe`
   - `python.exe` or `pythonw.exe` (other instances)
   - `TeraTerm.exe`

#### Solution 2: Disconnect and Reconnect USB

1. Physically unplug the USB cable from your computer
2. Wait 5 seconds
3. Plug it back in
4. Click "🔄 Refresh" in the app
5. Try connecting again

#### Solution 3: Try Different USB Port

1. Unplug from current USB port
2. Try a different USB port (preferably USB 2.0 port)
3. Wait for Windows to recognize device
4. Click "🔄 Refresh"
5. Connect

#### Solution 4: Check Device Manager

1. Press `Win + X` → Device Manager
2. Expand **Ports (COM & LPT)**
3. Find your device (e.g., "USB Serial Port (COM29)")
4. Right-click → **Disable device**
5. Wait 2 seconds
6. Right-click → **Enable device**
7. Note the COM port number
8. Try connecting again

#### Solution 5: Restart the Application

1. Close this application completely
2. Re-open it
3. Select port and connect

#### Solution 6: Restart Computer

If nothing else works:
1. Close all applications
2. Restart Windows
3. Connect device first, then open app

---

## ❌ Error: "Port not found"

### Problem
```
Port COM29 not found
```

### Solutions:

1. **Refresh ports:**
   - Click "🔄 Refresh" button
   - Port might appear after device reconnect

2. **Check device is plugged in:**
   - Look for LED lights on device
   - Check USB cable connection

3. **Install drivers:**
   - Some RS485 adapters need FTDI or CH340 drivers
   - Download from manufacturer's website
   - Install and restart computer

4. **Check Device Manager:**
   - Open Device Manager
   - Look for "Unknown Device" with yellow warning
   - Right-click → Update Driver

---

## ❌ Error: "Write timeout"

### Problem
```
Failed to connect to head sensor: Write timeout
```

### Solutions:

1. **Wrong baud rate:**
   - Default is 9600
   - Your motor might use different rate
   - Common rates: 9600, 19200, 38400, 115200

2. **Motor not powered:**
   - Check motor has power supply connected
   - Look for power LED

3. **Wrong wiring:**
   - Check RS485 A/B connections
   - Swap A and B if needed

4. **Motor not responding:**
   - Motor might be in error state
   - Power cycle the motor
   - Check motor controller manual

---

## ⚙️ Changing Baud Rate

If 9600 doesn't work, you can modify the code:

1. Open `motor_control_gui.py`
2. Find line ~320: `baudrate=9600`
3. Change to your motor's baud rate:
   ```python
   baudrate=19200,  # or 38400, 115200, etc.
   ```
4. Save and restart application

---

## 🔌 Hardware Connections

### RS485 Wiring
```
Computer USB → RS485 Adapter → Motor Controller

RS485 Adapter:
A (or D+) → Motor A terminal
B (or D-) → Motor B terminal
GND       → Motor GND (if available)
```

### Common Issues:
- ❌ A and B swapped → No communication
- ❌ No ground connection → Unstable
- ❌ Long cables (>10m) → Add termination resistor (120Ω)

---

## 📝 Getting More Help

If none of these solutions work:

1. **Check motor model/manual:**
   - What commands does it accept?
   - What is the baud rate?
   - Does it need device addressing?

2. **Test with terminal program:**
   - Use PuTTY or Tera Term
   - Connect to COM port at 9600 baud
   - Try sending command manually
   - See if motor responds

3. **Provide details:**
   - Motor controller model
   - Error messages
   - What you've already tried

---

## ✅ Verification Checklist

Before asking for help, verify:

- [ ] Device is plugged in (USB cable)
- [ ] Motor has power supply connected
- [ ] COM port shows in Device Manager
- [ ] No other programs using the port
- [ ] Tried different USB port
- [ ] Drivers installed (if needed)
- [ ] Correct baud rate for your motor
- [ ] RS485 wiring is correct (A to A, B to B)

---

## 🔍 Advanced: Finding What's Using the Port

### Windows PowerShell Method:

```powershell
# Run as Administrator
Get-Process | Where-Object {$_.Modules.ModuleName -like "*serial*"}
```

### Using Process Explorer (Free Tool):

1. Download Process Explorer from Microsoft
2. Run as Administrator
3. Find → Find Handle or DLL
4. Search for: "COM29"
5. Shows which program is using the port

---

## 💡 Tips

- **Always close terminal programs** before using this app
- **USB hubs** can cause issues - try direct connection
- **Long USB cables** (>5m) can cause problems
- **Some motors need time** to power up (wait 5-10 seconds)
- **Test with low step sizes first** (10-50 steps)

---

**Still having issues?** Check the motor controller's documentation or contact support with:
- Motor controller model
- Exact error message
- What you've tried from this guide
