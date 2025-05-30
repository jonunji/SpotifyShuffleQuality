import os
from flask import Flask, render_template, redirect, request, session, jsonify
from spotipy.oauth2 import SpotifyOAuth
import spotipy
from dotenv import load_dotenv
import time

load_dotenv()

stored_tracks = []
artist_genres_cache = {}
MAX_TRACKS_TO_SEND = 100 # You can adjust this number

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a real secret in production

SCOPE = "playlist-read-private user-read-playback-state user-modify-playback-state user-library-read user-top-read"

# Helper function to restore Spotify's repeat state
def _restore_repeat_state(sp_instance):
    # Only try to restore if we actually have a stored state
    if 'original_repeat_state' in session:
        try:
            sp_instance.repeat(session['original_repeat_state'])
            del session['original_repeat_state'] # Clear after restoration
        except spotipy.exceptions.SpotifyException:
            # Suppress errors if restoration fails (e.g., device disappeared)
            pass

# Helper function to perform full reset logic (data and Spotify state)
def _perform_reset():
    global stored_tracks
    global artist_genres_cache
    stored_tracks = []
    artist_genres_cache = {} # Reset cache when data is reset
    
    # Clear session-specific tracking variables
    if 'unshuffledkeys' in session:
        del session['unshuffledkeys']
    session['running'] = False

    # Attempt to restore repeat state if a token is available
    if session.get('token_info'):
        sp = spotipy.Spotify(auth=session['token_info']['access_token'])
        _restore_repeat_state(sp)

def populateUnShuffledKeys(queue_data):
    if not session.get('unshuffledkeys'):
        tracks = queue_data.get('queue', [])
        if len(tracks) >= 2:
            session['unshuffledkeys'] = [tracks[0]['id'], tracks[1]['id']]
        elif len(tracks) == 1:
            session['unshuffledkeys'] = [tracks[0]['id']]
        else:
            session['unshuffledkeys'] = []

@app.route('/toggle', methods=['GET', 'POST']) # Allow both for flexibility with frontend
def toggle():
    token_info = session.get('token_info')
    if not token_info:
        return jsonify({"status": "error", "error": "Not logged in"}), 401
    
    sp = spotipy.Spotify(auth=token_info['access_token'])

    current_running_state = session.get('running', False)
    new_running_state = not current_running_state

    session['running'] = new_running_state

    # Initialize playback_info for the response
    playback_info = {
        'is_playing': False,
        'device_name': 'N/A',
        'item_name': 'N/A',
        'item_artist': 'N/A'
    }
    # Initialize context_info for the response
    context_info = {}

    if new_running_state:
        try:
            current_playback = sp.current_playback()

            # If no active device or no item playing, cannot start tracking
            if not current_playback or not current_playback.get('is_playing') or not current_playback.get('item'):
                session['running'] = False # Revert running state if setup fails
                return jsonify({"status": "error", "error": "Please start playing a song on a Spotify device to enable full tracking."}), 400

            # Populate playback_info for the response from current_playback
            playback_info['is_playing'] = current_playback.get('is_playing', False)
            playback_info['device_name'] = current_playback.get('device', {}).get('name', 'Unknown Device')
            playback_info['item_name'] = current_playback.get('item', {}).get('name')
            playback_info['item_artist'] = ", ".join([a['name'] for a in current_playback.get('item', {}).get('artists', [])])

            # Populate context_info
            if current_playback.get('context'):
                context_type = current_playback['context']['type']
                context_id = current_playback['context']['uri'].split(':')[-1]
                context_info['type'] = context_type

                if context_type == 'album':
                    album = sp.album(context_id)
                    context_info['name'] = album['name']
                    context_info['image_url'] = album['images'][0]['url'] if album['images'] else None
                    context_info['owner_name'] = album['artists'][0]['name'] if album['artists'] else None
                    context_info['total_tracks'] = album['total_tracks']
                elif context_type == 'playlist':
                    playlist = sp.playlist(context_id)
                    context_info['name'] = playlist['name']
                    context_info['image_url'] = playlist['images'][0]['url'] if playlist['images'] else None
                    context_info['owner_name'] = playlist['owner']['display_name']
                    context_info['total_tracks'] = playlist['tracks']['total']
                elif context_type == 'artist':
                    artist = sp.artist(context_id)
                    context_info['name'] = artist['name']
                    context_info['image_url'] = artist['images'][0]['url'] if artist['images'] else None
                    context_info['owner_name'] = None # Artists don't have an 'owner'
                    context_info['total_tracks'] = None # Artists don't have a 'total_tracks' count directly
                else:
                    context_info['name'] = 'N/A'
                    context_info['image_url'] = None
                    context_info['owner_name'] = None
                    context_info['total_tracks'] = None


            # Store original repeat state to restore it later
            session['original_repeat_state'] = current_playback.get('repeat_state', 'off')

            # Set repeat mode to 'track' for stable playback
            sp.repeat('track')
            sp.shuffle(False) # Unshuffle
            time.sleep(2.5) # Give Spotify a moment to apply the repeat state

            # Get the initial queue after setting repeat for unshuffled keys
            initial_queue_data = sp.queue()
            populateUnShuffledKeys(initial_queue_data) # This will set session['unshuffledkeys']

            return jsonify(running=session['running'], status="started", playback_info=playback_info, context_info=context_info)

        except spotipy.exceptions.SpotifyException as e:
            session['running'] = False # Revert running state if setup fails
            if e.http_status == 401:
                return jsonify({"status": "error", "error": "Token expired, please log in again"}), 401
            return jsonify({"status": "error", "error": f"Error during setup: {str(e)}"}), 500
    else: # User is trying to STOP tracking
        _restore_repeat_state(sp) # Restore original repeat state when stopping
        return jsonify(running=session['running'], status="stopped")

