import logging
from flask import Flask, request, jsonify, render_template  # type: ignore
import os
import requests
import sqlite3
import re

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
SONARR_API_URL = os.getenv("SONARR_API_URL", "http://localhost:8989/api/v3")
SONARR_API_KEY = os.getenv("SONARR_API_KEY")

# Headers for Sonarr API
headers = {"X-Api-Key": SONARR_API_KEY}

DB_PATH = "/config/renamerr.db"

# Format template for generating new filenames
format_template = (
    "{Series_Title} - {episode:02d} [{Quality_Full} {MediaInfo_VideoCodec}]"
    "[{Mediainfo_AudioCodec} {Mediainfo_AudioChannels}]{Release_Group}"
)

def initialize_database():
    """Initialize the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create the table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS series_titles (
            series_id INTEGER PRIMARY KEY,
            chosen_title TEXT NOT NULL,
            use_season_folders BOOLEAN NOT NULL DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()

def get_stored_series_info(series_id):
    """Retrieve the stored info for a series."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT chosen_title, use_season_folders FROM series_titles WHERE series_id = ?", 
        (series_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "chosen_title": result[0],
            "use_season_folders": bool(result[1])
        }
    return None

def get_all_stored_series():
    """Retrieve all series information from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT series_id, chosen_title, use_season_folders FROM series_titles")
    results = cursor.fetchall()
    conn.close()
    return {
        str(series_id): {
            "chosen_title": title,
            "use_season_folders": bool(use_season_folders)
        }
        for series_id, title, use_season_folders in results
    }

def store_series_info(series_id, chosen_title, use_season_folders):
    """Store or update the series information."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO series_titles 
        (series_id, chosen_title, use_season_folders)
        VALUES (?, ?, ?)
    """, (series_id, chosen_title, use_season_folders))
    conn.commit()
    conn.close()

def generate_new_filename(episode_file, chosen_title, episode_label, file_extension):
    """Generate a new filename based on the episode file details."""
    quality = episode_file["quality"]["quality"]["name"]
    media_info = episode_file.get("mediaInfo", {})
    video_codec = media_info.get("videoCodec", "")
    audio_codec = media_info.get("audioCodec", "")
    audio_channels = str(media_info.get("audioChannels", ""))
    if audio_channels == "2":
        audio_channels = "2.0"
    release_group = episode_file.get("releaseGroup", "")
    release_group_part = f"-{release_group}" if release_group else ""

    # Use the format_template to generate the new filename
    new_filename = format_template.format(
        Series_Title=chosen_title,
        episode=episode_label,
        Quality_Full=quality,
        MediaInfo_VideoCodec=video_codec,
        Mediainfo_AudioCodec=audio_codec,
        Mediainfo_AudioChannels=audio_channels,
        Release_Group=release_group_part,
    ) + file_extension  # Add the original extension

    return new_filename

def determine_new_path(current_path, new_filename, season, use_season_folders):
    """Determine the new path based on the current path and folder structure preference."""
    current_dir = os.path.dirname(current_path)
    current_in_season = any(f"Season {i:02d}" for i in range(100) if f"Season {i:02d}" in current_path)
    
    if use_season_folders:
        if current_in_season:
            # If already in season folder, keep it there
            new_path = os.path.join(current_dir, new_filename)
        else:
            # If not in season folder, create season folder structure
            base_dir = os.path.dirname(current_path)
            new_path = os.path.join(base_dir, f"Season {int(season):02d}", new_filename)
    else:
        if current_in_season:
            # If currently in season folder but moving to single folder, place in parent directory
            new_path = os.path.join(os.path.dirname(os.path.dirname(current_path)), new_filename)
        else:
            # If already in single folder, keep it there
            new_path = os.path.join(current_dir, new_filename)
    
    return new_path

def rename_file(current_path, new_path, UID, GID):
    """Rename a file and set permissions."""
    # Create any necessary directories
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    os.chmod(os.path.dirname(new_path), 0o2775)
    os.chown(os.path.dirname(new_path), UID, GID)
    # Rename the file
    os.rename(current_path, new_path)
    os.chown(new_path, UID, GID)
    logger.info(f"File renamed: {current_path} -> {new_path}")
    return {"status": "renamed", "message": "File renamed successfully."}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/series', methods=['GET'])
def get_series():
    """Fetches all series from Sonarr."""
    response = requests.get(f"{SONARR_API_URL}/series", headers=headers)
    if response.status_code != 200:
        logger.error("Failed to fetch series from Sonarr")
        return jsonify({"error": "Failed to fetch series"}), response.status_code

    series_list = response.json()
    return jsonify([
        {"id": series["id"], "title": series["title"]}
        for series in series_list
    ])

@app.route('/series/<int:series_id>', methods=['GET'])
def get_alternative_titles(series_id):
    """Fetches alternative titles for a specific series and includes the stored info."""
    response = requests.get(f"{SONARR_API_URL}/series/{series_id}", headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch series details for series ID {series_id}")
        return jsonify({"error": "Failed to fetch series details"}), response.status_code

    series_data = response.json()
    alt_titles = series_data.get("alternateTitles", [])
    
    # Get stored info
    stored_info = get_stored_series_info(series_id)
    
    # Prepare the response
    response_data = {
        "titles": [{"title": title["title"], 
                   "isStored": stored_info and title["title"] == stored_info["chosen_title"]} 
                  for title in alt_titles],
        "stored_info": stored_info
    }
    
    # If stored title exists but isn't in the alternative titles, add it
    if stored_info and not any(t["title"] == stored_info["chosen_title"] for t in response_data["titles"]):
        response_data["titles"].insert(0, {
            "title": stored_info["chosen_title"],
            "isStored": True
        })
        
    return jsonify(response_data)

@app.route("/preview-rename", methods=["POST"])
def preview_rename_files():
    data = request.json
    series_id = int(data.get("series_id"))
    chosen_title = data.get("chosen_title")
    use_season_folders = data.get("use_season_folders", True)

    # Store the series information in the database
    store_series_info(series_id, chosen_title, use_season_folders)

    try:
        # Fetch episode details
        episode_response = requests.get(
            f"{SONARR_API_URL}/episode?seriesId={series_id}", headers=headers
        )
        if episode_response.status_code != 200:
            logger.error(f"Failed to fetch episode details for series ID {series_id}")
            return jsonify({"error": "Failed to fetch episode details"}), episode_response.status_code

        episodes = episode_response.json()

        # Filter episodes with files
        episodes_with_files = [ep for ep in episodes if ep.get("hasFile")]

        # Fetch episode files for the series using seriesId
        file_response = requests.get(
            f"{SONARR_API_URL}/episodefile?seriesId={series_id}", headers=headers
        )
        if file_response.status_code != 200:
            logger.error(f"Failed to fetch episode files for series ID {series_id}")
            return jsonify({"error": "Failed to fetch episode files"}), file_response.status_code

        episode_files = {file["id"]: file for file in file_response.json()}

        # Group episodes by season
        episodes_by_season = {}
        for episode in episodes_with_files:
            season = episode["seasonNumber"]
            if season not in episodes_by_season:
                episodes_by_season[season] = []
            episodes_by_season[season].append(episode)

        # Generate preview for each season
        rename_preview = {}
        for season, episodes in episodes_by_season.items():
            preview = []
            for episode in episodes:
                episode_file = episode_files.get(episode["episodeFileId"])
                if not episode_file:
                    continue

                current_path = episode_file["path"]
                file_extension = os.path.splitext(current_path)[1]
                
                episode_label = (
                    episode["episodeNumber"] if use_season_folders else episode["absoluteEpisodeNumber"]
                )
                if episode_label is None:
                    raise ValueError(f"Missing episode number for file: {current_path}")

                new_filename = generate_new_filename(episode_file, chosen_title, episode_label, file_extension)
                new_path = determine_new_path(current_path, new_filename, season, use_season_folders)

                # Check if the file is already renamed
                if os.path.basename(current_path) == os.path.basename(new_path):        
                    preview.append({
                        "episode": episode_label,
                        "current": current_path,
                        "new": new_path,
                        "status": "already_renamed",
                        "message": "Already renamed, nothing to do."
                    })
                else:
                    preview.append({
                        "episode": episode_label,
                        "current": current_path,
                        "new": new_path,
                        "status": "needs_rename",
                        "message": "File needs to be renamed."
                    })

            rename_preview[season] = preview

        return jsonify({"rename_preview": rename_preview})

    except Exception as e:
        logger.error(f"Error during preview rename: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/confirm-rename", methods=["POST"])
def confirm_rename_files():
    data = request.json
    rename_preview = data.get("rename_preview", {})
    series_id = int(data.get("series_id"))  # Make sure series_id is included in the request

    result = process_rename(rename_preview=rename_preview)
    return jsonify(result)

@app.route("/api/autorename", methods=["POST"])
def auto_rename():
    """
    API endpoint to auto-rename files for specific series or all series with stored info.
    
    Request body (optional):
    {
        "series_ids": ["123", "456"]  # Optional list of series IDs to process
    }
    """
    try:
        data = request.json or {}
        specific_series_ids = data.get("series_ids", [])
        
        # Get stored series information from database
        stored_series = get_all_stored_series()
        
        # If specific series IDs provided, filter stored_series
        if specific_series_ids:
            stored_series = {
                series_id: info 
                for series_id, info in stored_series.items() 
                if series_id in specific_series_ids
            }
        
        if not stored_series:
            logger.error("No stored information found for the specified series")
            return jsonify({
                "error": "No stored information found for the specified series"
            }), 404

        # Process each series
        results = {}
        for series_id, info in stored_series.items():
            results[series_id] = process_rename(
                series_id=int(series_id),
                chosen_title=info["chosen_title"],
                use_season_folders=info["use_season_folders"]
            )

        # Check if any series was processed successfully
        any_success = any(
            result.get("success", False) 
            for result in results.values()
        )
        
        if not any_success:
            logger.error("Failed to process any series")
            return jsonify({
                "error": "Failed to process any series",
                "results": results
            }), 500

        return jsonify({
            "message": "Auto-rename process completed",
            "results": results
        })

    except Exception as e:
        logger.error(f"Error during auto-rename: {str(e)}")
        return jsonify({
            "error": f"Error during auto-rename: {str(e)}"
        }), 500

def process_rename(series_id=None, chosen_title=None, use_season_folders=True, rename_preview=None):
    """
    Process rename for a single series or based on a rename preview.
    
    Args:
        series_id (int, optional): The ID of the series to process (for API calls).
        chosen_title (str, optional): The title to use for renaming (for API calls).
        use_season_folders (bool, optional): Whether to use season folders (for API calls).
        rename_preview (dict, optional): The rename preview object (for frontend calls).
    """
    UID = int(os.getenv("PUID", 1000))
    GID = int(os.getenv("PGID", 100))

    try:
        renamed_files = []
        logs = []

        if rename_preview:
            # Process based on rename_preview (frontend call)
            for season, episodes in rename_preview.items():
                for item in episodes:
                    current_path = item["current"]
                    new_path = item["new"]
                    
                    # Skip if the file is already renamed
                    if item.get("status") == "already_renamed":
                        logs.append(f"File already renamed: {current_path}")
                        renamed_files.append({
                            "message": f"Episode {item['episode']} already renamed, nothing to do.",
                            "path": current_path,
                            "status": "already_renamed"
                        })
                    else:
                        # Rename the file
                        rename_result = rename_file(current_path, new_path, UID, GID)
                        logs.append(rename_result["message"])
                        renamed_files.append({
                            "message": f"Episode {item['episode']} file renamed successfully.",
                            "new": new_path,
                            "old": current_path,
                            "status": "renamed"
                        })
        else:
            # Process based on series_id (API call)
            if not series_id or not chosen_title:
                return {"error": "Missing series_id or chosen_title"}

            # Fetch episode details
            episode_response = requests.get(
                f"{SONARR_API_URL}/episode?seriesId={series_id}", 
                headers=headers
            )
            if episode_response.status_code != 200:
                logger.error(f"Failed to fetch episodes for series {series_id}")
                return {"error": f"Failed to fetch episodes for series {series_id}"}

            episodes = episode_response.json()
            episodes_with_files = [ep for ep in episodes if ep.get("hasFile")]

            # Fetch episode files
            file_response = requests.get(
                f"{SONARR_API_URL}/episodefile?seriesId={series_id}", 
                headers=headers
            )
            if file_response.status_code != 200:
                logger.error(f"Failed to fetch episode files for series {series_id}")
                return {"error": f"Failed to fetch episode files for series {series_id}"}

            episode_files = {file["id"]: file for file in file_response.json()}

            # Process each episode
            for episode in episodes_with_files:
                episode_file = episode_files.get(episode["episodeFileId"])
                if not episode_file:
                    continue

                current_path = episode_file["path"]
                file_extension = os.path.splitext(current_path)[1]
                
                episode_label = (
                    episode["episodeNumber"] if use_season_folders 
                    else episode["absoluteEpisodeNumber"]
                )
                
                if episode_label is None:
                    continue

                new_filename = generate_new_filename(episode_file, chosen_title, episode_label, file_extension)
                new_path = determine_new_path(current_path, new_filename, episode["seasonNumber"], use_season_folders)

                # Check if the file is already renamed
                if os.path.basename(current_path) == os.path.basename(new_path):
                    renamed_files.append({
                        "message": f"Episode {episode_label} already renamed, nothing to do.",
                        "path": current_path,
                        "status": "already_renamed"
                    })
                else:
                    # Rename the file
                    rename_result = rename_file(current_path, new_path, UID, GID)
                    if rename_result["status"] == "renamed":
                        renamed_files.append({
                            "message": f"Episode {episode_label} file renamed successfully.",
                            "new": new_path,
                            "old": current_path,
                            "status": "renamed"
                        })

        # Construct a summary message
        num_renamed = len([f for f in renamed_files if f["status"] == "renamed"])
        num_skipped = len([f for f in renamed_files if f["status"] == "already_renamed"])
        popup_message = f"Renamed {num_renamed} files, skipped {num_skipped} files (already renamed)."

            # Trigger Sonarr rescan only if at least one file was renamed
        rescan_status = "not_triggered"
        if num_renamed > 0:
            rescan_response = requests.post(
                f"{SONARR_API_URL}/command",
                headers=headers,
                json={
                    "name": "RescanSeries",
                    "seriesId": series_id
                }
            )
            rescan_status = "success" if rescan_response.status_code == 201 else "failed"

        return {
            "id": series_id,
            "title": chosen_title,
            "renamed_files": renamed_files,
            "rescan_status": rescan_status,
            "success": True,
            "logs": logs,
            "message": popup_message
        }

    except Exception as e:
        logger.error(f"Error during rename operation: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=5000, debug=True)