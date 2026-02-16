"""
Standalone Log Viewer Server
Run this separately from your main experiment server if you prefer
"""
from flask import Flask
from log_viewer_routes import register_log_viewer_routes

app = Flask(__name__)

# Register log viewer routes
register_log_viewer_routes(app)

@app.route('/')
def index():
    """Redirect to log viewer"""
    from flask import redirect
    return redirect('/logs')

if __name__ == '__main__':
    print("=" * 50)
    print("  Log Viewer Server Starting")
    print("=" * 50)
    print("")
    print("  Access at: http://localhost:5001")
    print("")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)