from flask import Flask, request, jsonify, render_template # type: ignore
import os
import requests
import sqlite3
import re

app = Flask(__name__)

# Environment variables
SONARR_API_URL = os.getenv("SONARR_API_URL", "http://localhost:8989/api/v3")
SONARR_API_KEY = os.getenv("SONARR_API_KEY")

# Headers for Sonarr API
headers = {"X-Api-Key": SONARR_API_KEY}

DB_PATH = "/config/renamerr.db"

def initialize_database():
    """Initialize the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create the table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS series_titles (
            series_id INTEGER PRIMARY KEY,
            chosen_title TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def get_stored_title(series_id):
    """Retrieve the stored chosen title for a series."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT chosen_title FROM series_titles WHERE series_id = ?", (series_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def store_chosen_title(series_id, chosen_title):
    """Store or update the chosen title for a series."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO series_titles (series_id, chosen_title)
        VALUES (?, ?)
    """, (series_id, chosen_title))
    conn.commit()
    conn.close()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/series', methods=['GET'])
def get_series():
    """Fetches all series from Sonarr."""
    response = requests.get(f"{SONARR_API_URL}/series", headers=headers)
    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch series"}), response.status_code

    series_list = response.json()
    return jsonify([
        {"id": series["id"], "title": series["title"]}
        for series in series_list
    ])

@app.route('/series/<int:series_id>', methods=['GET'])
def get_alternative_titles(series_id):
    """Fetches alternative titles for a specific series and includes the stored title."""
    response = requests.get(f"{SONARR_API_URL}/series/{series_id}", headers=headers)
    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch series details"}), response.status_code

    series_data = response.json()
    alt_titles = series_data.get("alternateTitles", [])
    
    # Get stored title
    stored_title = get_stored_title(series_id)
    
    # Prepare the response with stored title information
    titles_list = [{"title": title["title"], "isStored": title["title"] == stored_title} 
                   for title in alt_titles]
    
    # If stored title exists but isn't in the alternative titles, add it
    if stored_title and not any(t["title"] == stored_title for t in titles_list):
        titles_list.insert(0, {"title": stored_title, "isStored": True})
        
    return jsonify(titles_list)

@app.route("/preview-rename", methods=["POST"])
def preview_rename_files():
    data = request.json
    series_id = int(data.get("series_id"))
    chosen_title = data.get("chosen_title")
    use_season_folders = data.get("use_season_folders", True)

    # Store the chosen title in the database
    store_chosen_title(series_id, chosen_title)

    format_template = (
        "{Series_Title} - {episode:02d} [{Quality_Full} {MediaInfo_VideoCodec}]"
        "[{Mediainfo_AudioCodec} {Mediainfo_AudioChannels}]{Release_Group}"
    )

    try:
        # Fetch episode details
        episode_response = requests.get(
            f"{SONARR_API_URL}/episode?seriesId={series_id}", headers=headers
        )
        if episode_response.status_code != 200:
            return jsonify({"error": "Failed to fetch episode details"}), episode_response.status_code

        episodes = episode_response.json()

        # Filter episodes with files
        episodes_with_files = [ep for ep in episodes if ep.get("hasFile")]

        # Fetch episode files for the series using seriesId
        file_response = requests.get(
            f"{SONARR_API_URL}/episodefile?seriesId={series_id}", headers=headers
        )
        if file_response.status_code != 200:
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
                current_dir = os.path.dirname(current_path)
                # Get the original file extension
                file_extension = os.path.splitext(current_path)[1]
                
                episode_label = (
                    episode["episodeNumber"] if use_season_folders else episode["absoluteEpisodeNumber"]
                )
                if episode_label is None:
                    raise ValueError(f"Missing episode number for file: {current_path}")

                quality = episode_file["quality"]["quality"]["name"]
                media_info = episode_file.get("mediaInfo", {})
                video_codec = media_info.get("videoCodec", "")
                audio_codec = media_info.get("audioCodec", "")
                audio_channels = str(media_info.get("audioChannels", ""))
                if audio_channels == "2":
                    audio_channels = "2.0"
                release_group = episode_file.get("releaseGroup", None)

                # Conditionally include release group in the filename
                if release_group:
                    release_group_part = f"-{release_group}"
                else:
                    release_group_part = ""

                # Build new filename with original extension
                new_filename = format_template.format(
                    Series_Title=chosen_title,
                    episode=episode_label,
                    Quality_Full=quality,
                    MediaInfo_VideoCodec=video_codec,
                    Mediainfo_AudioCodec=audio_codec,
                    Mediainfo_AudioChannels=audio_channels,
                    Release_Group=release_group_part,
                ) + file_extension  # Add the original extension

                # Determine new path based on current location and desired structure
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
                        # If currently in season folder but moving to single folder,
                        # place in parent directory
                        new_path = os.path.join(os.path.dirname(os.path.dirname(current_path)), new_filename)
                    else:
                        # If already in single folder, keep it there
                        new_path = os.path.join(current_dir, new_filename)

                preview.append({
                    "episode": episode_label,
                    "current": current_path,
                    "new": new_path,
                })

            rename_preview[season] = preview

        return jsonify({"rename_preview": rename_preview})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/confirm-rename", methods=["POST"])
