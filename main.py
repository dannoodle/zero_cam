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
safe_mode_interrupted = False

# Base directories
BASE_DIR = Path(__file__).parent
IMAGES_DIR = os.path.join(BASE_DIR, "images")
TEMP_DIR = os.path.join(IMAGES_DIR, "temp")  # New temp directory
ARCHIVE_DIR = os.path.join(IMAGES_DIR, "archive")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

def setup_logging(log_level="INFO"):
    """Configure logging for the application."""
    try:
        # Ensure logs directory exists
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        # Get camera name from config if available, otherwise default
        camera_name = "zero_cam"
        try:
            if 'camera' in config and 'name' in config['camera']:
                camera_name = config['camera']['name']
        except Exception:
            pass
        
        # Generate log filename with date and camera name
        log_date = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(LOGS_DIR, f"{camera_name}_{log_date}.log")
        
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
        "safe_mode": {
            "enabled": True,
            "delay_seconds": 180,
            "message": "Safe mode: Waiting for potential remote intervention..."
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
    global running, safe_mode_interrupted
    print(f"Received signal {sig}, shutting down gracefully...")
    running = False
    safe_mode_interrupted = True

def safe_mode_signal_handler(sig, frame):
    """Handle signals during safe mode - allows immediate exit."""
    global safe_mode_interrupted
    print(f"Safe mode interrupted by signal {sig}")
    safe_mode_interrupted = True

def safe_mode_delay(config, logger):
    """
    Implement safe mode delay with countdown and ability to interrupt.
    Returns True if the delay completed normally, False if interrupted.
    """
    safe_config = config.get('safe_mode', {})
    
    # Check if safe mode is enabled
    if not safe_config.get('enabled', True):
        logger.info("Safe mode disabled in configuration")
        return True
    
    delay_seconds = safe_config.get('delay_seconds', 180)
    message = safe_config.get('message', "Safe mode: Waiting for potential remote intervention...")
    
    logger.warning("=== SAFE MODE ACTIVATED ===")
    logger.warning(message)
    logger.warning(f"System will start normally in {delay_seconds} seconds")
    logger.warning("Send SIGINT (Ctrl+C) or SIGTERM to exit immediately")
    logger.warning("===========================")
    
    # Also print to console for immediate visibility
    print("\n" + "="*60)
    print("           SAFE MODE ACTIVATED")
    print("="*60)
    print(f"System starting in {delay_seconds} seconds...")
    print("Press Ctrl+C to stop the service immediately")
    print("This gives you time to connect remotely if needed")
    print("="*60 + "\n")
    
    # Set up signal handler for safe mode (allows immediate exit)
    old_sigint_handler = signal.signal(signal.SIGINT, safe_mode_signal_handler)
    old_sigterm_handler = signal.signal(signal.SIGTERM, safe_mode_signal_handler)
    
    try:
        # Countdown with regular updates
        for remaining in range(delay_seconds, 0, -1):
            if safe_mode_interrupted:
                logger.info("Safe mode interrupted - exiting immediately")
                print("Safe mode interrupted - service stopping")
                return False
            
            # Log every 30 seconds and for the last 10 seconds
            if remaining % 30 == 0 or remaining <= 10:
                logger.info(f"Safe mode: {remaining} seconds remaining")
                print(f"Starting in {remaining} seconds... (Ctrl+C to stop)")
            
            time.sleep(1)
        
        # Restore original signal handlers
        signal.signal(signal.SIGINT, old_sigint_handler)
        signal.signal(signal.SIGTERM, old_sigterm_handler)
        
        logger.info("Safe mode completed - starting normal operation")
        print("Safe mode completed - starting camera system\n")
        return True
        
    except Exception as e:
        logger.error(f"Error during safe mode: {str(e)}")
        # Restore signal handlers even if there was an error
        signal.signal(signal.SIGINT, old_sigint_handler)
        signal.signal(signal.SIGTERM, old_sigterm_handler)
        return False

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
    
    # Load configuration first
    config = load_config()
    
    # Set up logging
    logger = setup_logging(config.get('log_level', 'INFO'))
    logger.info("Starting Raspberry Pi Zero Camera System")
    
    try:
        # Execute safe mode delay if configured
        if not safe_mode_delay(config, logger):
            logger.info("Exiting due to safe mode interruption")
            return 0
        
        # If we get here, safe mode completed or was disabled
        if safe_mode_interrupted:
            logger.info("Service stopped during safe mode")
            return 0
        
        # Log actual paths being used
        logger.info(f"BASE_DIR: {BASE_DIR}")
        logger.info(f"IMAGES_DIR: {IMAGES_DIR}")
        logger.info(f"TEMP_DIR: {TEMP_DIR}")
        logger.info(f"ARCHIVE_DIR: {ARCHIVE_DIR}")
        logger.info(f"LOGS_DIR: {LOGS_DIR}")
        
        # Ensure all directories exist
        for directory in [TEMP_DIR, ARCHIVE_DIR, LOGS_DIR]:
            logger.info(f"Ensuring directory exists: {directory}")
            os.makedirs(directory, exist_ok=True)
            
        # Register signal handlers for graceful shutdown (normal operation)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize components
        logger.info("Initialising system components...")
        
        camera = Camera(config, TEMP_DIR)
        sync = DropboxSync(config, TEMP_DIR, ARCHIVE_DIR, LOGS_DIR)
        file_manager = FileManager(config, ARCHIVE_DIR, LOGS_DIR)
        
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
                        logger.info("Starting sync process...")
                        # Sync temp directory to Dropbox and move files to archive
                        sync_success = sync.sync_temp_and_move()
                        
                        if sync_success:
                            logger.info("Sync and file move successful, resetting capture count")
                            camera.reset_capture_count()
                        else:
                            logger.warning("Sync or move operation failed, not resetting capture count")
                        
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