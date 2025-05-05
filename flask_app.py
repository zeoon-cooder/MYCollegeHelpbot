from flask import Flask, jsonify
import os
from database import get_user_stats, DB_PATH

app = Flask(__name__)

@app.route('/')
def index():
    """Index page showing bot status"""
    # Get the bot stats
    stats = get_user_stats()
    
    if not stats:
        return "Educational Resources Bot - Unable to fetch stats", 500
    
    # Return a very simple HTML page
    return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Bot Status</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f4f4f4;
                color: #333;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 800px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #2c3e50;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
            }}
            ul li {{
                margin-bottom: 10px;
                background: #ecf0f1;
                padding: 10px;
                border-radius: 5px;
            }}
            code {{
                background: #dfe6e9;
                padding: 2px 6px;
                border-radius: 4px;
            }}
            .section {{
                margin-top: 30px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📚 Educational Resources Bot Status</h1>
            <p>✅ The bot is <strong>running</strong>.</p>

            <div class="section">
                <h2>📊 Stats</h2>
                <ul>
                    <li><strong>Total Users:</strong> {stats['total_users']}</li>
                    <li><strong>Active Subscribers:</strong> {stats['active_subscribers']}</li>
                    <li><strong>Total Payments:</strong> {stats['total_payments']}</li>
                    <li><strong>Pending Payments:</strong> {stats['pending_payments']}</li>
                    <li><strong>Total Resources:</strong> {stats['total_resources']}</li>
                    <li><strong>Subject Count:</strong> {stats['subject_count']}</li>
                </ul>
            </div>

            <div class="section">
                <h2>🛠 Admin Commands</h2>
                <ul>
                    <li><code>/verify &lt;ref_id&gt;</code> - Verify a user's payment</li>
                    <li><code>/grant_access &lt;telegram_id&gt;</code> - Grant subscription access</li>
                    <li><code>/add_resource &lt;code&gt; &lt;unit&gt; &lt;type&gt; &lt;link&gt;</code> - Add resource</li>
                    <li><code>/stats</code> - Show bot statistics</li>
                </ul>
            </div>

            <div class="section">
                <h2>ℹ️ Bot Information</h2>
                <ul>
                    <li><strong>UPI ID:</strong> {os.environ.get('UPI_ID', 'Not set')}</li>
                    <li><strong>Free Searches:</strong> 4</li>
                    <li><strong>Subscription:</strong> ₹21 for 1 week</li>
                </ul>
            </div>
        </div>
    </body>
    </html>"""

@app.route('/health')
def health():
    """Health endpoint for monitoring"""
    return jsonify({"status": "ok"})

@app.route('/stats')
def stats():
    """API endpoint to get bot stats"""
    stats = get_user_stats()
    if not stats:
        return jsonify({"error": "Unable to fetch stats"}), 500
    return jsonify(stats)