def confirm_rename_files():
        
    # Fetch UID and GID from environment variables
    UID = int(os.getenv("PUID", 1000))
    GID = int(os.getenv("PGID", 100))

    data = request.json
    rename_preview = data.get("rename_preview", {})
    series_id = int(data.get("series_id"))  # Make sure series_id is included in the request

    try:
        renamed_files = []

        for season, episodes in rename_preview.items():
            for item in episodes:
                current_path = item["current"]
                new_path = item["new"]
                current_dir = os.path.dirname(current_path)
                
                # Check if current path is in a season folder
                current_in_season = any(f"Season {i:02d}" for i in range(100) if f"Season {i:02d}" in current_path)
                
                # Check if new path should be in season folder
                new_in_season = any(f"Season {i:02d}" for i in range(100) if f"Season {i:02d}" in new_path)
                
                if current_in_season and not new_in_season:
                    # If moving from season folder to single folder,
                    # place the file in the parent directory
                    parent_dir = os.path.dirname(os.path.dirname(current_path))
                    filename = os.path.basename(new_path)
                    new_path = os.path.join(parent_dir, filename)
                elif not current_in_season and new_in_season:
                    # If moving from single folder to season folder,
                    # create the season folder in the current directory
                    season_folder = f"Season {int(season):02d}"
                    new_path = os.path.join(current_dir, season_folder, os.path.basename(new_path))
                elif current_in_season and new_in_season:
                    # If already in season folder and should stay in season folder,
                    # just rename in the current folder
                    new_path = os.path.join(current_dir, os.path.basename(new_path))

                # Create any necessary directories
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                os.chmod(os.path.dirname(new_path), 0o2775)
                os.chown(os.path.dirname(new_path), UID, GID)

                # Rename the file
                os.rename(current_path, new_path)
                os.chown(new_path, UID, GID)
                renamed_files.append({"old": current_path, "new": new_path})

        # After successful rename, trigger a rescan in Sonarr
        rescan_response = requests.post(
            f"{SONARR_API_URL}/command",
            headers=headers,
            json={
                "name": "RescanSeries",
                "seriesId": series_id
            }
        )

        # Check rescan response
        if rescan_response.status_code != 201:
            return jsonify({
                "message": "Files renamed successfully, but failed to trigger rescan in Sonarr.",
                "renamed_files": renamed_files,
                "rescan_error": f"Sonarr API returned status code {rescan_response.status_code}: {rescan_response.text}"
            }), 207  # Using 207 Multi-Status to indicate partial success

        # Everything succeeded
        return jsonify({
            "message": "Files renamed successfully and Sonarr rescan triggered.",
            "renamed_files": renamed_files
        })

    except Exception as e:
        return jsonify({
            "error": f"Error during rename operation: {str(e)}"
        }), 500
    #     return jsonify({"message": "Files renamed successfully", "renamed_files": renamed_files})

    # except Exception as e:
    #     return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=5000, debug=True)
