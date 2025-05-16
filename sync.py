#!/usr/bin/env python3
"""
Dropbox synchronisation module using rclone.
Handles bidirectional file transfer between local system and Dropbox,
allowing deletions to sync in both directions.
"""

import os
import subprocess
import logging
import tempfile
import time
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
        self.bidirectional = self.config.get('bidirectional', True)
        self.current_dir = current_dir
        self.logs_dir = logs_dir
        
        # Use a simple directory path for state files to avoid permission issues
        self.state_dir = os.path.join(os.path.expanduser("~"), ".pi_cam_sync_state")
        try:
            os.makedirs(self.state_dir, exist_ok=True)
            # Ensure directory has the right permissions
            os.chmod(self.state_dir, 0o755)
            logger.info(f"Sync state directory: {self.state_dir}")
        except Exception as e:
            logger.error(f"Error creating state directory: {str(e)}")
            self.bidirectional = False
        
        # Check if rclone is configured
        if not self._check_rclone_config():
            self.bidirectional = False
    
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
                logger.error(f"Failed to run rclone. Is it installed? Error: {result.stderr}")
                return False
            
            remotes = result.stdout.splitlines()
            remote_full = f"{self.remote_name}:"
            
            if remote_full not in remotes:
                logger.error(f"Remote '{self.remote_name}:' not found in rclone configuration.")
                logger.error("Available remotes: " + ", ".join(remotes))
                logger.error("Please run 'rclone config' to set up the Dropbox remote.")
                return False
            
            # Check if we can access the remote
            result = subprocess.run(
                ["rclone", "lsf", f"{self.remote_name}:"], 
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Cannot access remote {self.remote_name}: {result.stderr}")
                return False
                
            logger.info(f"Rclone configured with remote: {self.remote_name}:")
            return True
            
        except Exception as e:
            logger.error(f"Error checking rclone configuration: {str(e)}")
            return False
    
    def _ensure_directory_not_empty(self, directory):
        """Ensure a directory is not empty by creating a placeholder file if needed."""
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            
        # If directory is empty, create a placeholder file
        if not os.listdir(directory):
            placeholder = os.path.join(directory, ".pi_cam_sync_placeholder")
            try:
                with open(placeholder, 'w') as f:
                    f.write(f"Placeholder file for sync - created {datetime.now().isoformat()}")
                logger.debug(f"Created placeholder file in empty directory: {directory}")
                return True
            except Exception as e:
                logger.error(f"Error creating placeholder: {str(e)}")
                return False
        return True
    
    def sync_directory(self, local_dir):
        """Sync a directory between local system and Dropbox."""
        try:
            # Skip sync for non-existent directories
            if not os.path.exists(local_dir):
                logger.info(f"Skipping sync for non-existent directory: {local_dir}")
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
                logger.info(f"Skipping unrecognized directory: {local_dir}")
                return True
            
            # Ensure directory is not empty
            self._ensure_directory_not_empty(local_dir)
            
            # Use simple copy-delete approach instead of bisync
            if self.bidirectional:
                return self._bidirectional_copy_approach(local_dir, remote_dir)
            else:
                return self._one_way_sync(local_dir, remote_dir)
            
        except Exception as e:
            logger.error(f"Error syncing directory: {str(e)}")
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
    
    def _bidirectional_copy_approach(self, local_dir, remote_dir):
        """Implement bidirectional sync using copy and delete operations."""
        logger.info(f"Bidirectional sync between {local_dir} and {remote_dir}")
        
        # Step 1: Create a temporary directory for tracking files
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Step 2: List all files in local directory
                local_files = set()
                for root, _, files in os.walk(local_dir):
                    rel_root = os.path.relpath(root, local_dir)
                    if rel_root == '.':
                        rel_root = ''
                    for file in files:
                        if file.startswith('.pi_cam_sync_placeholder'):
                            continue  # Skip placeholder files
                        local_path = os.path.join(rel_root, file)
                        local_files.add(local_path)
                
                # Step 3: List all files in remote directory
                remote_files = set()
                result = subprocess.run(
                    ["rclone", "lsf", "-R", remote_dir], 
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    remote_files = set(line.strip() for line in result.stdout.splitlines() if line.strip())
                else:
                    logger.warning(f"Could not list remote files: {result.stderr}")
                    # Remote might not exist yet, just do one-way sync
                    return self._one_way_sync(local_dir, remote_dir)
                
                # Step 4: Identify files to sync
                need_to_upload = local_files - remote_files
                need_to_download = remote_files - local_files
                
                # Step 5: Upload new/changed files to remote
                if need_to_upload:
                    logger.info(f"Uploading {len(need_to_upload)} files to remote")
                    for file in need_to_upload:
                        src = os.path.join(local_dir, file)
                        dst = f"{remote_dir}/{file}"
                        logger.debug(f"Uploading: {src} -> {dst}")
                        result = subprocess.run(
                            ["rclone", "copy", src, os.path.dirname(dst)],
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        if result.returncode != 0:
                            logger.error(f"Failed to upload {file}: {result.stderr}")
                
                # Step 6: Download new/changed files from remote
                if need_to_download:
                    logger.info(f"Downloading {len(need_to_download)} files from remote")
                    for file in need_to_download:
                        src = f"{remote_dir}/{file}"
                        dst = os.path.join(local_dir, file)
                        # Ensure the parent directory exists
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        logger.debug(f"Downloading: {src} -> {dst}")
                        result = subprocess.run(
                            ["rclone", "copy", src, os.path.dirname(dst)],
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        if result.returncode != 0:
                            logger.error(f"Failed to download {file}: {result.stderr}")
                
                # Step 7: Delete files on remote that don't exist locally
                if need_to_download:
                    # Only delete if we know remote files
                    deleted_count = 0
                    for file in need_to_download:
                        # Don't delete placeholder files
                        if '.pi_cam_sync_placeholder' in file:
                            continue
                            
                        local_file = os.path.join(local_dir, file)
                        remote_file = f"{remote_dir}/{file}"
                        
                        # Check if local file exists now (after download)
                        if not os.path.exists(local_file):
                            # File was deleted locally, delete from remote
                            logger.debug(f"Deleting from remote: {remote_file}")
                            result = subprocess.run(
                                ["rclone", "delete", remote_file],
                                capture_output=True,
                                text=True,
                                timeout=30
                            )
                            if result.returncode == 0:
                                deleted_count += 1
                            else:
                                logger.error(f"Failed to delete {file} from remote: {result.stderr}")
                    
                    if deleted_count > 0:
                        logger.info(f"Deleted {deleted_count} files from remote")
                
                logger.info(f"Bidirectional sync completed: {len(need_to_upload)} uploaded, {len(need_to_download)} downloaded")
                return True
                
        except Exception as e:
            logger.error(f"Error in bidirectional sync: {str(e)}")
            logger.info("Falling back to one-way sync")
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