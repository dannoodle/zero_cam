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
    
    def __init__(self, config, temp_dir, logs_dir):
        """Initialize with configuration settings."""
        self.config = config['sync']
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
        Sync temporary directory to Dropbox and 
        then move files to properly dated archive directories.
        """
        try:
            # Skip if the temp directory is empty
            if not os.path.exists(self.temp_dir) or not os.listdir(self.temp_dir):
                logger.info("No images in temp directory to sync")
                return True
                    
            # Sync the temp directory to Dropbox
            remote_path = f"{self.remote_name}:{self.remote_path}"
            logger.info(f"Transferring new images from temp to {remote_path}")
            
            # Use the configured operation mode (copy by default)
            operation_mode = self.config.get('operation_mode', 'copy')
            logger.info(f"Using operation mode: {operation_mode}")
            
            cmd = [
                "rclone", 
                operation_mode,
                self.temp_dir, 
                remote_path,
                "--progress"
            ]
            
            # Execute rclone command
            logger.info(f"Running command: {' '.join(cmd)}")
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
            
            # Now move all files from temp to archive directory
            # Use parent of current_dir to get the images dir
            images_dir = os.path.dirname(self.current_dir)
            archive_dir = os.path.join(images_dir, "archive")
            
            # Create dated directory in archive
            today = datetime.now().strftime("%Y-%m-%d")
            dated_archive_dir = os.path.join(self.archive_dir, today)
            os.makedirs(dated_archive_dir, exist_ok=True)
            
            # Move files from temp to dated archive directory
            logger.info(f"Moving files from {self.temp_dir} to {dated_archive_dir}")
            
            move_count = 0
            move_errors = 0
            for filename in os.listdir(self.temp_dir):
                src_file = os.path.join(self.temp_dir, filename)
                dst_file = os.path.join(dated_archive_dir, filename)
                
                if os.path.isfile(src_file):
                    try:
                        # Handle existing files
                        if os.path.exists(dst_file):
                            import time
                            name, ext = os.path.splitext(filename)
                            new_name = f"{name}_{int(time.time())}{ext}"
                            dst_file = os.path.join(dated_archive_dir, new_name)
                        
                        shutil.move(src_file, dst_file)
                        move_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error moving file {src_file} to {dst_file}: {str(e)}")
                        move_errors += 1
            
            logger.info(f"Moved {move_count} files from temp to archive directory (errors: {move_errors})")
            
            # Check if all files were moved
            remaining = 0
            if os.path.exists(self.temp_dir):
                remaining = len([f for f in os.listdir(self.temp_dir) if os.path.isfile(os.path.join(self.temp_dir, f))])
                
            if remaining > 0:
                logger.warning(f"{remaining} files still remain in temp directory")
                return False
                
            return move_errors == 0
                
        except Exception as e:
            logger.error(f"Error in sync_temp_and_move: {str(e)}")
            return False
            
    def move_temp_to_archive(self):
        """
        Move files from temp directory directly to archive.
        """
        try:
            # Skip if the temp directory is empty
            if not os.path.exists(self.temp_dir) or not os.listdir(self.temp_dir):
                logger.info("No images in temp directory to move")
                return True
                
            # Use today's date for the archive folder
            today = datetime.now().strftime("%Y-%m-%d")
            archive_dir = os.path.join(os.path.dirname(self.current_dir), "archive", today)
            os.makedirs(archive_dir, exist_ok=True)
            
            logger.info(f"Moving files from temp directory to archive: {archive_dir}")
            
            move_count = 0
            move_errors = 0
            for filename in os.listdir(self.temp_dir):
                src_file = os.path.join(self.temp_dir, filename)
                dst_file = os.path.join(archive_dir, filename)
                
                if os.path.isfile(src_file):
                    try:
                        # Handle existing files
                        if os.path.exists(dst_file):
                            file_base, file_ext = os.path.splitext(filename)
                            dst_file = f"{archive_dir}/{file_base}_{int(time.time())}{file_ext}"
                        
                        shutil.move(src_file, dst_file)
                        move_count += 1
                    except Exception as e:
                        logger.error(f"Failed to move {src_file} to {dst_file}: {str(e)}")
                        move_errors += 1
            
            logger.info(f"Moved {move_count} files from temp to archive ({move_errors} errors)")
            
            # Check if all files were moved
            remaining_files = len(os.listdir(self.temp_dir))
            if remaining_files > 0:
                logger.warning(f"{remaining_files} files still remain in temp directory")
                return False
                
            return move_errors == 0
            
        except Exception as e:
            logger.error(f"Error moving files to archive: {str(e)}")
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