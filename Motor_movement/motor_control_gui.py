#!/usr/bin/env python3
"""
SciGlob Linear Motor Control GUI
A simple GUI application to control a linear motor using the SciGlob library.

Features:
- Port selection and connection management
- Left/Right linear movement control
- Adjustable step size and speed
- Real-time position display
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Optional

try:
    from sciglob.core.connection import SerialConnection
    from sciglob.core.protocols import SerialConfig
    from sciglob.core.exceptions import ConnectionError, CommunicationError
    import serial.tools.list_ports
except ImportError as e:
    print("Error: SciGlob library not found!")
    print("Please install it with: pip install sciglob")
    exit(1)


class MotorControlGUI:
    """GUI application for controlling SciGlob linear motor."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SciGlob Linear Motor Control")
        self.root.geometry("600x450")
        self.root.resizable(False, False)
        
        # Variables
        self.connection: Optional[SerialConnection] = None
        self.connected = False
        self.selected_port = tk.StringVar()
        self.step_size = tk.IntVar(value=100)
        self.speed = tk.IntVar(value=50)
        self.current_position = tk.StringVar(value="Position: Not Connected")
        self.current_steps = 0  # Track current position in steps
        
        # Position update thread
        self.position_thread = None
        self.stop_thread = False
        
        # Setup GUI
        self.setup_gui()
        
        # Refresh ports on startup
        self.refresh_ports()
        
    def setup_gui(self):
        """Setup the GUI components."""
        
        # Title Label
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="🔧 Linear Motor Control",
            font=("Arial", 20, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title_label.pack(pady=15)
        
        # Main content frame
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Connection Section
        self.create_connection_section(main_frame)
        
        # Control Section
        self.create_control_section(main_frame)
        
        # Speed Control Section
        self.create_speed_section(main_frame)
        
        # Status Section
        self.create_status_section(main_frame)
        
    def create_connection_section(self, parent):
        """Create the connection control section."""
        conn_frame = tk.LabelFrame(parent, text="Connection", font=("Arial", 12, "bold"), padx=10, pady=10)
        conn_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Port selection row
        port_row = tk.Frame(conn_frame)
        port_row.pack(fill=tk.X, pady=5)
        
        tk.Label(port_row, text="Port:", font=("Arial", 10)).pack(side=tk.LEFT, padx=(0, 10))
        
        self.port_combo = ttk.Combobox(
            port_row,
            textvariable=self.selected_port,
            state="readonly",
            width=30,
            font=("Arial", 10)
        )
        self.port_combo.pack(side=tk.LEFT, padx=(0, 10))
        
        refresh_btn = tk.Button(
            port_row,
            text="🔄 Refresh",
            command=self.refresh_ports,
            bg="#3498db",
            fg="white",
            font=("Arial", 9),
            relief=tk.FLAT,
            padx=10
        )
        refresh_btn.pack(side=tk.LEFT)
        
        # Connection buttons row
        btn_row = tk.Frame(conn_frame)
        btn_row.pack(fill=tk.X, pady=(10, 0))
        
        self.connect_btn = tk.Button(
            btn_row,
            text="🔌 Connect",
            command=self.connect,
            bg="#27ae60",
            fg="white",
            font=("Arial", 11, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=10,
            width=15
        )
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.disconnect_btn = tk.Button(
            btn_row,
            text="⏻ Disconnect",
            command=self.disconnect,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 11, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=10,
            width=15,
            state=tk.DISABLED
        )
        self.disconnect_btn.pack(side=tk.LEFT)
        
    def create_control_section(self, parent):
        """Create motor control buttons section."""
        control_frame = tk.LabelFrame(parent, text="Linear Motor Control", font=("Arial", 12, "bold"), padx=10, pady=10)
        control_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Info label
        info_label = tk.Label(
            control_frame,
            text="Rail Movement",
            font=("Arial", 10),
            fg="#7f8c8d"
        )
        info_label.pack(pady=(0, 10))
        
        # Arrows and center display
        arrow_frame = tk.Frame(control_frame)
        arrow_frame.pack(pady=10)
        
        # Left button
        self.left_btn = tk.Button(
            arrow_frame,
            text="◀ LEFT",
            command=self.move_left,
            bg="#3498db",
            fg="white",
            font=("Arial", 16, "bold"),
            relief=tk.FLAT,
            width=10,
            height=3,
            state=tk.DISABLED
        )
        self.left_btn.pack(side=tk.LEFT, padx=20)
        
        # Center info
        center_frame = tk.Frame(arrow_frame)
        center_frame.pack(side=tk.LEFT, padx=20)
        
        tk.Label(
            center_frame,
            text="Linear\nMovement",
            font=("Arial", 12, "bold"),
            fg="#34495e"
        ).pack()
        
        # Right button
        self.right_btn = tk.Button(
            arrow_frame,
            text="RIGHT ▶",
            command=self.move_right,
            bg="#3498db",
            fg="white",
            font=("Arial", 16, "bold"),
            relief=tk.FLAT,
            width=10,
            height=3,
            state=tk.DISABLED
        )
        self.right_btn.pack(side=tk.LEFT, padx=20)
        
    def create_speed_section(self, parent):
        """Create speed and step control section."""
        speed_frame = tk.LabelFrame(parent, text="Movement Settings", font=("Arial", 12, "bold"), padx=10, pady=10)
        speed_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Step size control
        step_row = tk.Frame(speed_frame)
        step_row.pack(fill=tk.X, pady=5)
        
        tk.Label(step_row, text="Step Size:", font=("Arial", 10), width=12, anchor=tk.W).pack(side=tk.LEFT)
        
        self.step_scale = tk.Scale(
            step_row,
            from_=10,
            to=1000,
            variable=self.step_size,
            orient=tk.HORIZONTAL,
            length=300,
            font=("Arial", 9),
            state=tk.DISABLED
        )
        self.step_scale.pack(side=tk.LEFT, padx=10)
        
        self.step_label = tk.Label(step_row, text="100 steps", font=("Arial", 10), width=10)
        self.step_label.pack(side=tk.LEFT)
        
        self.step_size.trace_add("write", self.update_step_label)
        
        # Speed control
        speed_row = tk.Frame(speed_frame)
        speed_row.pack(fill=tk.X, pady=5)
        
        tk.Label(speed_row, text="Speed:", font=("Arial", 10), width=12, anchor=tk.W).pack(side=tk.LEFT)
        
        self.speed_scale = tk.Scale(
            speed_row,
            from_=1,
            to=100,
            variable=self.speed,
            orient=tk.HORIZONTAL,
            length=300,
            font=("Arial", 9),
            state=tk.DISABLED
        )
        self.speed_scale.pack(side=tk.LEFT, padx=10)
        
        self.speed_label = tk.Label(speed_row, text="50%", font=("Arial", 10), width=10)
        self.speed_label.pack(side=tk.LEFT)
        
        self.speed.trace_add("write", self.update_speed_label)
        
    def create_status_section(self, parent):
        """Create status display section."""
        status_frame = tk.LabelFrame(parent, text="Status", font=("Arial", 12, "bold"), padx=10, pady=10)
        status_frame.pack(fill=tk.BOTH, expand=True)
        
        self.position_label = tk.Label(
            status_frame,
            textvariable=self.current_position,
            font=("Arial", 12),
            fg="#2c3e50",
            pady=10
        )
        self.position_label.pack()
        
        self.status_label = tk.Label(
            status_frame,
            text="Status: Disconnected",
            font=("Arial", 10),
            fg="#95a5a6"
        )
        self.status_label.pack()
        
    def refresh_ports(self):
        """Refresh available serial ports."""
        ports = serial.tools.list_ports.comports()
        port_list = []
        
        for port in ports:
            # Show port with description
            port_info = f"{port.device}"
            if port.description and port.description != 'n/a':
                port_info += f" - {port.description}"
            port_list.append(port_info)
        
        # Extract just the port names for the combo box
        port_devices = [port.device for port in ports]
        
        self.port_combo['values'] = port_devices
        if port_devices:
            self.port_combo.current(0)
            # Show port info in status
            info = f"Found {len(port_devices)} port(s)"
            self.status_label.config(text=info, fg="#7f8c8d")
        else:
            messagebox.showwarning("No Ports", "No serial ports detected!\n\nMake sure your device is plugged in.")
            
    def connect(self):
        """Connect to the selected port."""
        port = self.selected_port.get()
        if not port:
            messagebox.showerror("Error", "Please select a port!")
            return
            
        try:
            self.status_label.config(text="Status: Connecting...", fg="#f39c12")
            self.root.update()
            
            # Create serial configuration for RS485 connection
            # Typical RS485 settings: 9600 baud, 8N1
            config = SerialConfig(
                baudrate=9600,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=2.0,
                write_timeout=2.0
            )
            
            # Connect to motor via RS485
            self.connection = SerialConnection(port=port, config=config)
            self.connection.open()
            
            self.connected = True
            self.current_steps = 0  # Reset position counter
            
            # Update UI
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.port_combo.config(state=tk.DISABLED)
            self.left_btn.config(state=tk.NORMAL)
            self.right_btn.config(state=tk.NORMAL)
            self.step_scale.config(state=tk.NORMAL)
            self.speed_scale.config(state=tk.NORMAL)
            
            self.status_label.config(text=f"Status: Connected to {port}", fg="#27ae60")
            self.current_position.set("Position: 0 steps (Home)")
            
            messagebox.showinfo("Success", f"Connected to {port} successfully!")
            
        except PermissionError as e:
            self.status_label.config(text="Status: Connection Failed", fg="#e74c3c")
            error_msg = (
                f"Port {port} is already in use!\n\n"
                "Possible solutions:\n"
                "1. Close other programs using this port\n"
                "   (Arduino IDE, PuTTY, Tera Term, etc.)\n\n"
                "2. Disconnect and reconnect the USB cable\n\n"
                "3. Try a different USB port\n\n"
                "4. Restart the application"
            )
            messagebox.showerror("Port Access Denied", error_msg)
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
            self.connection = None
            
        except Exception as e:
            self.status_label.config(text="Status: Connection Failed", fg="#e74c3c")
            error_msg = f"Failed to connect to {port}\n\nError: {str(e)}"
            
            # Add helpful suggestions based on error type
            if "could not open" in str(e).lower():
                error_msg += "\n\nTip: Make sure the device is plugged in and drivers are installed."
            elif "timeout" in str(e).lower():
                error_msg += "\n\nTip: Device not responding. Check power and connections."
            
            messagebox.showerror("Connection Error", error_msg)
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
            self.connection = None
            
    def disconnect(self):
        """Disconnect from the device."""
        if self.connection:
            try:
                # Stop position update thread
                self.stop_thread = True
                if self.position_thread:
                    self.position_thread.join(timeout=2)
                
                self.connection.close()
                self.connection = None
                self.connected = False
                
                # Update UI
                self.connect_btn.config(state=tk.NORMAL)
                self.disconnect_btn.config(state=tk.DISABLED)
                self.port_combo.config(state=tk.READONLY)
                self.left_btn.config(state=tk.DISABLED)
                self.right_btn.config(state=tk.DISABLED)
                self.step_scale.config(state=tk.DISABLED)
                self.speed_scale.config(state=tk.DISABLED)
                
                self.current_position.set("Position: Not Connected")
                self.status_label.config(text="Status: Disconnected", fg="#95a5a6")
                
                messagebox.showinfo("Disconnected", "Disconnected successfully!")
                
            except Exception as e:
                messagebox.showerror("Error", f"Error during disconnect:\n{str(e)}")
                
    def send_motor_command(self, steps: int):
        """Send movement command to motor via RS485."""
        if not self.connection:
            return False
            
        try:
            # Motor command format: TRp<steps> for pan/horizontal movement
            # Positive steps = right, negative steps = left
            command = f"TRp{steps:+d}"
            
            # Send command to motor (no response expected for movement commands)
            self.connection.send_command(command)
            
            # Update position counter
            self.current_steps += steps
            
            # Update position display
            direction = "right" if steps > 0 else "left"
            self.current_position.set(f"Position: {self.current_steps} steps from home")
            
            return True
            
        except Exception as e:
            raise Exception(f"Motor command failed: {str(e)}")
    
    def move_right(self):
        """Move motor to the right."""
        if not self.connected or not self.connection:
            return
            
        try:
            steps = self.step_size.get()
            
            self.status_label.config(text=f"Status: Moving RIGHT ({steps} steps)...", fg="#3498db")
            self.root.update()
            
            # Send command to motor
            self.send_motor_command(steps)
            
            # Give time for motor to move
            time.sleep(0.5)
            
            self.status_label.config(text=f"Status: Moved RIGHT ({steps} steps)", fg="#27ae60")
                
        except Exception as e:
            messagebox.showerror("Movement Error", f"Failed to move motor:\n{str(e)}")
            self.status_label.config(text="Status: Movement Failed", fg="#e74c3c")
            
    def move_left(self):
        """Move motor to the left."""
        if not self.connected or not self.connection:
            return
            
        try:
            steps = self.step_size.get()
            
            self.status_label.config(text=f"Status: Moving LEFT ({steps} steps)...", fg="#3498db")
            self.root.update()
            
            # Send command to motor (negative for left)
            self.send_motor_command(-steps)
            
            # Give time for motor to move
            time.sleep(0.5)
            
            self.status_label.config(text=f"Status: Moved LEFT ({steps} steps)", fg="#27ae60")
                
        except Exception as e:
            messagebox.showerror("Movement Error", f"Failed to move motor:\n{str(e)}")
            self.status_label.config(text="Status: Movement Failed", fg="#e74c3c")
            
    def update_step_label(self, *args):
        """Update step size label."""
        self.step_label.config(text=f"{self.step_size.get()} steps")
        
    def update_speed_label(self, *args):
        """Update speed label."""
        self.speed_label.config(text=f"{self.speed.get()}%")
        
    def on_closing(self):
        """Handle window closing."""
        if self.connected:
            if messagebox.askokcancel("Quit", "Disconnect and quit?"):
                self.disconnect()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    """Main entry point."""
    root = tk.Tk()
    app = MotorControlGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
