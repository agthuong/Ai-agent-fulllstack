import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from asgiref.wsgi import WsgiToAsgi

# Import the Flask app instance from your app.py file
from app import app

async def main():
    """
    Main function to configure and run the Hypercorn server.
    """
    # Wrap the Flask WSGI app to make it an ASGI app
    asgi_app = WsgiToAsgi(app)

    # Configure Hypercorn
    # You can customize bind address, port, etc. here
    config = Config()
    config.bind = ["0.0.0.0:5000"]  # Same as default Flask port
    config.use_reloader = True # Enable auto-reloading for development
    
    print("Starting Hypercorn server for the Flask app...")
    print("Access the application at http://127.0.0.1:5001")

    # Run the server
    await serve(asgi_app, config)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped.") 