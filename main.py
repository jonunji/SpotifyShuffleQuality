import os
from flask import Flask, render_template, redirect, request, session, jsonify
from spotipy.oauth2 import SpotifyOAuth
import spotipy
from dotenv import load_dotenv
import time
from trackTrie import TrackTrie
from collections import deque

class TracksInContext:
    def __init__(self):
        self.num_shuffles = 0
        self.stored_tracks = {}
        self.track_trie = TrackTrie()

load_dotenv()

stored_tracks = {}
artist_genres_cache = {}
track_trie = TrackTrie()
num_shuffles = 0
MAX_TRACKS_TO_SEND = 100

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a real secret in production

SCOPE = "playlist-read-private user-read-playback-state user-modify-playback-state user-library-read user-top-read"

# Helper function to perform full reset logic (data and Spotify state)
def reset():
    # wait for things to stop running
    session['running'] = False
    time.sleep(2)

    global stored_tracks
    global artist_genres_cache
    stored_tracks = {}
    artist_genres_cache = {} # Reset cache when data is reset
    
    # Clear session-specific tracking variables
    if 'unshuffledkeys' in session:
        del session['unshuffledkeys']

# Dedicated endpoint for the "Reset Data" button/link
@app.route('/reset')
def reset_route():
    reset()
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

@app.route('/callback')
def callback():
    sp_oauth = SpotifyOAuth(scope=SCOPE)
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect('/')

@app.route('/logout')
def logout():
    # Clear all session data, including Spotify tokens
    session.clear()
    reset()

    # Redirect to the home page after logout
    return redirect('/')

def populateUnShuffledKeys(queue_data):
    if 'unshuffledkeys' in session:
        session['unshuffledkeys'].clear()

    tracks = queue_data.get('queue', [])
    if len(tracks) >= 2:
        session['unshuffledkeys'] = [tracks[0]['id'], tracks[1]['id']]
    elif len(tracks) == 1:
        session['unshuffledkeys'] = [tracks[0]['id']]
    else:
        session['unshuffledkeys'] = []

