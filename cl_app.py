from flask import Flask

_CSS = """
body {
    background-color: #f0f0f0;
    font-family: Arial, sans-serif;
}

.header {
    text-align: center;
    padding: 20px;
}

.footer {
    text-align: center;
    padding: 20px;
    position: fixed;
    bottom: 0;
    width: 100%;
}
"""

# Create Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return '''
    <html>
    <style>{}</style>
    <body>
        <div class="header">
            <h1>Welcome to Your Fantasy Teams App</h1>
        </div>
        <!-- Add your content here -->
        <div class="footer">
            <p>&copy; 2026 Fantasy Teams</p>
        </div>
    </body>
    </html>
    '''.format(_CSS)

if __name__ == '__main__':
    app.run()