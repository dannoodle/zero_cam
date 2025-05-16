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
                if local_dir == self.current_dir:
                    # Root current directory
                    remote_dir = f"{self.remote_name}:{self.remote_path}"
                else:
                    # Dated subdirectory
                    rel_path = os.path.relpath(local_dir, self.current_dir)
                    remote_dir = f"{self.remote_name}:{self.remote_path}/{rel_path}"
            elif local_dir.startswith(self.logs_dir) and self.sync_logs:
                # For logs
                if local_dir == self.logs_dir:
                    # Root logs directory 
                    remote_dir = f"{self.remote_name}:{self.remote_path}/logs"
                else:
                    # Subdirectory within logs
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
                        local_files.add(local_path.replace('\\', '/'))  # Normalize path separators
                
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
                    
                    # Use a single copy command for all files
                    result = subprocess.run(
                        ["rclone", "copy", local_dir, remote_dir, "--progress"],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"Failed to upload files: {result.stderr}")
                    else:
                        logger.info(f"Successfully uploaded {len(need_to_upload)} files")
                
                # Step 6: Download new/changed files from remote
                if need_to_download:
                    logger.info(f"Downloading {len(need_to_download)} files from remote")
                    
                    # Use a single copy command for all files
                    result = subprocess.run(
                        ["rclone", "copy", remote_dir, local_dir, "--progress"],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"Failed to download files: {result.stderr}")
                    else:
                        logger.info(f"Successfully downloaded {len(need_to_download)} files")
                
                # Step 7: Delete files on remote that don't exist locally (only if files were actually downloaded)
                if need_to_download and remote_files:
                    # Refresh local file list after downloads
                    new_local_files = set()
                    for root, _, files in os.walk(local_dir):
                        rel_root = os.path.relpath(root, local_dir)
                        if rel_root == '.':
                            rel_root = ''
                        for file in files:
                            if file.startswith('.pi_cam_sync_placeholder'):
                                continue  # Skip placeholder files
                            local_path = os.path.join(rel_root, file)
                            new_local_files.add(local_path.replace('\\', '/'))  # Normalize path separators
                    
                    # Files that exist remotely but not locally after download
                    to_delete_remotely = remote_files - new_local_files
                    
                    # Use a filter file for deletion
                    if to_delete_remotely:
                        logger.info(f"Deleting {len(to_delete_remotely)} files from remote that don't exist locally")
                        try:
                            # Delete files individually - compatible with all rclone versions
                            deleted_count = 0
                            for file in to_delete_remotely:
                                remote_file = f"{remote_dir}/{file}"
                                logger.debug(f"Deleting from remote: {remote_file}")
                                
                                result = subprocess.run(
                                    ["rclone", "deletefile", remote_file],
                                    capture_output=True,
                                    text=True,
                                    timeout=30
                                )
                                
                                if result.returncode == 0:
                                    deleted_count += 1
                                else:
                                    logger.error(f"Failed to delete {file} from remote: {result.stderr}")
                            
                            logger.info(f"Successfully deleted {deleted_count} files from remote")
                            
                        except Exception as e:
                            logger.error(f"Error deleting remote files: {str(e)}")
                
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