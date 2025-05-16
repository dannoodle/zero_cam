#!/usr/bin/env python3
"""
Dropbox synchronisation module for Raspberry Pi Zero Camera System.
Handles file transfer between local system and Dropbox using rclone.
"""

import os
import subprocess
import logging
import shutil
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DropboxSync:
    """Handles file transfer with Dropbox using rclone."""
    
    def __init__(self, config, current_dir, temp_dir, logs_dir):
        """Initialize with configuration settings."""
        self.config = config['sync']
        self.current_dir = current_dir
        self.temp_dir = temp_dir
        self.logs_dir = logs_dir
        
        self.remote_name = self.config.get('remote_name', 'dropbox')
        self.remote_path = self.config.get('remote_path', 'pi_cam')
        self.sync_logs = self.config.get('sync_logs', True)
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Check if rclone is configured
        self._check_rclone_config()
    
    def _check_rclone_config(self):
        """Verify that rclone is properly configured with the remote."""
        try:
            # Check if rclone is installed
            result = subprocess.run(
                ["rclone", "--version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.error("Failed to run rclone. Is it installed?")
                return False
            
            # Check if the configured remote exists
            result = subprocess.run(
                ["rclone", "listremotes"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.error("Failed to list rclone remotes")
                return False
            
            remotes = result.stdout.splitlines()
            remote_full = f"{self.remote_name}:"
            
            if remote_full not in remotes:
                logger.error(f"Remote '{self.remote_name}:' not found in rclone configuration")
                logger.error("Available remotes: " + ", ".join(remotes))
                logger.error("Please run 'rclone config' to set up the Dropbox remote")
                return False
                
            logger.info(f"Rclone configured with remote: {self.remote_name}:")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking rclone configuration")
            return False
        except Exception as e:
            logger.error(f"Error checking rclone configuration: {str(e)}")
            return False
    
    def sync_temp_and_move(self):
        """
        Sync only the temporary directory to Dropbox and 
        then move files to the daily directory.
        """
        try:
            # Skip if the temp directory is empty
            if not os.path.exists(self.temp_dir) or not os.listdir(self.temp_dir):
                logger.info("No images in temp directory to sync")
                return True
                
            # Sync the temp directory to Dropbox
            remote_path = f"{self.remote_name}:{self.remote_path}/latest"
            logger.info(f"Transferring new images from temp to {remote_path}")
            
            # Use copy operation for the temp directory
            cmd = [
                "rclone", 
                "copy",
                self.temp_dir, 
                remote_path,
                "--progress"
            ]
            
            # Execute rclone command
            result = subprocess.run(
                cmd,
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Transfer failed: {result.stderr}")
                return False
            
            logger.info(f"Transfer completed successfully: {self.temp_dir} → {remote_path}")
            
            # Now move all files from temp to daily directory
            today = datetime.now().strftime("%Y-%m-%d")
            daily_dir = os.path.join(self.current_dir, today)
            os.makedirs(daily_dir, exist_ok=True)
            
            move_count = 0
            for filename in os.listdir(self.temp_dir):
                src_file = os.path.join(self.temp_dir, filename)
                dst_file = os.path.join(daily_dir, filename)
                
                if os.path.isfile(src_file):
                    shutil.move(src_file, dst_file)
                    move_count += 1
            
            logger.info(f"Moved {move_count} files from temp to daily directory")
            return True
            
        except Exception as e:
            logger.error(f"Error in sync_temp_and_move: {str(e)}")
            return False
    
    def sync_logs_directory(self):
        """Transfer log files to Dropbox if enabled."""
        if not self.sync_logs:
            return True
            
        try:
            if not os.path.exists(self.logs_dir) or not os.listdir(self.logs_dir):
                logger.info("No logs to sync")
                return True
                
            # Sync logs directory to Dropbox
            remote_path = f"{self.remote_name}:{self.remote_path}/logs"
            logger.info(f"Transferring logs to {remote_path}")
            
            cmd = [
                "rclone", 
                "copy",
                self.logs_dir, 
                remote_path,
                "--progress"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True, 
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                logger.error(f"Logs transfer failed: {result.stderr}")
                return False
            
            logger.info(f"Logs transfer completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing logs: {str(e)}")
            return False
    
    def check_connection(self):
        """Check if the Dropbox connection is working."""
        try:
            # Try to list the root of the remote to check connection
            result = subprocess.run(
                [
                    "rclone", "lsf", 
                    f"{self.remote_name}:",
                    "--max-depth", "1"
                ], 
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error checking Dropbox connection: {str(e)}")
            return False