@app.route('/toggle', methods=['GET', 'POST'])
def toggle():
    token_info = session.get('token_info')
    if not token_info:
        return jsonify({"status": "error", "error": "Not logged in"}), 401
    
    sp = spotipy.Spotify(auth=token_info['access_token'])

    # toggle the state 
    new_running_state = not session.get('running', False)

    session['running'] = new_running_state

    # Initialize playback_info for the response
    playback_info = {
        'is_playing': False,
        'device_name': 'N/A',
        'item_name': 'N/A',
        'item_artist': 'N/A'
    }
    # Initialize context_info for the response
    context_info = {
        'name': 'N/A',
        'image_url': None,
        'owner_name': None,
        'total_tracks': None
    }

    if new_running_state:
        try:
            current_playback = sp.current_playback()

            # If no active device or no item playing, cannot start tracking
            if not current_playback or not current_playback.get('is_playing') or not current_playback.get('item'):
                session['running'] = False # Revert running state if setup fails
                return jsonify({"status": "error", "error": "Please start playing a song on a Spotify device to allow tracking."}), 400

            # Populate playback_info for the response from current_playback
            playback_info['is_playing'] = current_playback.get('is_playing', False)
            playback_info['device_name'] = current_playback.get('device', {}).get('name', 'Unknown Device')
            playback_info['item_name'] = current_playback.get('item', {}).get('name')
            playback_info['item_artist'] = ", ".join([a['name'] for a in current_playback.get('item', {}).get('artists', [])])

            # store the current song so we can check when it changes
            session['current_song_id'] = current_playback.get('item', {}).get('id')

            # Populate context_info
            if current_playback.get('context'):
                context_type = current_playback['context']['type']
                context_id = current_playback['context']['uri'].split(':')[-1]
                context_info['type'] = context_type

                app.logger.info(current_playback['context'])
                if context_type == 'album':
                    context = sp.album(context_id)
                    context_info['owner_name'] = context['artists'][0]['name'] if context['artists'] else None
                    context_info['total_tracks'] = context['total_tracks']
                elif context_type == 'playlist':
                    context = sp.playlist(context_id)
                    context_info['owner_name'] = context['owner']['display_name']
                    context_info['total_tracks'] = context['tracks']['total']
                elif context_type == 'artist':
                    context = sp.artist(context_id)
                
                if context:
                    context_info['name'] = context['name']
                    context_info['image_url'] = context['images'][0]['url'] if context['images'] else None

            sp.shuffle(False) # Unshuffle
            time.sleep(2.5)

            populateUnShuffledKeys(sp.queue())

            return jsonify(running=session['running'], status="started", playback_info=playback_info, context_info=context_info)

        except spotipy.exceptions.SpotifyException as e:
            session['running'] = False # Revert running state if setup fails
            if e.http_status == 401:
                return jsonify({"status": "error", "error": "Token expired, please log in again"}), 401
            return jsonify({"status": "error", "error": f"Error during setup: {str(e)}"}), 500
        
    else: # User is trying to STOP tracking
        return jsonify(running=session['running'], status="stopped")

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
        reset()
        return jsonify({"status": "error", "error": "Tracking setup incomplete. Please restart tracking."}), 400

    sp = spotipy.Spotify(auth=token_info['access_token'])

    global stored_tracks
    global artist_genres_cache
    global num_shuffles

    try:
              
        sp.shuffle(False)
        
        queue_data = sp.queue()
        # song changed, so need to update the unshuffled keys
        if queue_data['currently_playing']['id'] != session['current_song_id']:
            time.sleep(5)
            populateUnShuffledKeys(queue_data)
            session['current_song_id'] = queue_data['currently_playing']['id']

        sp.shuffle(True)

        # Wait until the shuffle takes effect by checking if the first 2 tracks changed
        max_attempts = 5
        attempts = 0

        unshuffled_keys = session.get('unshuffledkeys', [])
        
        # wait until shuffle takes effect
        while attempts < max_attempts:
            queue_data = sp.queue()
            tracks = queue_data.get('queue', [])

            if len(tracks) >= 2 and len(unshuffled_keys) >= 2:
                if tracks[0]['id'] != unshuffled_keys[0] or tracks[1]['id'] != unshuffled_keys[1]:
                    break  # Shuffle has taken effect
            elif len(tracks) >= 1 and len(unshuffled_keys) >= 1:
                if len(unshuffled_keys) >= 1 and tracks[0]['id'] != unshuffled_keys[0]:
                    break # Shuffle has taken effect
            else:
                break  # Not enough info to compare or queue is empty

            time.sleep(0.5)  # Avoid hitting rate limits with spotify
            attempts += 1

    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401: # Token expired
            return jsonify({"status": "error", "error": "Token expired, please log in again"}), 401
        if e.http_status == 429: # rate limits
            return jsonify({"status": "error", "error": "Rate limits met, please try again later"}), 429
        if e.http_status == 404: # rate limits
            return jsonify({"status": "error", "error": "No active device, please keep spotify open"}), 404
        
        # For any other Spotify API errors during this process, return an error to frontend
        return jsonify({"status": "error", "error": f"Spotify API error during shuffle operation: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": f"An unexpected error occurred: {str(e)}"}), 500

    # Collect unique artist IDs from the current queue to fetch genres
    new_artist_ids = set()
    for track in tracks:
        for artist in track.get('artists', []):
            if artist['id'] not in artist_genres_cache:
                new_artist_ids.add(artist['id'])

    # Fetch genres for new artists and add to cache
    if new_artist_ids:
        # Spotify API allows fetching up to 50 artists at once
        artist_ids_list = list(new_artist_ids)
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

        if tid in stored_tracks:
            stored_tracks[tid]['frequency'] += 1
        else:
            track['frequency'] = 1
            stored_tracks[tid] = track

    # Handle the track trie for pattern finding later
    tracks_deque = deque([track.get('id') for track in tracks])
    track_trie.addShuffleQueue(tracks_deque, num_shuffles)
    num_shuffles += 1

    # Rebuild and sort
    stored_tracks_list = list(stored_tracks.values())
    stored_tracks_list.sort(key=lambda x: x['frequency'], reverse=True)

    total_unique_tracks = len(stored_tracks_list)
    total_plays_counted = sum(t['frequency'] for t in stored_tracks_list)

    return jsonify(
        queue=stored_tracks_list[:MAX_TRACKS_TO_SEND],
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
        track_details = stored_tracks[track_id]
        if not track_details:
            return jsonify({"status": "error", "error": "Track not found."}), 404

        track_stats['name'] = track_details['name']
        track_stats['artists'] = [{"id": a['id'], "name": a['name']} for a in track_details['artists']]
        track_stats['album_name'] = track_details['album']['name']
        track_stats['album_image'] = track_details['album']['images'][0]['url'] if track_details['album']['images'] else None
        track_stats['duration_ms'] = track_details['duration_ms']
        track_stats['popularity'] = track_details['popularity'] # 0-100
        track_stats['shuffle_chance_percent'] = 0.0 # TODO: delte this when fix todo below

        track_stats['frequency'] = track_details['frequency']

        total_unique_tracks_in_queue = len(stored_tracks)
        if total_unique_tracks_in_queue > 0:
            # TODO: change this to the total num of songs in the context, not in queue
            track_stats['shuffle_chance_percent'] = (track_stats['frequency'] / total_unique_tracks_in_queue) * 100

        clicked_track_artist_ids = {a['id'] for a in track_details['artists']}

        # helper function to flatten the list of genres from multiple artists
        def GetGenreList(artist_ids):
            genre_list = []

            for artist_id in artist_ids:
                if artist_id in artist_genres_cache:
                    genre_list.extend(artist_genres_cache[artist_id])

            return genre_list

        track_stats['artist_genres'] = GetGenreList(clicked_track_artist_ids)
        # Use a set to store track IDs that have already matched a genre to avoid double-counting
        songs_matching_genre = []
        songs_by_same_artists = {}

        total_plays_by_same_artists = 0
        for stored_track_id, cur_stored_track in stored_tracks.items():
            # don't count the song that was clicked on
            if stored_track_id == track_id:
                continue

            # Same artist count
            cur_stored_track_artist_ids = {a['id'] for a in cur_stored_track['artists']} # Extract IDs
            for aid in clicked_track_artist_ids:
                if aid in cur_stored_track_artist_ids:
                    songs_by_same_artists.setdefault(aid, []).append(cur_stored_track)
                    total_plays_by_same_artists += cur_stored_track['frequency']
            
            # Genre matching count
            cur_song_artist_genres = set(GetGenreList(cur_stored_track_artist_ids))
            if set(track_stats['artist_genres']).intersection(cur_song_artist_genres):
                songs_matching_genre.append(cur_stored_track)

        track_stats['songs_by_same_artists'] = songs_by_same_artists
        track_stats['total_plays_by_same_artists'] = total_plays_by_same_artists
        
        # Add actual tracks for songs_matching_genre
        track_stats['songs_matching_genre'] = songs_matching_genre
        track_stats['shuffle_ids'] = track_trie.getShuffleIDs(track_id)

        try:
            unique_patterns = {}
            patterns = track_trie.findAllPatterns(track_id)
            for pattern_track_ids in patterns.values():
                if not pattern_track_ids or len(pattern_track_ids) < 2:
                    continue
                
                pattern_tuple = tuple(t_id for t_id in pattern_track_ids)

                if pattern_tuple not in unique_patterns:
                    cur_pattern = []
                    for track_id in pattern_track_ids:
                        cur_pattern.append({"id": track_id, "name": stored_tracks[track_id]['name']})

                        unique_patterns[pattern_tuple] = {
                            'count': 0,
                            'pattern': cur_pattern
                        }
                        
                unique_patterns[pattern_tuple]['count'] += 1   
 
            # Filter out empty patterns for a cleaner response
            track_stats['patterns'] = list(unique_patterns.values())

        except KeyError:
            # If the track_id isn't in the trie, it means no patterns were recorded for it
            track_stats['patterns'] = []
        except Exception as e:
            # Log any other errors during pattern finding but don't fail the whole request
            print(f"Error finding patterns for track {track_id}: {e}")
            track_stats['patterns'] = [] # Send empty patterns on error
        
        return jsonify(track_stats)

    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return jsonify({"status": "error", "error": "Token expired, please log in again"}), 401
        return jsonify({"status": "error", "error": f"Spotify API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/shuffle_order/<int:shuffle_id>/<string:track_id>')
def get_shuffle_order_route(shuffle_id, track_id):
    token_info = session.get('token_info')
    if not token_info:
        return jsonify({"status": "error", "error": "Not logged in"}), 401

    try:
        # Assuming track_trie.getShuffleOrder(shuffle_id) exists and returns the full deque of track IDs
        # If it doesn't exist, you'll need to implement it in your TrackTrie class.
        # It should return the original deque of track IDs from that specific shuffle.
        selected_track_full_shuffle = track_trie.getShuffleQueue(shuffle_id, track_id)
        if not selected_track_full_shuffle:
            return jsonify({"status": "error", "error": f"Shuffle ID {shuffle_id} not found."}), 404
        
        # Convert track IDs to track objects with names and artists for frontend display
        formatted_shuffle_order = []
        for track_id in selected_track_full_shuffle:
            track_info = stored_tracks.get(track_id)
            formatted_shuffle_order.append({
                "id": track_id,
                "name": track_info.get('name', 'Unknown Track'),
                "artists": track_info.get('artists', [])
            })

        return jsonify({"status": "success", "shuffle_order": formatted_shuffle_order})

    except Exception as e:
        print(f"Error fetching shuffle order for ID {shuffle_id}: {e}")
        return jsonify({"status": "error", "error": f"Failed to retrieve shuffle order: {str(e)}"}), 500


if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)