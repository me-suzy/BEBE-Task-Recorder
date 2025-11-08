# BEBE Task Recorder

<div align="center">

![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

**A powerful, user-friendly macro recorder and automation tool for Windows**

*Record mouse movements, clicks, keyboard input, and key combinations with precision. Playback your recorded tasks with customizable speed.*

[Features](#-features) • [Installation](#-installation) • [Usage](#-usage) • [Building](#-building) • [Contributing](#-contributing)

</div>

---

## 🎯 Overview

**BEBE Task Recorder** is a professional-grade macro recording and playback application designed for Windows. Unlike basic macro tools like TinyTask, BEBE offers:

<div align="center">

![BEBE Task Recorder Screenshot](screenshot.png)

*BEBE Task Recorder - Professional GUI Interface*

</div>

- ✅ **Full GUI interface** with real-time event monitoring
- ✅ **Advanced key combination support** (Ctrl+A, Alt+F4, Ctrl+Shift+B, etc.)
- ✅ **Precise mouse tracking** (movements, clicks, scrolls)
- ✅ **Task management** (save, load, organize your macros)
- ✅ **Detailed logging** (human-readable event logs)
- ✅ **Administrator privilege handling** (automatic UAC elevation)
- ✅ **Executable build** (standalone .exe with admin rights)

Perfect for automating repetitive tasks, testing workflows, or creating complex automation sequences.

---

## ✨ Features

### Recording Capabilities
- **Mouse Events**: Track all mouse movements, clicks (left/right/middle), and scroll actions
- **Keyboard Input**: Record individual keys, characters, and special keys (Enter, Tab, F1-F12, Arrow keys, etc.)
- **Key Combinations**: Properly handles Ctrl, Alt, Shift combinations:
  - `Ctrl+A` (Select All)
  - `Ctrl+Shift+A` (Complex combinations)
  - `Alt+F4` (Close window)
  - `Ctrl+C`, `Ctrl+V` (Copy/Paste)
  - And many more...

### Playback Features
- **Precise Timing**: Maintains original timing between events
- **Adjustable Speed**: Customizable playback speed (default optimized)
- **Error Handling**: Robust error handling during playback

### User Interface
- **Real-time Monitoring**: See events as they're recorded in a detailed table
- **Task Management**: Save and load tasks with descriptive names
- **Quick Load**: Dropdown list of saved tasks for easy access
- **Resizable Window**: Adjust interface to your preference
- **Event Details**: View timestamp, event type, and detailed information

### Technical Features
- **Administrator Mode**: Automatically requests admin privileges for global event capture
- **Thread-safe GUI**: Smooth UI updates during recording/playback
- **JSON Storage**: Human-readable task files
- **Log Files**: Detailed `.log` files alongside `.json` task files

---

## 📋 Requirements

- **Operating System**: Windows 7/8/10/11
- **Python**: 3.7 or higher (if running from source)
- **Dependencies**:
  - `pyautogui` - GUI automation
  - `pynput` - Mouse and keyboard event capture
  - `tkinter` - GUI framework (usually included with Python)

---

## 🚀 Installation

### Option 1: Using Pre-built Executable (Recommended)

1. Download `BEBE_Task_Recorder.exe` from the [Releases](https://github.com/me-suzy/BEBE-Task-Recorder/releases) page
2. Run the executable (it will automatically request administrator privileges)
3. Start recording!

### Option 2: Running from Source

1. **Clone the repository**:
   ```bash
   git clone https://github.com/me-suzy/BEBE-Task-Recorder.git
   cd BEBE-Task-Recorder
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python bebe_gui.py
   ```
   
   **Note**: On Windows, run with administrator privileges for global event capture:
   ```bash
   # Right-click PowerShell/CMD and select "Run as Administrator", then:
   python bebe_gui.py
   ```
   
   Or use the provided batch script:
   ```bash
   RUN_GUI.bat
   ```

---

## 📖 Usage

### Basic Workflow

1. **Start Recording**:
   - Click "Start Inregistrare"
   - Perform your actions (mouse movements, clicks, keyboard input)
   - Press `ESC` or `F9` to stop recording

2. **Review Events**:
   - View all recorded events in the "Evenimente (optimizate cu context)" table
   - Check timestamps and event details

3. **Save Task**:
   - Click "Salveaza task"
   - Enter a descriptive name
   - Task is saved in the `tasks/` folder

4. **Load Task**:
   - Select from dropdown list, or
   - Click "Incarca din fisier..." to browse
   - Click "Incarca task selectat" to load

5. **Playback**:
   - Click "Start Redare"
   - Watch your recorded actions replay automatically

### Recording Tips

- **Position Matters**: The recorder captures absolute screen coordinates. If you move windows or icons before playback, positions may not match. This is expected behavior for precise automation.

- **Key Combinations**: All standard Windows shortcuts work:
  - `Ctrl+A`, `Ctrl+C`, `Ctrl+V` (Select All, Copy, Paste)
  - `Alt+Tab` (Switch windows)
  - `Alt+F4` (Close window)
  - `Ctrl+Shift+Esc` (Task Manager)
  - And more...

- **Stop Recording**: Press `ESC` or `F9` at any time to stop recording

### File Structure

```
BEBE/
├── bebe_gui.py              # Main application
├── tasks/                   # Saved task files
│   ├── task1.json          # Task data (JSON)
│   └── task1.log            # Human-readable log
├── requirements.txt         # Python dependencies
├── BUILD.bat                # Build executable script
└── README.md               # This file
```

---

## 🔨 Building Executable

To create a standalone `.exe` file with automatic administrator privileges:

1. **Install build dependencies**:
   ```bash
   pip install -r requirements_build.txt
   ```

2. **Run build script**:
   ```bash
   BUILD.bat
   ```

3. **Find executable**:
   - Output: `dist/BEBE_Task_Recorder.exe`
   - The executable automatically requests admin privileges on launch

### Build Requirements

- `pyinstaller` - For creating executables
- `pyautogui`, `pynput` - Runtime dependencies

---

## 🎨 Screenshots

<div align="center">

![BEBE Task Recorder Interface](screenshot.png)

*Main interface showing real-time event monitoring, task management, and playback controls*

</div>

---

## 🔧 Technical Details

### Architecture

- **GUI Framework**: Tkinter (native Python GUI)
- **Event Capture**: `pynput` library for global mouse/keyboard hooks
- **Automation**: `pyautogui` for precise mouse/keyboard control
- **Storage**: JSON format for task files
- **Threading**: Separate threads for recording/playback to keep GUI responsive

### Key Features Implementation

- **Key Combination Detection**: Properly handles control characters (e.g., `\x01` = Ctrl+A)
- **Modifier Tracking**: Maintains state of Ctrl/Alt/Shift keys during recording
- **Event Serialization**: Efficient JSON storage with timestamps
- **Admin Privileges**: Windows UAC manifest embedded in executable

---

## ⚠️ Important Notes

### Administrator Privileges

**Why admin rights are needed**: Global keyboard and mouse hooks require elevated privileges on Windows. Without admin rights, the application can only capture events from its own window.

**Security**: The application only requests admin rights for event capture. It does not modify system files or settings.

### Position-Based Recording

**Important**: BEBE records **absolute screen coordinates**. This means:
- ✅ Perfect for fixed workflows (same window positions)
- ⚠️ If you move windows/icons before playback, coordinates won't match
- 💡 **Tip**: Keep your desktop layout consistent, or use relative positioning for future versions

This is intentional design for precise automation - similar to professional macro tools.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built with Python and open-source libraries
- Inspired by the need for better macro recording tools
- Thanks to all contributors and users

---

## 📧 Support

- **Issues**: [GitHub Issues](https://github.com/me-suzy/BEBE-Task-Recorder/issues)
- **Discussions**: [GitHub Discussions](https://github.com/me-suzy/BEBE-Task-Recorder/discussions)

---

## 🚀 Roadmap

- [ ] Relative positioning mode (for flexible window positions)
- [ ] Variable speed playback controls
- [ ] Task scheduling (run at specific times)
- [ ] Multiple task chaining
- [ ] Export/Import task collections
- [ ] Cross-platform support (Linux, macOS)

---

<div align="center">

**Made with ❤️ for automation enthusiasts**

⭐ Star this repo if you find it useful!

</div>

