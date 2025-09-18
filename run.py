import socket
import threading
import webbrowser
import sys
import visiofirm
import atexit  
from visiofirm.errortracker import VFSessionTracker 
import uvicorn 

app = visiofirm.create_app()

def find_free_port(start_port=8000):
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                port += 1 

def main():
    # Handle version flags
    if any(arg in ('-V', '--version') for arg in sys.argv[1:]):
        print(f"VisioFirm v{visiofirm.__version__}")
        return

    port = find_free_port()
    url = f"http://localhost:{port}"
    
    print(r"""
WELCOME TO
 _   _ _____ _____ _____ ____  _____ _____ _____ 
 __      ___     _       ______ _                
  \ \    / (_)   (_)     |  ____(_)               
   \ \  / / _ ___ _  ___ | |__   _ _ __ _ __ ___  
    \ \/ / | / __| |/ _ \|  __| | | '__| '_ ` _ \ 
     \  /  | \__ \ | (_) | |    | | |  | | | | | |
      \/   |_|___/_|\___/|_|    |_|_|  |_| |_| |_|                          

You are currently running the version:
VisioFirm v{}

VisioFirm running in {}
Stay updated by visiting our GitHub Repository https://github.com/OschAI/VisioFirm
""".format(visiofirm.__version__, url))
    
    tracker = VFSessionTracker()
    tracker.start_session() 
    app.tracker = tracker 
    
    def shutdown_tracker():
        tracker.end_session(print_path=True) 
    atexit.register(shutdown_tracker)
    
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    
    config = uvicorn.Config(
        app=app, 
        host="localhost", 
        port=port, 
        access_log=False, 
        log_level="info", 
        reload=False 
    )
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    main()