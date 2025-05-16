#!/usr/bin/env python3
"""
Dropbox synchronisation module for Raspberry Pi Zero Camera System.
Handles file transfer between local system and Dropbox using rclone.
"""

import os
import subprocess
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DropboxSync:
    """Handles file transfer with Dropbox using rclone."""
    
    def __init__(self, config, current_dir, logs_dir):
        """Initialize with configuration settings."""
        self.config = config['sync']
        self.current_dir = current_dir
        self.logs_dir = logs_dir
        
        self.remote_name = self.config.get('remote_name', 'dropbox')
        self.remote_path = self.config.get('remote_path', 'pi_cam')
        self.sync_logs = self.config.get('sync_logs', True)
        self.operation_mode = self.config.get('operation_mode', 'copy')
        
        # Validate operation mode
        if self.operation_mode not in ['copy', 'sync']:
            logger.warning(f"Invalid operation mode '{self.operation_mode}', defaulting to 'copy'")
            self.operation_mode = 'copy'
        
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
            logger.info(f"Using operation mode: {self.operation_mode}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking rclone configuration")
            return False
        except Exception as e:
            logger.error(f"Error checking rclone configuration: {str(e)}")
            return False
    
    def _get_remote_path(self, local_path):
        """Generate the appropriate remote path for a local directory."""
        # For dated directories within current
        if os.path.dirname(local_path) == self.current_dir:
            # Just use the date folder name directly
            folder_name = os.path.basename(local_path)
            return f"{self.remote_name}:{self.remote_path}/{folder_name}"
        
        # For logs directory
        elif local_path == self.logs_dir and self.sync_logs:
            return f"{self.remote_name}:{self.remote_path}/logs"
        
        # For any other directory (fallback)
        else:
            # Extract just the basename as the target directory
            folder_name = os.path.basename(local_path)
            return f"{self.remote_name}:{self.remote_path}/{folder_name}"
    
    def sync_directory(self, local_dir):
        """Transfer a local directory to Dropbox using the configured operation mode."""
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
    
    def sync_daily_directory(self):
        """Transfer the current day's directory to Dropbox."""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.current_dir, today)
        
        if os.path.exists(daily_dir):
            result = self.sync_directory(daily_dir)
            
            # Also sync logs if configured
            if result and self.sync_logs:
                self.sync_logs_directory()
                
            return result
        else:
            logger.warning(f"Today's directory does not exist: {daily_dir}")
            return False
    
    def sync_all_current(self):
        """Transfer all dated directories from current images to Dropbox."""
        success = True
        sync_count = 0
        
        # Get all items in the current directory
        try:
            for item in os.listdir(self.current_dir):
                item_path = os.path.join(self.current_dir, item)
                
                # Only sync directories that match date format (YYYY-MM-DD)
                if os.path.isdir(item_path) and self._is_date_format(item):
                    logger.info(f"Syncing dated directory: {item}")
                    if not self.sync_directory(item_path):
                        success = False
                    else:
                        sync_count += 1
                        
            logger.info(f"Synced {sync_count} dated directories")
            
            # Also sync logs if configured
            if success and self.sync_logs:
                self.sync_logs_directory()
                
            return success
            
        except Exception as e:
            logger.error(f"Error syncing dated directories: {str(e)}")
            return False
    
    def _is_date_format(self, dirname):
        """Check if a directory name follows the YYYY-MM-DD format."""
        try:
            datetime.strptime(dirname, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    
    def sync_recent_directories(self, days=7):
        """Sync recent dated directories (last N days)."""
        success = True
        sync_count = 0
        
        try:
            # Get cutoff date
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
            
            # Get all items in the current directory
            for item in os.listdir(self.current_dir):
                item_path = os.path.join(self.current_dir, item)
                
                # Only sync directories that match date format and are recent
                if os.path.isdir(item_path) and self._is_date_format(item) and item >= cutoff_str:
                    logger.info(f"Syncing recent directory: {item}")
                    if not self.sync_directory(item_path):
                        success = False
                    else:
                        sync_count += 1
                        
            logger.info(f"Synced {sync_count} recent directories")
            
            # Also sync logs if configured
            if success and self.sync_logs:
                self.sync_logs_directory()
                
            return success
            
        except Exception as e:
            logger.error(f"Error syncing recent directories: {str(e)}")
            return False
    
    def sync_logs_directory(self):
        """Transfer log files to Dropbox if enabled."""
        if self.sync_logs:
            return self.sync_directory(self.logs_dir)
        return True
    
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