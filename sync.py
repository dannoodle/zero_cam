#!/usr/bin/env python3
"""
Dropbox synchronisation module using rclone.
Handles bidirectional file transfer between local system and Dropbox,
allowing deletions to sync in both directions.
"""

import os
import subprocess
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DropboxSync:
    """Handles bidirectional synchronisation with Dropbox using rclone."""
    
    def __init__(self, config, current_dir, logs_dir):
        """Initialize with configuration settings."""
        self.config = config['sync']
        self.remote_name = self.config.get('remote_name', 'dropbox')
        self.remote_path = self.config.get('remote_path', 'pi_cam')
        self.sync_logs = self.config.get('sync_logs', True)
        self.bidirectional = self.config.get('bidirectional', True)  # New setting
        self.current_dir = current_dir
        self.logs_dir = logs_dir
        
        # Directory for rclone bisync state files
        parent_dir = os.path.dirname(os.path.dirname(current_dir))
        self.state_dir = os.path.join(parent_dir, "sync_state")
        try:
            os.makedirs(self.state_dir, exist_ok=True)
            # Set permissions to ensure write access
            os.chmod(self.state_dir, 0o755)
            logger.info(f"Sync state directory created at {self.state_dir}")
        except Exception as e:
            logger.error(f"Failed to create sync state directory: {str(e)}")
            self.bidirectional = False
        
        # Check if rclone is configured
        self._check_rclone_config()
        
        # Check if rclone version supports bisync
        if self.bidirectional:
            self._check_rclone_bisync()
    
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
    
    def _check_rclone_bisync(self):
        """Check if rclone version supports bisync."""
        try:
            # Run the help command for bisync specifically
            result = subprocess.run(
                ["rclone", "help", "bisync"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info("Rclone supports bidirectional sync")
                return True
            else:
                logger.warning("Rclone version doesn't support bidirectional sync. Falling back to one-way sync.")
                self.bidirectional = False
                return False
                
        except Exception as e:
            logger.error(f"Error checking rclone bisync support: {str(e)}")
            self.bidirectional = False
            return False
    
    def sync_directory(self, local_dir):
        """Sync a directory between local system and Dropbox.
        
        If bidirectional is enabled, uses rclone bisync to sync in both directions.
        Otherwise, falls back to standard one-way sync.
        """
        try:
            # Skip sync for non-existent directories
            if not os.path.exists(local_dir):
                logger.info(f"Skipping sync for non-existent directory: {local_dir}")
                return True
                
            # Skip empty directories for one-way sync only
            if not self.bidirectional and not os.listdir(local_dir):
                logger.info(f"Skipping sync for empty directory: {local_dir}")
                return True
            
            # Determine remote path based on directory type
            if local_dir.startswith(self.current_dir):
                # For current images
                rel_path = os.path.relpath(local_dir, self.current_dir)
                remote_dir = f"{self.remote_name}:{self.remote_path}/{rel_path}"
                state_file = os.path.join(self.state_dir, f"bisync_{rel_path.replace('/', '_')}.json")
            elif local_dir.startswith(self.logs_dir) and self.sync_logs:
                # For logs
                rel_path = os.path.relpath(local_dir, self.logs_dir)
                remote_dir = f"{self.remote_name}:{self.remote_path}/logs/{rel_path}"
                state_file = os.path.join(self.state_dir, f"bisync_logs_{rel_path.replace('/', '_')}.json")
            else:
                # Skip if not a recognized directory
                return True
            
            # Choose sync method based on configuration
            if self.bidirectional:
                return self._bisync_directory(local_dir, remote_dir, state_file)
            else:
                return self._one_way_sync(local_dir, remote_dir)
            
        except Exception as e:
            logger.error(f"Error syncing to Dropbox: {str(e)}")
            return False
    
    def _one_way_sync(self, local_dir, remote_dir):
        """Perform traditional one-way sync (local to remote)."""
        logger.info(f"One-way syncing {local_dir} to {remote_dir}")
        
        try:
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
            logger.error(f"Error in one-way sync: {str(e)}")
            return False
    
    def _bisync_directory(self, local_dir, remote_dir, state_file):
        """Perform bidirectional sync between local and remote directories."""
        logger.info(f"Bidirectional sync between {local_dir} and {remote_dir}")
        
        try:
            # Check if this is the first sync for this directory
            first_run = not os.path.exists(state_file)
            
            # Build the bisync command
            cmd = [
                "rclone", "bisync", 
                local_dir, 
                remote_dir,
                "--verbose",
                "--state-path", state_file
            ]
            
            # Add resync flag for first run
            if first_run:
                cmd.append("--resync")
                logger.info("First sync, performing full resync")
            
            logger.debug(f"Running bisync command: {' '.join(cmd)}")
            
            # Run the bisync command
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            # Log the full output for debugging
            if result.stdout:
                logger.debug(f"Bisync stdout: {result.stdout}")
            if result.stderr:
                logger.debug(f"Bisync stderr: {result.stderr}")
            
            # Check for common bisync errors and handle them
            if result.returncode != 0:
                logger.error(f"Bidirectional sync failed with code {result.returncode}")
                
                # Handle common errors
                if "bisync requires a --resync" in result.stderr:
                    logger.info("Will perform a full resync on next attempt")
                    if os.path.exists(state_file):
                        os.remove(state_file)
                    return self._bisync_directory(local_dir, remote_dir, state_file)  # Try again with fresh state
                elif "Failed to create state file" in result.stderr:
                    logger.info("State file error, will retry with resync")
                    if os.path.exists(state_file):
                        os.remove(state_file)
                
                # Fall back to one-way sync on failure
                logger.info("Falling back to one-way sync after bidirectional sync failure")
                return self._one_way_sync(local_dir, remote_dir)
            
            logger.info(f"Bidirectional sync completed successfully between {local_dir} ↔ {remote_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Error in bidirectional sync: {str(e)}")
            # Fall back to one-way sync on exception
            logger.info("Falling back to one-way sync after exception")
            return self._one_way_sync(local_dir, remote_dir)
    
    def sync_daily_directory(self):
        """Sync the current day's directory with Dropbox."""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.current_dir, today)
        
        if os.path.exists(daily_dir):
            return self.sync_directory(daily_dir)
        else:
            logger.warning(f"Daily directory does not exist: {daily_dir}")
            return False
    
    def sync_all_current(self):
        """Sync all current images with Dropbox."""
        return self.sync_directory(self.current_dir)
    
    def sync_logs(self):
        """Sync log files with Dropbox if enabled."""
        if self.sync_logs:
            return self.sync_directory(self.logs_dir)
        return True