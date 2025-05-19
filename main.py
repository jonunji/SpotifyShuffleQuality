import os
from flask import Flask, render_template, redirect, request, session
from spotipy.oauth2 import SpotifyOAuth
import spotipy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a real secret in production

# Only needed scopes for now
SCOPE = "playlist-read-private"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    auth_manager = SpotifyOAuth(scope=SCOPE)
    auth_url = auth_manager.get_authorize_url()
    session['auth_manager'] = auth_manager  # Store manager in session if needed
    return redirect(auth_url)

@app.route('/callback')
def callback():
    sp_oauth = SpotifyOAuth(scope=SCOPE)
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect('/playlists')

@app.route('/playlists')
def playlists():
    token_info = session.get('token_info', None)
    if not token_info:
        return redirect('/login')

    sp = spotipy.Spotify(auth=token_info['access_token'])
    results = sp.current_user_playlists(limit=20)['items']

    return render_template('playlists.html', playlists=results)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
