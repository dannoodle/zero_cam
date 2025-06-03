#!/bin/bash
# Enhanced Installation script for Raspberry Pi Zero Camera System

set -e

# Display banner
echo "=================================================="
echo "    Raspberry Pi Zero Camera System Installer     "
echo "=================================================="
echo "This script will guide you through the installation process"
echo "=================================================="

# Script must be run as root
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use sudo."
    exit 1
fi

# Determine the actual user (who ran sudo)
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    # If not run with sudo, try to guess the user
    # This could be the first non-root user on the system
    ACTUAL_USER=$(getent passwd 1000 | cut -d: -f1)
    
    # If we couldn't find a user with UID 1000, use current $USER 
    # or fallback to a default
    if [ -z "$ACTUAL_USER" ]; then
        ACTUAL_USER=${USER:-"pi"}
    fi
fi

# Ask for confirmation of the user
read -p "Installing for user: $ACTUAL_USER. Is this correct? (y/n) " -n 1 -r USER_CONFIRM
echo
if [[ ! $USER_CONFIRM =~ ^[Yy]$ ]]; then
    read -p "Please enter the correct username: " ACTUAL_USER
    if [ -z "$ACTUAL_USER" ]; then
        echo "Error: No username provided. Exiting."
        exit 1
    fi
    
    # Verify user exists
    if ! id "$ACTUAL_USER" &>/dev/null; then
        echo "Error: User '$ACTUAL_USER' does not exist. Exiting."
        exit 1
    fi
fi

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Ask for installation directory
DEFAULT_PROJECT_DIR="/home/$ACTUAL_USER/zero_cam"
read -p "Enter installation directory [$DEFAULT_PROJECT_DIR]: " PROJECT_DIR
PROJECT_DIR=${PROJECT_DIR:-$DEFAULT_PROJECT_DIR}

# Confirm installation directory
echo "Installing to: $PROJECT_DIR"
read -p "Is this correct? (y/n) " -n 1 -r DIR_CONFIRM
echo
if [[ ! $DIR_CONFIRM =~ ^[Yy]$ ]]; then
    echo "Installation cancelled. Please run the script again with the desired path."
    exit 0
fi

# Create config directory for installation settings
CONFIG_DIR="/home/$ACTUAL_USER/.config/zero_cam"
mkdir -p "$CONFIG_DIR"

# Save installation settings
cat > "$CONFIG_DIR/install_config" << EOF
# Zero Cam Installation Configuration
INSTALL_DATE="$(date)"
INSTALL_USER="$ACTUAL_USER"
PROJECT_DIR="$PROJECT_DIR"
SCRIPT_VERSION="1.0.0"
EOF

# Ask for camera name (used for remote path and display)
read -p "Enter a name for this camera (e.g., garden_cam, front_door) [zero_cam]: " CAMERA_NAME
CAMERA_NAME=${CAMERA_NAME:-"zero_cam"}

# Check if this is an upgrade
if [ -d "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/config.json" ]; then
    echo "Existing installation detected at $PROJECT_DIR"
    read -p "Would you like to upgrade the existing installation? (y/n) " -n 1 -r UPGRADE_CONFIRM
    echo
    if [[ $UPGRADE_CONFIRM =~ ^[Yy]$ ]]; then
        # Backup existing config
        echo "Backing up existing configuration..."
        cp "$PROJECT_DIR/config.json" "$PROJECT_DIR/config.json.bak.$(date +%Y%m%d%H%M%S)"
        UPGRADE_MODE=true
    else
        echo "Installation cancelled to prevent overwriting existing setup."
        exit 0
    fi
else
    UPGRADE_MODE=false
fi

# Install required packages
echo "Installing required packages..."
apt-get update
apt-get install -y python3 python3-pip python3-picamera2 rclone dialog

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install --break-system-packages psutil python-dotenv

# Create project directory
echo "Creating project directory..."
mkdir -p $PROJECT_DIR

# Create directory structure
echo "Creating directory structure..."
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/images/temp" 
mkdir -p "$PROJECT_DIR/images/archive"

