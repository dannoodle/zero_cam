#!/usr/bin/env python3
"""
Camera module for Raspberry Pi Zero Camera System.
Handles image capture using rpicam-still.
"""

import os
import subprocess
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

class Camera:
    """Simple camera controller for capturing images."""
    
    def __init__(self, config, temp_dir):
        """Initialize camera with configuration settings."""
        self.config = config['camera']
        self.temp_dir = temp_dir
        self.capture_count = 0
        self.captures_before_sync = self.config.get('captures', 3)
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)

    def get_image_filename(self):
        """Generate a timestamped filename for an image."""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        # Save to temp directory
        return os.path.join(self.temp_dir, f"img_{timestamp}.jpg")
    
    def capture_image(self):
        """Capture a single image using rpicam-still."""
        try:
            # Always save to temp directory initially
            filename = self.get_image_filename(temp=True)
            
            # Build command with parameters
            cmd = [
                "rpicam-still",
                "-o", filename,
                "--quality", str(self.config.get('quality', 35)),
                "--width", str(self.config.get('width', 2592)),
                "--height", str(self.config.get('height', 1944)),
                "-n"  # Skip preview window
            ]
            
            # Add optional parameters if enabled
            rotation = self.config.get('rotation', 0)
            if rotation != 0:
                cmd.extend(["--rotation", str(rotation)])
            if self.config.get('hflip', False):
                cmd.append("--hflip")
            if self.config.get('vflip', False):
                cmd.append("--vflip")
            
            # Execute the capture command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Camera capture failed: {result.stderr}")
                return None
            
            # Verify file was created
            if not os.path.exists(filename):
                logger.error(f"Image file not created: {filename}")
                return None
                
            file_size = os.path.getsize(filename)
            logger.info(f"Image captured: {filename} ({file_size} bytes)")
            
            # Increment capture counter
            self.capture_count += 1
            
            return filename
        
        except subprocess.TimeoutExpired:
            logger.error("Camera capture timed out")
            return None
        except Exception as e:
            logger.error(f"Error capturing image: {str(e)}")
            return None
    
    def should_sync(self):
        """Check if it's time to sync based on capture count."""
        return self.capture_count >= self.captures_before_sync
    
    def reset_capture_count(self):
        """Reset the capture counter after syncing."""
        self.capture_count = 0
    
    def check_camera(self):
        """Check if camera is connected and functioning."""
        try:
            # Use rpicam-hello to check for available cameras
            result = subprocess.run(
                ['rpicam-hello', '--list-cameras'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and "Available cameras" in result.stdout:
                logger.debug("Camera detected")
                return True
            else:
                logger.warning("Camera not detected")
                return False
                
        except Exception as e:
            logger.error(f"Error checking camera: {str(e)}")
            return False