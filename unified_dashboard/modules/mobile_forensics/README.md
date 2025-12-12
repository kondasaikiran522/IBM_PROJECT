# Mobile Forensics Tool - Professional Edition

A modern, web-based mobile forensics tool for extracting digital evidence from Android devices using ADB (Android Debug Bridge).

## 🚀 Features

### Enhanced User Interface
- **Modern Design**: Professional gradient background with card-based layout
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Real-time Status Monitoring**: Live device connection status with automatic refresh
- **Progress Tracking**: Visual progress bar with detailed status messages
- **Statistics Dashboard**: Real-time extraction statistics and data counts

### Data Extraction Capabilities
- **Call Logs**: Complete call history with timestamps, duration, and contact names
- **SMS Messages**: Text messages with sender, timestamp, and message content
- **Contacts**: Phone contacts with names, numbers, and additional metadata
- **Photos**: Image files from device storage
- **Installed Applications**: List of user-installed apps with package information
- **Browser History**: Basic browser data extraction (Chrome)

### Advanced Features
- **Device Status Monitoring**: Real-time ADB and device connection status
- **Multiple Export Formats**: Excel reports and JSON data export
- **Time Range Filtering**: Extract data from specific time periods
- **Error Handling**: Comprehensive error reporting and user feedback
- **Form Validation**: Smart form validation with visual feedback

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.7+
- ADB (Android Debug Bridge) installed and in PATH
- Android device with USB debugging enabled

### Installation Steps

1. **Clone or download the project**
   ```bash
   git clone <repository-url>
   cd IBM_PRO
   ```

2. **Install Python dependencies**
   ```bash
   pip install flask pandas xlsxwriter
   ```

3. **Enable USB Debugging on Android device**
   - Go to Settings > About Phone
   - Tap "Build Number" 7 times to enable Developer Options
   - Go to Settings > Developer Options
   - Enable "USB Debugging"
   - Connect device via USB

4. **Authorize ADB connection**
   - When prompted on your device, allow USB debugging
   - Run `adb devices` to verify connection

5. **Start the application**
   ```bash
   python main.py
   ```

6. **Access the interface**
   - Open browser and go to `http://localhost:5000`
   - The enhanced interface will load automatically

## 📱 Usage Guide

### 1. Device Connection
- The interface automatically checks device status every 10 seconds
- Ensure your device shows as "Connected" and "Authorized"
- Use the "Refresh Status" button to manually check connection

### 2. Case Configuration
- **Case Name**: Enter a descriptive name for your forensic case
- **Case Number**: Provide a unique case identifier
- **Time Range**: Select the time period for data extraction
- **Data Types**: Choose which types of data to extract

### 3. Data Extraction
- Click "Start Extraction" to begin the process
- Monitor progress in real-time with the progress bar
- View extraction statistics as data is processed
- Wait for completion notification

### 4. Results & Export
- Review extracted data in the formatted output area
- Download Excel report for comprehensive analysis
- Export JSON data for further processing
- Clear results to start a new extraction

## 🎨 Interface Enhancements

### Visual Improvements
- **Gradient Background**: Professional purple gradient theme
- **Card Layout**: Clean, organized information display
- **Icons**: Font Awesome icons for better visual hierarchy
- **Hover Effects**: Interactive elements with smooth animations
- **Status Indicators**: Color-coded status displays

### User Experience
- **Real-time Feedback**: Immediate response to user actions
- **Error Handling**: Clear error messages with suggestions
- **Loading States**: Visual feedback during operations
- **Responsive Design**: Adapts to different screen sizes
- **Accessibility**: Proper contrast and keyboard navigation

### Functionality
- **Device Monitoring**: Continuous connection status checking
- **Smart Validation**: Form validation with helpful messages
- **Progress Tracking**: Detailed extraction progress updates
- **Data Statistics**: Real-time counts of extracted items
- **Export Options**: Multiple format support for results

## 🔧 Technical Details

### Backend Enhancements
- **Device Status API**: New endpoint for real-time device monitoring
- **Enhanced Error Handling**: Better error reporting and recovery
- **Additional Data Types**: Support for apps and browser data
- **Improved Progress Tracking**: More accurate progress calculation
- **Better Data Formatting**: Enhanced output formatting

### Frontend Improvements
- **Modern JavaScript**: ES6+ features and async/await
- **Event Handling**: Comprehensive event management
- **State Management**: Better application state handling
- **API Integration**: Enhanced communication with backend
- **Error Recovery**: Graceful error handling and recovery

## 📊 Data Types Supported

| Data Type | Description | Fields Extracted |
|-----------|-------------|------------------|
| Call Logs | Phone call history | Number, Name, Date, Duration, Type |
| SMS Messages | Text messages | Address, Date, Body, Type |
| Contacts | Phone contacts | Name, Number, Type, Label |
| Photos | Image files | File paths and metadata |
| Apps | Installed applications | Package name, Path, Type |
| Browser | Browser history | URLs and timestamps |

## 🚨 Important Notes

### Security Considerations
- This tool requires physical access to the device
- USB debugging must be enabled (requires device unlock)
- Extracted data should be handled according to legal requirements
- Always obtain proper authorization before forensic analysis

### Limitations
- Requires ADB access to the device
- Some data may require root access for full extraction
- Browser history extraction is limited without database access
- Photo extraction depends on device storage structure

### Troubleshooting
- **Device not detected**: Check USB connection and debugging settings
- **ADB not found**: Ensure Android Platform Tools are installed
- **Authorization failed**: Accept USB debugging prompt on device
- **Extraction errors**: Check device storage and permissions

## 🔄 Future Enhancements

### Planned Features
- **Root Access Support**: Enhanced data extraction with root privileges
- **Cloud Data Integration**: Support for cloud service data extraction
- **Advanced Filtering**: More sophisticated data filtering options
- **Report Generation**: Automated forensic report generation
- **Data Visualization**: Charts and graphs for extracted data
- **Multi-device Support**: Simultaneous extraction from multiple devices

### Technical Improvements
- **Database Integration**: Persistent case management
- **API Authentication**: Secure API access controls
- **Plugin System**: Extensible architecture for custom extractors
- **Performance Optimization**: Faster extraction and processing
- **Cross-platform Support**: Native desktop application

## 📄 License

This project is for educational and forensic purposes. Ensure compliance with local laws and regulations when using this tool.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

---

**Note**: This tool is designed for legitimate forensic analysis. Always ensure you have proper authorization before extracting data from any device.