# Check if source and destination are the same
if [ "$SCRIPT_DIR" = "$PROJECT_DIR" ]; then
    echo "Source and destination directories are the same, skipping file copy"
else
    # Copy Python files
    echo "Copying Python files from $SCRIPT_DIR to $PROJECT_DIR"
    cp "$SCRIPT_DIR/main.py" "$PROJECT_DIR/"
    cp "$SCRIPT_DIR/camera.py" "$PROJECT_DIR/"
    cp "$SCRIPT_DIR/sync.py" "$PROJECT_DIR/"
    cp "$SCRIPT_DIR/file_manager.py" "$PROJECT_DIR/"
fi

# Function to configure the camera settings interactively
configure_camera() {
    # Default values - if upgrading, read from existing config
    if [ "$UPGRADE_MODE" = true ] && [ -f "$PROJECT_DIR/config.json" ]; then
        CAM_INTERVAL=$(grep -o '"interval": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "20")
        CAM_CAPTURES=$(grep -o '"captures": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "3")
        CAM_HFLIP=$(grep -o '"hflip": [a-z]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "false")
        CAM_VFLIP=$(grep -o '"vflip": [a-z]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "false")
        CAM_ROTATION=$(grep -o '"rotation": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "0")
        CAM_QUALITY=$(grep -o '"quality": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "35")
        CAM_WIDTH=$(grep -o '"width": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "2592")
        CAM_HEIGHT=$(grep -o '"height": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "1944")
    else
        CAM_INTERVAL=20
        CAM_CAPTURES=3
        CAM_HFLIP=false
        CAM_VFLIP=false
        CAM_ROTATION=0
        CAM_QUALITY=35
        CAM_WIDTH=2592
        CAM_HEIGHT=1944
    fi

    # Ask for camera settings
    echo "Camera Configuration:"
    echo "--------------------"
    
    read -p "Capture interval in seconds [$CAM_INTERVAL]: " NEW_INTERVAL
    CAM_INTERVAL=${NEW_INTERVAL:-$CAM_INTERVAL}
    
    read -p "Images to capture before sync [$CAM_CAPTURES]: " NEW_CAPTURES
    CAM_CAPTURES=${NEW_CAPTURES:-$CAM_CAPTURES}
    
    read -p "Flip image horizontally (true/false) [$CAM_HFLIP]: " NEW_HFLIP
    CAM_HFLIP=${NEW_HFLIP:-$CAM_HFLIP}
    
    read -p "Flip image vertically (true/false) [$CAM_VFLIP]: " NEW_VFLIP
    CAM_VFLIP=${NEW_VFLIP:-$CAM_VFLIP}
    
    read -p "Image rotation (0, 90, 180, 270) [$CAM_ROTATION]: " NEW_ROTATION
    CAM_ROTATION=${NEW_ROTATION:-$CAM_ROTATION}
    
    read -p "Image quality (1-100, lower is more compressed) [$CAM_QUALITY]: " NEW_QUALITY
    CAM_QUALITY=${NEW_QUALITY:-$CAM_QUALITY}
    
    read -p "Image width in pixels [$CAM_WIDTH]: " NEW_WIDTH
    CAM_WIDTH=${NEW_WIDTH:-$CAM_WIDTH}
    
    read -p "Image height in pixels [$CAM_HEIGHT]: " NEW_HEIGHT
    CAM_HEIGHT=${NEW_HEIGHT:-$CAM_HEIGHT}
    
    # Return the camera config as JSON
    cat << EOF
  "camera": {
    "name": "$CAMERA_NAME",
    "interval": $CAM_INTERVAL,
    "captures": $CAM_CAPTURES,
    "hflip": $CAM_HFLIP,
    "vflip": $CAM_VFLIP,
    "rotation": $CAM_ROTATION,
    "quality": $CAM_QUALITY,
    "width": $CAM_WIDTH,
    "height": $CAM_HEIGHT
  }
EOF
}

# Function to configure sync settings interactively
configure_sync() {
    # Default values - if upgrading, read from existing config
    if [ "$UPGRADE_MODE" = true ] && [ -f "$PROJECT_DIR/config.json" ]; then
        SYNC_REMOTE=$(grep -o '"remote_name": "[^"]*"' "$PROJECT_DIR/config.json" | cut -d'"' -f4 || echo "dropbox")
        SYNC_PATH=$(grep -o '"remote_path": "[^"]*"' "$PROJECT_DIR/config.json" | cut -d'"' -f4 || echo "$CAMERA_NAME")
        SYNC_MODE=$(grep -o '"operation_mode": "[^"]*"' "$PROJECT_DIR/config.json" | cut -d'"' -f4 || echo "copy")
        SYNC_LOGS=$(grep -o '"sync_logs": [a-z]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "true")
        SYNC_SHUTDOWN=$(grep -o '"sync_on_shutdown": [a-z]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "true")
    else
        SYNC_REMOTE="dropbox"
        SYNC_PATH="$CAMERA_NAME"
        SYNC_MODE="copy"
        SYNC_LOGS=true
        SYNC_SHUTDOWN=true
    fi

    # Ask for sync settings
    echo "Sync Configuration:"
    echo "-----------------"
    
    read -p "rclone remote name [$SYNC_REMOTE]: " NEW_REMOTE
    SYNC_REMOTE=${NEW_REMOTE:-$SYNC_REMOTE}
    
    read -p "Remote path (folder on $SYNC_REMOTE) [$SYNC_PATH]: " NEW_PATH
    SYNC_PATH=${NEW_PATH:-$SYNC_PATH}
    
    echo "Sync operation mode: copy (keep local files), move (delete after sync), sync (two-way sync)"
    read -p "Operation mode (copy/move/sync) [$SYNC_MODE]: " NEW_MODE
    SYNC_MODE=${NEW_MODE:-$SYNC_MODE}
    
    read -p "Sync log files (true/false) [$SYNC_LOGS]: " NEW_SYNC_LOGS
    SYNC_LOGS=${NEW_SYNC_LOGS:-$SYNC_LOGS}
    
    read -p "Sync on shutdown (true/false) [$SYNC_SHUTDOWN]: " NEW_SYNC_SHUTDOWN
    SYNC_SHUTDOWN=${NEW_SYNC_SHUTDOWN:-$SYNC_SHUTDOWN}
    
    # Return the sync config as JSON
    cat << EOF
  "sync": {
    "remote_name": "$SYNC_REMOTE",
    "remote_path": "$SYNC_PATH",
    "operation_mode": "$SYNC_MODE",
    "sync_logs": $SYNC_LOGS,
    "sync_on_shutdown": $SYNC_SHUTDOWN
  }
EOF
}

# Function to configure file management settings interactively
configure_file_management() {
    # Default values - if upgrading, read from existing config
    if [ "$UPGRADE_MODE" = true ] && [ -f "$PROJECT_DIR/config.json" ]; then
        ARCHIVE_DAYS=$(grep -o '"days_before_archive": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "2")
        RETENTION_DAYS=$(grep -o '"archive_retention_days": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "10")
        LOG_DAYS=$(grep -o '"log_retention_days": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "7")
        MIN_SPACE=$(grep -o '"min_free_space_mb": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "500")
    else
        ARCHIVE_DAYS=2
        RETENTION_DAYS=10
        LOG_DAYS=7
        MIN_SPACE=500
    fi

    # Ask for file management settings
    echo "File Management Configuration:"
    echo "----------------------------"
    
    read -p "Days before archiving images [$ARCHIVE_DAYS]: " NEW_ARCHIVE_DAYS
    ARCHIVE_DAYS=${NEW_ARCHIVE_DAYS:-$ARCHIVE_DAYS}
    
    read -p "Days to keep archived images [$RETENTION_DAYS]: " NEW_RETENTION_DAYS
    RETENTION_DAYS=${NEW_RETENTION_DAYS:-$RETENTION_DAYS}
    
    read -p "Days to keep log files [$LOG_DAYS]: " NEW_LOG_DAYS
    LOG_DAYS=${NEW_LOG_DAYS:-$LOG_DAYS}
    
    read -p "Minimum free disk space in MB [$MIN_SPACE]: " NEW_MIN_SPACE
    MIN_SPACE=${NEW_MIN_SPACE:-$MIN_SPACE}
    
    # Return the file management config as JSON
    cat << EOF
  "file_management": {
    "days_before_archive": $ARCHIVE_DAYS,
    "archive_retention_days": $RETENTION_DAYS,
    "log_retention_days": $LOG_DAYS,
    "min_free_space_mb": $MIN_SPACE
  }
EOF
}

# Function to configure safe mode settings
configure_safe_mode() {
    # Default values - if upgrading, read from existing config
    if [ "$UPGRADE_MODE" = true ] && [ -f "$PROJECT_DIR/config.json" ]; then
        SAFE_ENABLED=$(grep -o '"enabled": [a-z]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "true")
        SAFE_DELAY=$(grep -o '"delay_seconds": [0-9]*' "$PROJECT_DIR/config.json" | awk '{print $2}' || echo "180")
        SAFE_MESSAGE=$(grep -o '"message": "[^"]*"' "$PROJECT_DIR/config.json" | cut -d'"' -f4 || echo "Safe mode: Waiting for potential remote intervention...")
    else
        SAFE_ENABLED=true
        SAFE_DELAY=180
        SAFE_MESSAGE="Safe mode: Waiting for potential remote intervention..."
    fi

    # Ask for safe mode settings
    echo "Safe Mode Configuration:"
    echo "----------------------"
    echo "Safe mode provides a startup delay for recovery purposes."
    echo "This gives you time to connect remotely and stop the service if needed."
    
    read -p "Enable safe mode (true/false) [$SAFE_ENABLED]: " NEW_SAFE_ENABLED
    SAFE_ENABLED=${NEW_SAFE_ENABLED:-$SAFE_ENABLED}
    
    if [[ $SAFE_ENABLED =~ ^[Tt]rue$ ]]; then
        read -p "Delay in seconds [$SAFE_DELAY]: " NEW_SAFE_DELAY
        SAFE_DELAY=${NEW_SAFE_DELAY:-$SAFE_DELAY}
        
        read -p "Custom message (press ENTER for default): " NEW_SAFE_MESSAGE
        SAFE_MESSAGE=${NEW_SAFE_MESSAGE:-$SAFE_MESSAGE}
    fi
    
    # Return the safe mode config as JSON
    cat << EOF
  "safe_mode": {
    "enabled": $SAFE_ENABLED,
    "delay_seconds": $SAFE_DELAY,
    "message": "$SAFE_MESSAGE"
  }
EOF
}

# Function to configure logging settings
configure_logging() {
    # Default values - if upgrading, read from existing config
    if [ "$UPGRADE_MODE" = true ] && [ -f "$PROJECT_DIR/config.json" ]; then
        LOG_LEVEL=$(grep -o '"log_level": "[^"]*"' "$PROJECT_DIR/config.json" | cut -d'"' -f4 || echo "INFO")
    else
        LOG_LEVEL="INFO"
    fi

    # Ask for logging settings
    echo "Logging Configuration:"
    echo "---------------------"
    
    echo "Available log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL"
    read -p "Log level [$LOG_LEVEL]: " NEW_LOG_LEVEL
    LOG_LEVEL=${NEW_LOG_LEVEL:-$LOG_LEVEL}
    
    # Return the logging config
    echo "  \"log_level\": \"$LOG_LEVEL\""
}

# Create or update configuration
if [ "$UPGRADE_MODE" = true ]; then
    echo "Updating configuration..."
else
    echo "Creating new configuration..."
fi

echo "Let's configure your Zero Cam system"
echo "You'll be asked for various settings. Press ENTER to accept defaults."
echo

# Offer simple or advanced configuration
read -p "Would you like to use simple (s) or advanced (a) configuration? [s]: " -n 1 -r CONFIG_MODE
echo
CONFIG_MODE=${CONFIG_MODE:-"s"}

if [[ $CONFIG_MODE =~ ^[Ss]$ ]]; then
    # Simple mode - just a few key settings
    read -p "Camera capture interval in seconds [20]: " SIMPLE_INTERVAL
    SIMPLE_INTERVAL=${SIMPLE_INTERVAL:-20}
    
    read -p "Flip camera image (for cameras installed upside down)? (y/n) [n]: " -n 1 -r SIMPLE_FLIP
    echo
    if [[ $SIMPLE_FLIP =~ ^[Yy]$ ]]; then
        SIMPLE_HFLIP=true
        SIMPLE_VFLIP=true
    else
        SIMPLE_HFLIP=false
        SIMPLE_VFLIP=false
    fi
    
    read -p "Days to keep images before deletion [10]: " SIMPLE_RETENTION
    SIMPLE_RETENTION=${SIMPLE_RETENTION:-10}
    
    echo "Safe mode provides a startup delay for recovery purposes."
    read -p "Enable safe mode (recommended for new installations)? (y/n) [y]: " -n 1 -r SIMPLE_SAFE_MODE
    echo
    if [[ $SIMPLE_SAFE_MODE =~ ^[Nn]$ ]]; then
        SIMPLE_SAFE_ENABLED=false
        SIMPLE_SAFE_DELAY=0
    else
        SIMPLE_SAFE_ENABLED=true
        SIMPLE_SAFE_DELAY=180
    fi
    
    # Create simple config
    cat > "$PROJECT_DIR/config.json" << EOF
{
  "camera": {
    "name": "$CAMERA_NAME",
    "interval": $SIMPLE_INTERVAL,
    "captures": 3,
    "hflip": $SIMPLE_HFLIP,
    "vflip": $SIMPLE_VFLIP,
    "rotation": 0,
    "quality": 35,
    "width": 2592,
    "height": 1944
  },
  "sync": {
    "remote_name": "dropbox",
    "remote_path": "$CAMERA_NAME",
    "operation_mode": "copy",
    "sync_logs": true,
    "sync_on_shutdown": true
  },
  "file_management": {
    "days_before_archive": 2,
    "archive_retention_days": $SIMPLE_RETENTION,
    "log_retention_days": 7,
    "min_free_space_mb": 500
  },
  "safe_mode": {
    "enabled": $SIMPLE_SAFE_ENABLED,
    "delay_seconds": $SIMPLE_SAFE_DELAY,
    "message": "Safe mode: Waiting for potential remote intervention..."
  },
  "log_level": "INFO",
  "system": {
    "installation_path": "$PROJECT_DIR",
    "user": "$ACTUAL_USER",
    "camera_name": "$CAMERA_NAME"
  }
}
EOF
else
    # Advanced mode - configure all settings
    # Collect configurations
    CAMERA_CONFIG=$(configure_camera)
    SYNC_CONFIG=$(configure_sync)
    FILE_CONFIG=$(configure_file_management)
    SAFE_MODE_CONFIG=$(configure_safe_mode)
    LOG_CONFIG=$(configure_logging)
    
    # Create configuration file
    cat > "$PROJECT_DIR/config.json" << EOF
{
$CAMERA_CONFIG,
$SYNC_CONFIG,
$FILE_CONFIG,
$SAFE_MODE_CONFIG,
$LOG_CONFIG,
  "system": {
    "installation_path": "$PROJECT_DIR",
    "user": "$ACTUAL_USER",
    "camera_name": "$CAMERA_NAME"
  }
}
EOF
fi

echo "Configuration saved to $PROJECT_DIR/config.json"

# Make main.py executable
chmod +x "$PROJECT_DIR/main.py"

# Configure rclone if not already set up
if ! rclone listremotes | grep -q "dropbox:"; then
    echo "rclone not configured for Dropbox."
    read -p "Would you like to configure rclone now? (y/n) " -n 1 -r RCLONE_SETUP
    echo
    if [[ $RCLONE_SETUP =~ ^[Yy]$ ]]; then
        echo "===== RCLONE CONFIGURATION ====="
        echo "You'll need to follow these steps:"
        echo "1. Select 'n' for New remote"
        echo "2. Enter 'dropbox' (or your preferred name) for the name"
        echo "3. Select the number for 'Dropbox' as the storage type"
        echo "4. Accept defaults for most options"
        echo "5. Select 'y' to use auto config, then authorise in your browser"
        echo "===============================\n"
        
        read -p "Press ENTER to continue to rclone config..."
        rclone config
    else
        echo "Please run 'rclone config' later to set up Dropbox sync."
        echo "Instructions: https://rclone.org/dropbox/"
    fi
fi

# Create manage script for easy administration
cat > "$PROJECT_DIR/manage.sh" << EOF
#!/bin/bash
# Zero Cam Management Script

# Variables
SERVICE_NAME="zero-cam"
CONFIG_FILE="$PROJECT_DIR/config.json"

# Functions
check_status() {
    systemctl status \$SERVICE_NAME
}

view_logs() {
    journalctl -u \$SERVICE_NAME -f
}

restart_service() {
    systemctl restart \$SERVICE_NAME
    echo "Service restarted"
}

edit_config() {
    # Use the default editor, fallback to nano
    \${EDITOR:-nano} \$CONFIG_FILE
    
    # Ask to restart service
    read -p "Would you like to restart the service to apply changes? (y/n) " -n 1 -r
    echo
    if [[ \$REPLY =~ ^[Yy]$ ]]; then
        restart_service
    fi
}

manual_capture() {
    echo "Taking a manual capture..."
    # Use python to call the camera capture function
    python3 -c "import sys; sys.path.append('$PROJECT_DIR'); from camera import Camera; import json; config = json.load(open('$CONFIG_FILE')); cam = Camera(config, '$PROJECT_DIR/images/temp'); print(cam.capture_image())"
}

manual_sync() {
    echo "Performing manual sync..."
    # Use python to call the sync function
    python3 -c "import sys; sys.path.append('$PROJECT_DIR'); from sync import DropboxSync; import json; config = json.load(open('$CONFIG_FILE')); sync = DropboxSync(config, '$PROJECT_DIR/images/temp', '$PROJECT_DIR/images/archive', '$PROJECT_DIR/logs'); sync.sync_temp_and_move(); sync.sync_logs_directory()"
}

toggle_safe_mode() {
    echo "Current safe mode configuration:"
    grep -A 4 '"safe_mode"' \$CONFIG_FILE
    echo
    read -p "Enable (e) or disable (d) safe mode? " -n 1 -r
    echo
    if [[ \$REPLY =~ ^[Ee]$ ]]; then
        # Enable safe mode
        sed -i 's/"enabled": false/"enabled": true/' \$CONFIG_FILE
        echo "Safe mode enabled"
    elif [[ \$REPLY =~ ^[Dd]$ ]]; then
        # Disable safe mode
        sed -i 's/"enabled": true/"enabled": false/' \$CONFIG_FILE
        echo "Safe mode disabled"
    else
        echo "No changes made"
        return
    fi
    
    read -p "Would you like to restart the service to apply changes? (y/n) " -n 1 -r
    echo
    if [[ \$REPLY =~ ^[Yy]$ ]]; then
        restart_service
    fi
}

# Menu
clear
echo "Zero Cam Management"
echo "==================="
echo "1. Check service status"
echo "2. View logs"
echo "3. Restart service"
echo "4. Edit configuration"
echo "5. Take manual capture"
echo "6. Perform manual sync"
echo "7. Toggle safe mode"
echo "0. Exit"
echo

read -p "Select an option: " OPTION

case \$OPTION in
    1) check_status ;;
    2) view_logs ;;
    3) restart_service ;;
    4) edit_config ;;
    5) manual_capture ;;
    6) manual_sync ;;
    7) toggle_safe_mode ;;
    0) exit 0 ;;
    *) echo "Invalid option" ;;
esac
EOF

# Make management script executable
chmod +x "$PROJECT_DIR/manage.sh"

# Create symlink for easy access
ln -sf "$PROJECT_DIR/manage.sh" "/home/$ACTUAL_USER/zero_cam-manage"
chown $ACTUAL_USER:$ACTUAL_USER "/home/$ACTUAL_USER/zero_cam-manage"

# Set correct permissions
echo "Setting permissions..."
chown -R $ACTUAL_USER:$ACTUAL_USER "$PROJECT_DIR"
chown -R $ACTUAL_USER:$ACTUAL_USER "$CONFIG_DIR"

# Install systemd service
echo "Installing systemd service..."
cat > /etc/systemd/system/zero-cam.service << EOF
[Unit]
Description=Raspberry Pi Zero Camera System
After=network.target

[Service]
ExecStart=/usr/bin/python3 $PROJECT_DIR/main.py
WorkingDirectory=$PROJECT_DIR
StandardOutput=inherit
StandardError=inherit
Restart=always
User=$ACTUAL_USER

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Ask to enable service
read -p "Enable zero-cam service to start at boot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl enable zero-cam.service
    echo "Service enabled to start at boot"
else
    echo "Service not enabled to start at boot"
fi

# Ask to start service now
read -p "Start zero-cam service now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl start zero-cam.service
    echo "Service started"
    echo "You can check the status with: sudo systemctl status zero-cam"
else
    echo "Service not started"
fi

echo "================================================================="
echo "Installation complete!"
echo "================================================================="
echo ""
echo "SAFE MODE INFORMATION:"
echo "- Safe mode is now configured in your system"
echo "- When enabled, the service waits 3 minutes before starting"
echo "- This gives you time to connect remotely if there are issues"
echo "- Use ~/zero_cam-manage option 7 to toggle safe mode on/off"
echo ""
echo "QUICK MANAGEMENT:"
echo "- Run ~/zero_cam-manage for quick administration"
echo ""
echo "SERVICE MANAGEMENT:"
echo "- Start: sudo systemctl start zero-cam"
echo "- Stop: sudo systemctl stop zero-cam"
echo "- Restart: sudo systemctl restart zero-cam"
echo "- Status: sudo systemctl status zero-cam"
echo "- View logs: sudo journalctl -u zero-cam -f"
echo ""
echo "CONFIGURATION:"
echo "- Configuration file: $PROJECT_DIR/config.json"
echo "- Log directory: $PROJECT_DIR/logs"
echo "- Images directory structure:"
echo "  - $PROJECT_DIR/images/temp (temporary storage before sync)"
echo "  - $PROJECT_DIR/images/archive (dated storage of synced images)"
echo ""
echo "RECOVERY INFORMATION:"
if grep -q '"enabled": true' "$PROJECT_DIR/config.json" 2>/dev/null; then
    echo "- Safe mode is ENABLED - service will wait 3 minutes on startup"
    echo "- During this time you can SSH in and stop the service if needed"
    echo "- Press Ctrl+C during safe mode countdown to stop immediately"
else
    echo "- Safe mode is DISABLED - service starts immediately"
    echo "- Enable safe mode via ~/zero_cam-manage if needed for recovery"
fi
echo ""
echo "TROUBLESHOOTING:"
echo "- Check service status: sudo systemctl status zero-cam"
echo "- View recent logs: sudo journalctl -u zero-cam -n 50"
echo "- Stop problematic service: sudo systemctl stop zero-cam"
echo "- Edit config safely: ~/zero_cam-manage (option 4)"
echo "- Test camera manually: ~/zero_cam-manage (option 5)"
echo "- Test sync manually: ~/zero_cam-manage (option 6)"
echo ""
echo "NETWORK CONFIGURATION:"
echo "- Configure rclone: rclone config"
echo "- Test rclone connection: rclone lsf dropbox:"
echo "- View rclone remotes: rclone listremotes"
echo ""
echo "SYSTEM INFORMATION:"
echo "- Installation user: $ACTUAL_USER"
echo "- Camera name: $CAMERA_NAME"
echo "- Installation directory: $PROJECT_DIR"
echo "- Config backup location: $PROJECT_DIR/config.json.bak.*"
echo ""
echo "NEXT STEPS:"
echo "1. Configure rclone if you haven't already (rclone config)"
echo "2. Test the camera: ~/zero_cam-manage (option 5)"
echo "3. Test the sync: ~/zero_cam-manage (option 6)"
echo "4. Monitor logs: sudo journalctl -u zero-cam -f"
echo ""
echo "For detailed help and configuration options, see:"
echo "- Configuration guide: $PROJECT_DIR/config_guide.md (if available)"
echo "- Management script: ~/zero_cam-manage"
echo ""
echo "================================================================="