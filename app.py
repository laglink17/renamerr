from flask import Flask, request, jsonify, render_template
import os
import requests

app = Flask(__name__)

# Environment variables
SONARR_API_URL = os.getenv("SONARR_API_URL", "http://localhost:8989/api/v3")
SONARR_API_KEY = os.getenv("SONARR_API_KEY")
FILES_BASE_PATH = os.getenv("FILES_BASE_PATH", "/files")

# Headers for Sonarr API
headers = {"X-Api-Key": SONARR_API_KEY}

def build_new_filename(episode, alternative_title, format_template):
    """Construct a new filename based on the format template."""
    # Extract necessary data from the episode
    absolute = episode.get("absoluteEpisodeNumber", 0)
    quality = episode["quality"]["quality"]["name"]
    media_info = episode.get("mediaInfo", {})
    video_codec = media_info.get("videoCodec", "")
    audio_codec = media_info.get("audioCodec", "")
    audio_channels = media_info.get("audioChannels", "")
    video_dynamic_range = media_info.get("videoDynamicRangeType", "")
    release_group = episode.get("releaseGroup", "Unknown")

    # Replace placeholders in the format template
    new_filename = format_template.format(
        Series_Title=alternative_title,
        absolute=f"{absolute:02d}",
        Custom_Formats="",
        Quality_Full=quality,
        MediaInfo_VideoDynamicRangeType=video_dynamic_range,
        MediaInfo_VideoCodec=video_codec,
        Mediainfo_AudioCodec=audio_codec,
        Mediainfo_AudioChannels=audio_channels,
        Release_Group=release_group,
    )

    return new_filename

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
    """Fetches alternative titles for a specific series."""
    response = requests.get(f"{SONARR_API_URL}/series/{series_id}", headers=headers)
    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch series details"}), response.status_code

    series_data = response.json()
    alt_titles = series_data.get("alternateTitles", [])
    return jsonify([
        {"title": title["title"]}
        for title in alt_titles
    ])

import re
import os

@app.route("/preview-rename", methods=["POST"])
def preview_rename_files():
    data = request.json
    series_id = int(data.get("series_id"))
    chosen_title = data.get("chosen_title")
    format_template = (
        "{Series_Title} - {absolute:02d} [{Quality_Full} {MediaInfo_VideoCodec}]"
        "[{Mediainfo_AudioCodec} {Mediainfo_AudioChannels}]-{Release_Group}.mkv"
    )

    try:
        # Fetch episode files for the series
        response = requests.get(
            f"{SONARR_API_URL}/episodefile?seriesId={series_id}", headers=headers
        )
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch episode files"}), response.status_code

        episode_files = response.json()

        # Group episodes by season
        episodes_by_season = {}
        for episode in episode_files:
            season = episode.get("seasonNumber", 0)
            if season not in episodes_by_season:
                episodes_by_season[season] = []
            episodes_by_season[season].append(episode)

        # Generate preview for each season
        rename_preview = {}
        for season, episodes in episodes_by_season.items():
            preview = []
            for episode in episodes:
                current_path = episode["path"]
                absolute_episode_number = (
                    episode.get("absoluteEpisodeNumber") or episode.get("episodeNumber")
                )

                # Fallback: Extract episode number from filename if missing
                if absolute_episode_number is None:
                    match = re.search(r"\b(\d{1,3})\b", os.path.basename(current_path))
                    if match:
                        absolute_episode_number = int(match.group(1))
                    else:
                        raise ValueError(f"Missing episode number for file: {current_path}")

                quality = episode["quality"]["quality"]["name"]
                media_info = episode.get("mediaInfo", {})
                video_codec = media_info.get("videoCodec", "")
                audio_codec = media_info.get("audioCodec", "")

                # Adjust audio channels
                audio_channels = str(media_info.get("audioChannels", ""))
                if audio_channels == "2":
                    audio_channels = "2.0"

                release_group = episode.get("releaseGroup", "Unknown")

                # Build new filename
                new_filename = format_template.format(
                    Series_Title=chosen_title,
                    absolute=absolute_episode_number,
                    Quality_Full=quality,
                    MediaInfo_VideoCodec=video_codec,
                    Mediainfo_AudioCodec=audio_codec,
                    Mediainfo_AudioChannels=audio_channels,
                    Release_Group=release_group,
                )
                new_path = os.path.join(os.path.dirname(current_path), new_filename)

                preview.append({
                    "episode": absolute_episode_number,
                    "current": current_path,
                    "new": new_path,
                })

            rename_preview[season] = preview

        return jsonify({"rename_preview": rename_preview})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/confirm-rename", methods=["POST"])
def confirm_rename_files():
    data = request.json
    rename_preview = data.get("rename_preview", {})

    try:
        renamed_files = []

        # Iterate over each season and its episodes
        for season, episodes in rename_preview.items():
            for item in episodes:
                current_path = item["current"]
                new_path = item["new"]

                # Check for duplicates before renaming
                if new_path in [file["new"] for file in renamed_files]:
                    raise ValueError(f"Duplicate filename detected: {new_path}")

                # Rename the file
                os.rename(current_path, new_path)
                renamed_files.append({"old": current_path, "new": new_path})

        return jsonify({"message": "Files renamed successfully", "renamed_files": renamed_files})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
