from vanna_flask_app import app


if __name__ == "__main__":
    # Local run convenience (Vercel will import `app` directly)
    app.run(host="0.0.0.0", port=8084, debug=True)
