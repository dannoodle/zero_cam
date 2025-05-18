Zero Cam Configuration Guide
This document explains all the configuration options available in the config.json file.

Camera Settings
Option	Description	Default
name	Unique name for this camera instance	"zero_cam"
interval	Time in seconds between image captures	20
captures	Number of images to capture before syncing	3
hflip	Flip image horizontally (true/false)	false
vflip	Flip image vertically (true/false)	false
rotation	Image rotation in degrees (0, 90, 180, 270)	0
quality	JPEG quality (1-100, lower = more compression)	35
width	Image width in pixels	2592
height	Image height in pixels	1944
Sync Settings
Option	Description	Default
remote_name	rclone remote name	"dropbox"
remote_path	Path/folder in the remote storage	Camera name
operation_mode	Sync mode: "copy" (keep local), "move" (delete after sync), or "sync" (two-way)	"copy"
sync_logs	Whether to sync log files (true/false)	true
sync_on_shutdown	Whether to sync on system shutdown (true/false)	true
File Management Settings
Option	Description	Default
days_before_archive	Days to keep images in active directory	2
archive_retention_days	Days to keep archived images before deletion	10
log_retention_days	Days to keep log files	7
min_free_space_mb	Minimum free space in MB before cleanup	500
System Settings
Option	Description	Auto-populated
installation_path	Path where the system is installed	Yes
user	User running the system	Yes
camera_name	Name of this camera instance	Yes
version	Software version	Yes
installation_date	Date of installation	Yes
Log Level
The log_level setting controls the verbosity of logging. Available options:

"DEBUG" - Most verbose, includes detailed diagnostic information
"INFO" - General operational information
"WARNING" - Issues that might cause problems but allow operation to continue
"ERROR" - Serious problems that prevent functionality
"CRITICAL" - Critical issues that prevent operation
Configuration Tips
Camera Orientation: If your camera is installed upside down, set both hflip and vflip to true
Storage Management: Adjust archive_retention_days based on your available storage and needs
Sync Frequency: To sync more often, reduce the captures setting
Image Quality: For more storage-efficient images, reduce the quality value (lower = more compression)
Bandwidth Optimisation: If you have limited bandwidth, increase the captures setting to sync less frequently
Managing Your Configuration
Use the management script to easily edit your configuration:

~/zero_cam-manage
Select option 4 to edit the configuration, then restart the service to apply changes.

