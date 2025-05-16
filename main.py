#!/usr/bin/env python3
"""
Raspberry Pi Zero Camera System

A simplified remote camera system that automatically captures images at regular intervals
and syncs them to Dropbox with basic error handling and file management.
"""

import os
import json
import time
import signal
import sys
import logging
import traceback
from datetime import datetime, date
from pathlib import Path

# Import modules
from camera import Camera
from sync import DropboxSync
from file_manager import FileManager

# Global variables
running = True

# Base directories
BASE_DIR = Path(__file__).parent
IMAGES_DIR = os.path.join(BASE_DIR, "images")
CURRENT_DIR = os.path.join(IMAGES_DIR, "current")
TEMP_DIR = os.path.join(IMAGES_DIR, "temp")  # New temp directory
ARCHIVE_DIR = os.path.join(IMAGES_DIR, "archive")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

def setup_logging(log_level="INFO"):
    """Configure logging for the application."""
    try:
        # Ensure logs directory exists
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        # Generate log filename with date
        log_date = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(LOGS_DIR, f"pi_cam_{log_date}.log")
        
        # Get log level
        log_level_value = getattr(logging, log_level.upper(), logging.INFO)
        
        # Configure root logger
        logging.basicConfig(
            level=log_level_value,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Logging initialised at level {log_level}")
        logger.info(f"Log file: {log_file}")
        
        return logger
        
    except Exception as e:
        print(f"Error setting up logging: {str(e)}")
        # Fall back to basic configuration
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to set up file logging: {str(e)}")
        return logger

def load_config():
    """Load configuration from file with defaults."""
    # Default configuration
    default_config = {
        "camera": {
            "interval": 20,
            "captures": 3,
            "hflip": False,
            "vflip": False,
            "rotation": 0,
            "quality": 35,
            "width": 2592,
            "height": 1944
        },
        "sync": {
            "remote_name": "dropbox",
            "remote_path": "pi_cam",
            "sync_logs": True,
            "sync_on_shutdown": True
        },
        "file_management": {
            "days_before_archive": 2,
            "archive_retention_days": 10,
            "log_retention_days": 7,
            "min_free_space_mb": 500
        },
        "log_level": "INFO"
    }
    
    config_file = os.path.join(BASE_DIR, "config.json")
    
    # Create default config if none exists
    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        return default_config
    
    # Load config from file
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            
        # Ensure all required sections exist
        for section in default_config:
            if section not in config:
                config[section] = default_config[section]
            elif isinstance(default_config[section], dict):
                for key in default_config[section]:
                    if key not in config[section]:
                        config[section][key] = default_config[section][key]
                        
        return config
    except Exception as e:
        print(f"Error loading configuration: {str(e)}")
        return default_config

def signal_handler(sig, frame):
    """Handle shutdown signals."""
    global running
    print(f"Received signal {sig}, shutting down gracefully...")
    running = False

def check_network_status(test_host="8.8.8.8"):
    """Check network connectivity by pinging Google's DNS."""
    try:
        import subprocess
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '2', test_host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def main():
    """Main application entry point."""
    global running
    
    # Load configuration
    config = load_config()
    
    # Set up logging
    logger = setup_logging(config.get('log_level', 'INFO'))
    logger.info("Starting Raspberry Pi Zero Camera System")
    
    try:
        # Ensure all directories exist
        for directory in [CURRENT_DIR, TEMP_DIR, ARCHIVE_DIR, LOGS_DIR]:
            os.makedirs(directory, exist_ok=True)
            
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize components
        logger.info("Initialising system components...")
        
        camera = Camera(config, CURRENT_DIR, TEMP_DIR)
        sync = DropboxSync(config, CURRENT_DIR, TEMP_DIR, LOGS_DIR)
        file_manager = FileManager(config, CURRENT_DIR, ARCHIVE_DIR, LOGS_DIR)
        
        # Check camera connection
        if not camera.check_camera():
            logger.error("Camera not detected. Check connections and try again.")
            return 1
        
        # Initial file maintenance
        file_manager.run_daily_maintenance()
        
        # Main variables
        interval = config['camera'].get('interval', 20)
        last_date = date.today()
        
        logger.info(f"Starting main capture loop (interval: {interval}s)")
        
        # Main capture loop
        while running:
            try:
                # Check for date change
                current_date = date.today()
                if current_date != last_date:
                    logger.info(f"Date changed from {last_date} to {current_date}")
                    last_date = current_date
                    file_manager.ensure_today_dir()
                    file_manager.run_daily_maintenance()
                
                # Check disk space
                if not file_manager.check_disk_space():
                    logger.error("Disk space critically low. Consider manual cleanup.")
                
                # Capture image
                image_path = camera.capture_image()
                
                # Sync to Dropbox if needed or if there was an error
                if camera.should_sync() or image_path is None:
                    # Check network before attempting sync
                    if check_network_status():
                        # Sync temp directory to Dropbox and move files to archive
                        if sync.sync_temp_and_move():
                            camera.reset_capture_count()
                        else:
                            logger.warning("Sync or move failed, not resetting capture count")
                        
                        # Also sync logs if configured
                        if config['sync'].get('sync_logs', True):
                            sync.sync_logs_directory()
                    else:
                        logger.warning("Network unavailable, skipping sync")
                
                # Sleep until next capture
                if running:
                    time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                logger.error(traceback.format_exc())
                
                # Wait before retrying
                if running:
                    time.sleep(5)
        
        # Perform final sync if configured
        if config['sync'].get('sync_on_shutdown', True):
            logger.info("Performing final sync before shutdown")
            try:
                if check_network_status():
                    # Final sync of temp directory and logs
                    sync.sync_temp_and_move()
                    if config['sync'].get('sync_logs', True):
                        sync.sync_logs_directory()
                else:
                    logger.warning("Network unavailable, skipping final sync")
            except Exception as e:
                logger.error(f"Error during final sync: {str(e)}")
        
        # Log shutdown message
        logger.info("Raspberry Pi Zero Camera System shutting down")
        return 0
        
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}")
        logger.critical(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main())