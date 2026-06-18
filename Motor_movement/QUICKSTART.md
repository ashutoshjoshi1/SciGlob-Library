# Quick Start Guide - SciGlob Motor Control

**Get started in 3 simple steps!**

---

## Step 1: Install SciGlob Library

```bash
pip install sciglob
```

---

## Step 2: Run the Application

### Option A: Using Launcher Scripts (Easiest)

**Windows:**
```bash
run.bat
```

**Linux/Mac:**
```bash
./run.sh
```

### Option B: Direct Python Execution

```bash
python motor_control_gui.py
```

Or on Linux/Mac:
```bash
python3 motor_control_gui.py
```

---

## Step 3: Use the GUI

### Connect to Your Device

1. **Select Port** from dropdown (e.g., COM3, /dev/ttyUSB0)
2. Click **"🔄 Refresh"** if port not visible
3. Click **"🔌 Connect"**
4. Wait for green "Connected" status

### Control the Motor

1. **Select Motor Type:**
   - ○ Azimuth (Horizontal)
   - ○ Zenith (Vertical)

2. **Adjust Settings:**
   - **Step Size**: 10-1000 steps (default: 100)
   - **Speed**: 1-100% (default: 50%)

3. **Move Motor:**
   - Click **◀ CCW** for counter-clockwise
   - Click **CW ▶** for clockwise

4. **Monitor Position:**
   - Watch real-time position display
   - Status updates automatically

### Disconnect

Click **"⏻ Disconnect"** when done

---

## Tips for First Use

✅ **Start with small steps** (10-50) to test  
✅ **Use low speed** (20-30%) initially  
✅ **Watch the motor** during first movements  
✅ **Check position display** for feedback  
✅ **Power off** device before disconnecting hardware  

---

## Troubleshooting

### Port not found?
- Click "🔄 Refresh"
- Check USB cable
- Install USB drivers

### Connection failed?
- Close other serial programs
- Check device power
- Try different USB port

### Motor not moving?
- Verify motor power
- Check cables
- Start with smaller steps

---

## GUI Overview

```
┌──────────────────────────────────────────┐
│   🔧 SciGlob Motor Control               │
├──────────────────────────────────────────┤
│ Port: [COM3 ▼] [🔄]                     │
│ [🔌 Connect]  [⏻ Disconnect]            │
├──────────────────────────────────────────┤
│ Motor: ● Azimuth  ○ Zenith              │
├──────────────────────────────────────────┤
│        [◀ CCW]  [CW ▶]                  │
├──────────────────────────────────────────┤
│ Steps: [====|=====] 100                 │
│ Speed: [=====|====] 50%                 │
├──────────────────────────────────────────┤
│ Position: Azi=180°, Zen=45°             │
│ Status: Connected                       │
└──────────────────────────────────────────┘
```

---

## Example Usage

### Fine Adjustment (0.1° movements)
```
Step Size: 10 steps
Speed: 20%
Click: ◀ CCW or CW ▶
```

### Fast Movement (5° movements)
```
Step Size: 500 steps
Speed: 80%
Click: ◀ CCW or CW ▶
```

---

## Need More Help?

📖 See **README.md** for detailed documentation  
🔧 Check **motor_control_gui.py** for code  
📚 Visit SciGlob Library docs for API reference  

---

**Ready to control your motor! 🎛️**