# Dedicated endpoint for the "Reset Data" button/link
@app.route('/reset')
def reset_route():
    _perform_reset() # Call the shared reset logic
    return redirect('/')

@app.route('/')
def index():
    token_info = session.get('token_info')
    logged_in = token_info is not None and not SpotifyOAuth(scope=SCOPE).is_token_expired(token_info)

    # Initialize these to empty dictionaries to prevent Jinja2 Undefined errors
    initial_context_info = {}
    initial_playback_info = {
        'is_playing': False,
        'device_name': 'N/A',
        'item_name': 'N/A',
        'item_artist': 'N/A'
    }

    return render_template('index.html',
                           running=session.get('running', False),
                           logged_in=logged_in,
                           initial_context_info=initial_context_info,
                           initial_playback_info=initial_playback_info)

@app.route('/login')
def login():
    sp_oauth = SpotifyOAuth(scope=SCOPE)
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/logout')
def logout():
    session.clear()  # Clear all session data, including Spotify tokens
    _perform_reset()

    # Redirect to the home page after logout
    return redirect('/')

@app.route('/callback')
def callback():
    sp_oauth = SpotifyOAuth(scope=SCOPE)
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect('/')

@app.route('/queue_data')
def queue_data_endpoint():
    if not session.get("running"):
        return jsonify({"status": "stopped"}), 200

    token_info = session.get('token_info')
    if not token_info:
        return jsonify({"status": "error", "error": "Not logged in"}), 401

    # Ensure unshuffledkeys are present before proceeding with shuffle verification
    # This assumes populateUnShuffledKeys has been called successfully by the /toggle route
    if 'unshuffledkeys' not in session:
        _perform_reset()
        return jsonify({"status": "error", "error": "Tracking setup incomplete. Please restart tracking."}), 400

    sp = spotipy.Spotify(auth=token_info['access_token'])

    global stored_tracks
    global artist_genres_cache

    stored_dict = {t['id']: t for t in stored_tracks}

    try:
        current_playback = sp.current_playback()

        # Check for paused state, no active device, or no current item playing
        if not current_playback or not current_playback.get('is_playing') or not current_playback.get('item'):
            # If not playing or no active device/item, automatically stop tracking and restore repeat state
            session['running'] = False
            _restore_repeat_state(sp)
            return jsonify({
                "status": "paused",
                "message": "Playback paused or no active device/song. Tracking stopped.",
                "running": False
            }), 200
        
        sp.shuffle(False)
        sp.shuffle(True)

        # Wait until the shuffle takes effect by checking if the first 2 tracks changed
        max_attempts = 100
        attempts = 0

        unshuffled_keys = session.get('unshuffledkeys', [])
        
        while attempts < max_attempts:
            queue_data = sp.queue() # Re-fetch inside the loop
            tracks_in_loop = queue_data.get('queue', [])

            if len(tracks_in_loop) >= 2 and len(unshuffled_keys) >= 2:
                if tracks_in_loop[0]['id'] != unshuffled_keys[0] or tracks_in_loop[1]['id'] != unshuffled_keys[1]:
                    break  # Shuffle has taken effect
            elif len(tracks_in_loop) >= 1 and len(unshuffled_keys) >= 1:
                if len(unshuffled_keys) >= 1 and tracks_in_loop[0]['id'] != unshuffled_keys[0]:
                    break
            else:
                break  # Not enough info to compare or queue is empty

            time.sleep(0.1)  # Avoid hitting rate limits, crucial for waiting for Spotify
            attempts += 1

    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401: # Token expired
            return jsonify({"status": "error", "error": "Token expired, please log in again"}), 401
        # For any other Spotify API errors during this process, return an error to frontend
        return jsonify({"status": "error", "error": f"Spotify API error during shuffle operation: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": f"An unexpected error occurred: {str(e)}"}), 500

    tracks = queue_data.get('queue', [])

    # Collect unique artist IDs from the current queue to fetch genres
    new_artist_ids_to_fetch = set()
    for track in tracks:
        for artist in track.get('artists', []):
            if artist['id'] not in artist_genres_cache:
                new_artist_ids_to_fetch.add(artist['id'])

    # Fetch genres for new artists and add to cache
    if new_artist_ids_to_fetch:
        # Spotify API allows fetching up to 50 artists at once
        artist_ids_list = list(new_artist_ids_to_fetch)
        for i in range(0, len(artist_ids_list), 50):
            batch_ids = artist_ids_list[i:i+50]
            try:
                artists_data = sp.artists(batch_ids)
                for artist in artists_data['artists']:
                    if artist and artist.get('genres'):
                        artist_genres_cache[artist['id']] = artist['genres']
            except spotipy.exceptions.SpotifyException as e:
                print(f"Warning: Could not fetch genres for artist batch: {e}")
                pass

    for track in tracks:
        tid = track.get('id')
        if not tid:
            continue
        if tid in stored_dict:
            stored_dict[tid]['frequency'] += 1
        else:
            track['frequency'] = 1
            # Ensure 'album' and 'artists' keys exist, even if empty
            if 'album' not in track:
                track['album'] = {'images': []}
            if 'artists' not in track:
                track['artists'] = []
            stored_dict[tid] = track

    # Rebuild and sort
    stored_tracks = list(stored_dict.values())
    stored_tracks.sort(key=lambda x: x['frequency'], reverse=True)

    total_unique_tracks = len(stored_tracks)
    total_plays_counted = sum(t['frequency'] for t in stored_tracks)

    # Return all data, playback_info will now be 'N/A' from the start
    return jsonify(
        queue=stored_tracks[:MAX_TRACKS_TO_SEND],
        total_unique_tracks=total_unique_tracks,
        total_plays_counted=total_plays_counted
    )

