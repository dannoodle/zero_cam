#!/usr/bin/env python3
"""
Dropbox synchronisation module using rclone.
Handles file transfer between local system and Dropbox.
"""

import os
import subprocess
import logging

logger = logging.getLogger(__name__)

class DropboxSync:
    """Handles synchronisation with Dropbox using rclone."""
    
    def __init__(self, config, current_dir, logs_dir):
        """Initialize with configuration settings."""
        self.config = config['sync']
        self.remote_name = self.config.get('remote_name', 'dropbox')
        self.remote_path = self.config.get('remote_path', 'pi_cam')
        self.sync_logs = self.config.get('sync_logs', True)
        self.current_dir = current_dir
        self.logs_dir = logs_dir
        
        # Check if rclone is configured
        self._check_rclone_config()
    
    def _check_rclone_config(self):
        """Verify that rclone is properly configured with the remote."""
        try:
            # Check if the configured remote exists
            result = subprocess.run(
                ["rclone", "listremotes"], 
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error("Failed to run rclone. Is it installed?")
                return False
            
            remotes = result.stdout.splitlines()
            remote_full = f"{self.remote_name}:"
            
            if remote_full not in remotes:
                logger.error(f"Remote '{self.remote_name}:' not found in rclone configuration.")
                logger.error("Available remotes: " + ", ".join(remotes))
                logger.error("Please run 'rclone config' to set up the Dropbox remote.")
                return False
                
            logger.info(f"Rclone configured with remote: {self.remote_name}:")
            return True
            
        except Exception as e:
            logger.error(f"Error checking rclone configuration: {str(e)}")
            return False
    
    def sync_directory(self, local_dir):
        """Sync a local directory to Dropbox."""
        try:
            # Skip sync for non-existent or empty directories
            if not os.path.exists(local_dir) or not os.listdir(local_dir):
                logger.info(f"Skipping sync for empty directory: {local_dir}")
                return True
            
            # Determine remote path based on directory type
            if local_dir.startswith(self.current_dir):
                # For current images
                rel_path = os.path.relpath(local_dir, self.current_dir)
                remote_dir = f"{self.remote_name}:{self.remote_path}/{rel_path}"
            elif local_dir.startswith(self.logs_dir) and self.sync_logs:
                # For logs
                rel_path = os.path.relpath(local_dir, self.logs_dir)
                remote_dir = f"{self.remote_name}:{self.remote_path}/logs/{rel_path}"
            else:
                # Skip if not a recognized directory
                return True
            
            logger.info(f"Syncing {local_dir} to {remote_dir}")
            
            # Run rclone sync command
            result = subprocess.run(
                [
                    "rclone", "sync", 
                    local_dir, 
                    remote_dir,
                    "--progress"
                ], 
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Sync failed: {result.stderr}")
                return False
            
            logger.info(f"Sync completed successfully: {local_dir} → {remote_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing to Dropbox: {str(e)}")
            return False
    
    def sync_daily_directory(self):
        """Sync the current day's directory to Dropbox."""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.current_dir, today)
        
        if os.path.exists(daily_dir):
            return self.sync_directory(daily_dir)
        else:
            logger.warning(f"Daily directory does not exist: {daily_dir}")
            return False
    
    def sync_all_current(self):
        """Sync all current images to Dropbox."""
        return self.sync_directory(self.current_dir)
    
    def sync_logs(self):
        """Sync log files to Dropbox if enabled."""
        if self.sync_logs:
            return self.sync_directory(self.logs_dir)
        return True