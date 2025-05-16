#!/bin/bash
# Simple Installation script for Raspberry Pi Zero Camera System

set -e

# Display banner
echo "=================================================="
echo "    Raspberry Pi Zero Camera System Installer     "
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

echo "Installing for user: $ACTUAL_USER"

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="/home/noodle/zero_cam"
echo "Installing to: $PROJECT_DIR"

# Install required packages
echo "Installing required packages..."
apt-get update
apt-get install -y python3 python3-pip python3-picamera2 rclone

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

# Copy Python files
cp "$SCRIPT_DIR/main.py" "$PROJECT_DIR/"
cp "$SCRIPT_DIR/camera.py" "$PROJECT_DIR/"
cp "$SCRIPT_DIR/sync.py" "$PROJECT_DIR/"
cp "$SCRIPT_DIR/file_manager.py" "$PROJECT_DIR/"

# Copy config if it exists, otherwise create default
if [ -f "$SCRIPT_DIR/config.json" ]; then
    cp "$SCRIPT_DIR/config.json" "$PROJECT_DIR/"
else
    # Create default configuration
    echo "Creating default configuration..."
    cat > "$PROJECT_DIR/config.json" << EOF
{
  "camera": {
    "interval": 20,
    "captures": 3,
    "hflip": false,
    "vflip": false,
    "rotation": 0,
    "quality": 35,
    "width": 2592,
    "height": 1944
  },
  "sync": {
    "remote_name": "dropbox",
    "remote_path": "zero_cam",
    "sync_logs": true,
    "sync_on_shutdown": true
  },
  "file_management": {
    "days_before_archive": 2,
    "archive_retention_days": 10,
    "log_retention_days": 7,
    "min_free_space_mb": 500
  },
  "log_level": "INFO"
}
EOF
fi

# Make main.py executable
chmod +x "$PROJECT_DIR/main.py"

# Configure rclone if not already set up
if ! rclone listremotes | grep -q "dropbox:"; then
    echo "rclone not configured for Dropbox. Please run 'rclone config' to set it up."
    echo "Instructions: https://rclone.org/dropbox/"
    
    read -p "Would you like to configure rclone now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Running rclone config..."
        echo "Please follow the prompts to set up a new remote named 'dropbox'"
        rclone config
    fi
fi

# Set correct permissions
echo "Setting permissions..."
chown -R $ACTUAL_USER:$ACTUAL_USER "$PROJECT_DIR"

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

echo "Installation complete!"
echo ""
echo "To manage the service:"
echo "- Start: sudo systemctl start zero-cam"
echo "- Stop: sudo systemctl stop zero-cam"
echo "- Restart: sudo systemctl restart zero-cam"
echo "- Status: sudo systemctl status zero-cam"
echo "- View logs: sudo journalctl -u zero-cam -f"
echo ""
echo "Configuration file: $PROJECT_DIR/config.json"
echo "Log directory: $PROJECT_DIR/logs"
echo "Images directory structure:"
echo "- $PROJECT_DIR/images/temp (temporary storage before sync)"
echo "- $PROJECT_DIR/images/current (daily sorted storage)"
echo "- $PROJECT_DIR/images/archive (older archives)"