"""
Dropbox synchronisation module for Raspberry Pi Zero Camera System.
Handles file transfer between local system and Dropbox using rclone.
"""

import os
import subprocess
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from config.settings import config, CURRENT_DIR, LOGS_DIR

logger = logging.getLogger(__name__)

class DropboxSync:
    """Handles file transfer with Dropbox using rclone."""
    
    def __init__(self):
        """Initialize with configuration settings."""
        self.remote_name = config.get('sync', 'remote_name', 'dropbox')
        self.remote_path = config.get('sync', 'remote_path', 'pi_cam')
        self.sync_logs = config.get('sync', 'sync_logs', True)
        self.operation_mode = config.get('sync', 'operation_mode', 'copy')  # Default to 'copy' instead of 'sync'
        
        # Validate operation mode
        if self.operation_mode not in ['copy', 'sync']:
            logger.warning(f"Invalid operation mode '{self.operation_mode}', defaulting to 'copy'")
            self.operation_mode = 'copy'
        
        # Check if rclone is configured
        self._check_rclone_config()
    
    def _check_rclone_config(self) -> bool:
        """Verify that rclone is properly configured with the remote.
        
        Returns:
            bool: True if configuration is valid, False otherwise
        """
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
            logger.info(f"Using operation mode: {self.operation_mode}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking rclone configuration")
            return False
        except Exception as e:
            logger.error(f"Error checking rclone configuration: {str(e)}")
            return False
    
    def _get_remote_path(self, local_path: str) -> str:
        """Generate the appropriate remote path for a local directory.
        
        Args:
            local_path: Local directory path
            
        Returns:
            str: Remote path
        """
        if local_path.startswith(CURRENT_DIR):
            # For current images, preserve directory structure
            rel_path = os.path.relpath(local_path, os.path.dirname(CURRENT_DIR))
            return f"{self.remote_name}:{self.remote_path}/{rel_path}"
        
        elif local_path.startswith(LOGS_DIR) and self.sync_logs:
            # For logs, use a logs subfolder
            rel_path = os.path.relpath(local_path, os.path.dirname(LOGS_DIR))
            return f"{self.remote_name}:{self.remote_path}/{rel_path}"
        
        else:
            # For anything else, use the base remote path + basename
            rel_path = os.path.basename(local_path)
            return f"{self.remote_name}:{self.remote_path}/{rel_path}"
    
    def transfer_directory(self, local_dir: str) -> bool:
        """Transfer a local directory to Dropbox using the configured operation mode.
        
        Args:
            local_dir: Local directory to transfer
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Skip transfer for non-existent directories
            if not os.path.exists(local_dir):
                logger.warning(f"Directory does not exist: {local_dir}")
                return False
                
            # Skip transfer for empty directories
            if not os.listdir(local_dir):
                logger.info(f"Skipping transfer for empty directory: {local_dir}")
                return True
            
            remote_path = self._get_remote_path(local_dir)
            logger.info(f"Transferring {local_dir} to {remote_path} using {self.operation_mode} mode")
            
            # Build the rclone command
            cmd = [
                "rclone", 
                self.operation_mode,  # 'copy' or 'sync'
                local_dir, 
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
            
            logger.info(f"Transfer completed successfully: {local_dir} → {remote_path}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout transferring directory: {local_dir}")
            return False
        except Exception as e:
            logger.error(f"Error transferring to Dropbox: {str(e)}")
            return False
    
    def transfer_today(self) -> bool:
        """Transfer the current day's directory to Dropbox.
        
        Returns:
            bool: True if successful, False otherwise
        """
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(CURRENT_DIR, today)
        
        if os.path.exists(daily_dir):
            return self.transfer_directory(daily_dir)
        else:
            logger.warning(f"Today's directory does not exist: {daily_dir}")
            return False
    
    def transfer_all_current(self) -> bool:
        """Transfer all current images to Dropbox.
        
        Returns:
            bool: True if successful, False otherwise
        """
        return self.transfer_directory(CURRENT_DIR)
    
    def transfer_logs(self) -> bool:
        """Transfer log files to Dropbox if enabled.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if self.sync_logs:
            return self.transfer_directory(LOGS_DIR)
        return True
    
    def check_connection(self) -> bool:
        """Check if the Dropbox connection is working.
        
        Returns:
            bool: True if connection is working, False otherwise
        """
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