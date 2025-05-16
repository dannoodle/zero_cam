#!/usr/bin/env python3
"""
File management module for Raspberry Pi Zero Camera System.
Handles directory structure, archiving, and cleanup.
"""

import os
import shutil
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class FileManager:
    """Handles file operations, directory structure, archiving and cleanup."""
    
    def __init__(self, config, archive_dir, logs_dir):
        """Initialize with configuration settings."""
        self.config = config['file_management']
        self.archive_dir = archive_dir
        self.logs_dir = logs_dir
        
        self.archive_retention_days = self.config.get('archive_retention_days', 10)
        self.log_retention_days = self.config.get('log_retention_days', 7)
        self.min_free_space_mb = self.config.get('min_free_space_mb', 500)
        
        # Ensure directories exist
        for directory in [archive_dir, logs_dir]:
            os.makedirs(directory, exist_ok=True)
            
        # Create today's directory
        self.ensure_today_dir()

    def ensure_today_dir(self):
        """Ensure today's directory exists in the archive."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = os.path.join(self.archive_dir, today)
        os.makedirs(today_dir, exist_ok=True)
        return today_dir
    
    def is_date_format(self, dirname):
        """Check if a directory name follows the YYYY-MM-DD format."""
        try:
            datetime.strptime(dirname, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    
    def get_date_dirs(self, base_dir):
        """Get all date-based directories in the specified base directory."""
        if not os.path.exists(base_dir):
            return []
            
        dirs = []
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            
            # Check if it's a directory and follows YYYY-MM-DD format
            if os.path.isdir(item_path) and self.is_date_format(item):
                dirs.append(item_path)
        
        return dirs
    
    def archive_old_directories(self):
        """Move old directories from current to archive."""
        logger.info("Checking for directories to archive...")
        
        # Calculate the cutoff date
        cutoff_date = datetime.now() - timedelta(days=self.days_before_archive)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        # Get all date directories
        date_dirs = self.get_date_dirs(self.current_dir)
        
        # Filter for directories older than the cutoff
        archived_count = 0
        for dir_path in date_dirs:
            dir_name = os.path.basename(dir_path)
            
            # Skip if not older than cutoff
            if dir_name >= cutoff_str:
                continue
                
            # Create archive destination
            archive_dest = os.path.join(self.archive_dir, dir_name)
            os.makedirs(os.path.dirname(archive_dest), exist_ok=True)
            
            # Move directory to archive
            logger.info(f"Archiving directory: {dir_path} → {archive_dest}")
            
            try:
                # Move entire directory if destination doesn't exist
                if not os.path.exists(archive_dest):
                    shutil.move(dir_path, archive_dest)
                else:
                    # Otherwise, move files individually and merge
                    for file in os.listdir(dir_path):
                        src_file = os.path.join(dir_path, file)
                        dst_file = os.path.join(archive_dest, file)
                        
                        if os.path.isfile(src_file):
                            shutil.move(src_file, dst_file)
                    
                    # Remove the now-empty source directory
                    os.rmdir(dir_path)
                
                archived_count += 1
                
            except Exception as e:
                logger.error(f"Error archiving directory {dir_path}: {str(e)}")
        
        logger.info(f"Archived {archived_count} directories")
        return archived_count
    
    def cleanup_old_archives(self):
        """Remove archived directories beyond the retention period."""
        logger.info("Checking for old archives to clean up...")
        
        # Calculate the cutoff date
        cutoff_date = datetime.now() - timedelta(days=self.archive_retention_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        # Get all date directories in archive
        archive_dirs = self.get_date_dirs(self.archive_dir)
        
        # Remove directories older than the cutoff
        removed_count = 0
        for dir_path in archive_dirs:
            dir_name = os.path.basename(dir_path)
            
            # Skip if not older than cutoff
            if dir_name >= cutoff_str:
                continue
                
            # Remove the directory
            logger.info(f"Removing old archive: {dir_path}")
            
            try:
                shutil.rmtree(dir_path)
                removed_count += 1
                
            except Exception as e:
                logger.error(f"Error removing archive {dir_path}: {str(e)}")
        
        logger.info(f"Removed {removed_count} old archive directories")
        return removed_count
    
    def cleanup_old_logs(self):
        """Remove log files beyond the retention period."""
        logger.info("Checking for old logs to clean up...")
        
        # Calculate the cutoff date
        cutoff_date = datetime.now() - timedelta(days=self.log_retention_days)
        
        # Get all files in logs directory
        removed_count = 0
        if not os.path.exists(self.logs_dir):
            return 0
            
        for filename in os.listdir(self.logs_dir):
            file_path = os.path.join(self.logs_dir, filename)
            
            # Skip if not a file
            if not os.path.isfile(file_path):
                continue
                
            # Get file modification time
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # Skip if not older than cutoff
                if mtime >= cutoff_date:
                    continue
                    
                # Remove the file
                logger.info(f"Removing old log file: {file_path}")
                os.remove(file_path)
                removed_count += 1
                
            except Exception as e:
                logger.error(f"Error checking/removing log file {file_path}: {str(e)}")
        
        logger.info(f"Removed {removed_count} old log files")
        return removed_count
    
    def check_disk_space(self):
        """Check available disk space and initiate cleanup if needed."""
        try:
            # Get disk usage statistics
            stat = shutil.disk_usage(self.current_dir)
            free_mb = stat.free / (1024 * 1024)
            
            logger.debug(f"Disk space: {free_mb:.1f}MB free")
            
            if free_mb < self.min_free_space_mb:
                logger.warning(f"Low disk space: {free_mb:.1f}MB available (min: {self.min_free_space_mb}MB)")
                
                # Run cleanup actions
                self.cleanup_old_logs()
                self.cleanup_old_archives()
                
                # Check if we've recovered enough space
                stat = shutil.disk_usage(self.current_dir)
                free_mb = stat.free / (1024 * 1024)
                
                if free_mb < self.min_free_space_mb:
                    logger.error(f"Critical disk space: {free_mb:.1f}MB available after cleanup")
                    return False
                else:
                    logger.info(f"Disk space recovered: {free_mb:.1f}MB available after cleanup")
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking disk space: {str(e)}")
            return False
    
    def run_daily_maintenance(self):
        """Run daily file maintenance tasks."""
        logger.info("Running daily file maintenance")
        
        try:
            # Clean up old archives
            self.cleanup_old_archives()
            
            # Clean up old logs
            self.cleanup_old_logs()
            
            # Check disk space
            return self.check_disk_space()
            
        except Exception as e:
            logger.error(f"Error during daily maintenance: {str(e)}")
            return False