@app.route('/track_stats/<string:track_id>')
def track_stats_endpoint(track_id):
    token_info = session.get('token_info')
    if not token_info:
        return jsonify({"status": "error", "error": "Not logged in"}), 401

    sp = spotipy.Spotify(auth=token_info['access_token'])
    global stored_tracks
    global artist_genres_cache

    track_stats = {}

    try:
        track_details = sp.track(track_id)
        if not track_details:
            return jsonify({"status": "error", "error": "Track not found."}), 404

        track_stats['name'] = track_details['name']
        track_stats['artists'] = [{"id": a['id'], "name": a['name']} for a in track_details['artists']]
        track_stats['album_name'] = track_details['album']['name']
        track_stats['album_image'] = track_details['album']['images'][0]['url'] if track_details['album']['images'] else None
        track_stats['duration_ms'] = track_details['duration_ms']
        track_stats['popularity'] = track_details['popularity'] # 0-100

        current_track_frequency = next((t['frequency'] for t in stored_tracks if t['id'] == track_id), 0)
        track_stats['frequency'] = current_track_frequency

        total_unique_tracks_in_queue = len(stored_tracks)
        if total_unique_tracks_in_queue > 0:
            track_stats['shuffle_chance_percent'] = (current_track_frequency / total_unique_tracks_in_queue) * 100
        else:
            track_stats['shuffle_chance_percent'] = 0.0

        artist_ids_of_clicked_track = [artist['id'] for artist in track_details['artists']]
        
        # Ensure genres for the clicked track's artists are in cache
        current_track_artist_genres = set()
        artists_to_fetch_now = []
        for artist_id in artist_ids_of_clicked_track:
            if artist_id in artist_genres_cache:
                current_track_artist_genres.update(artist_genres_cache[artist_id])
            else:
                artists_to_fetch_now.append(artist_id)
        
        if artists_to_fetch_now:
            try:
                fetched_artists = sp.artists(artists_to_fetch_now)
                for artist in fetched_artists['artists']:
                    if artist and artist.get('genres'):
                        artist_genres_cache[artist['id']] = artist['genres']
                        current_track_artist_genres.update(artist['genres'])
            except spotipy.exceptions.SpotifyException as e:
                print(f"Warning: Could not fetch genres for clicked track's artists: {e}")


        track_stats['artist_genres'] = list(current_track_artist_genres)

        num_songs_from_same_artists = 0
        songs_by_same_artists = {}
        
        num_songs_matching_genre = 0
        # Use a set to store track IDs that have already matched a genre to avoid double-counting
        matched_genre_track_ids = set()

        clicked_track_artist_ids = {a['id'] for a in track_details['artists']}

        for stored_track in stored_tracks:
            if stored_track['id'] == track_id:
                continue

            stored_track_artist_ids = {a['id'] for a in stored_track.get('artists', [])}
            
            # Same artist count
            if any(artist_id in clicked_track_artist_ids for artist_id in stored_track_artist_ids):
                num_songs_from_same_artists += 1
                for artist_id in stored_track_artist_ids.intersection(clicked_track_artist_ids):
                    if artist_id not in songs_by_same_artists:
                        songs_by_same_artists[artist_id] = []
                    songs_by_same_artists[artist_id].append(stored_track['id'])

            # Genre matching count
            # Only count if the track hasn't been counted for genre match yet
            if stored_track['id'] not in matched_genre_track_ids:
                for artist_id_in_stored_track in stored_track_artist_ids:
                    # Check if this stored track's artist's genres overlap with the clicked track's artist genres
                    if artist_id_in_stored_track in artist_genres_cache:
                        stored_artist_genres = set(artist_genres_cache[artist_id_in_stored_track])
                        if current_track_artist_genres.intersection(stored_artist_genres):
                            num_songs_matching_genre += 1
                            matched_genre_track_ids.add(stored_track['id']) # Mark as counted
                            break # Move to next stored_track as this one is counted for genre

        total_plays_by_same_artists = 0
        for stored_track in stored_tracks:
            stored_track_artist_ids = {a['id'] for a in stored_track.get('artists', [])}
            if any(artist_id in clicked_track_artist_ids for artist_id in stored_track_artist_ids):
                total_plays_by_same_artists += stored_track['frequency']

        track_stats['genres'] = list(current_track_artist_genres)
        track_stats['num_songs_from_same_artists'] = num_songs_from_same_artists
        track_stats['songs_by_same_artists'] = { # Changed from _breakdown to match frontend's expectation if it expects actual track IDs
            artist_id: [next((t for t in stored_tracks if t['id'] == tid), {}) for tid in track_ids]
            for artist_id, track_ids in songs_by_same_artists.items()
        }
        track_stats['total_plays_by_same_artists'] = total_plays_by_same_artists
        track_stats['num_songs_matching_genre'] = num_songs_matching_genre
        
        # Add actual tracks for songs_matching_genre
        track_stats['songs_matching_genre'] = [next((t for t in stored_tracks if t['id'] == tid), {}) for tid in matched_genre_track_ids]


        return jsonify(track_stats)

    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return jsonify({"status": "error", "error": "Token expired, please log in again"}), 401
        return jsonify({"status": "error", "error": f"Spotify API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)