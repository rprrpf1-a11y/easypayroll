"""
Production WSGI Runner for EasyPayroll
Powered by Waitress (production-grade multi-threaded WSGI server)
"""
import os
import sys
from waitress import serve
from app import app

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    threads = int(os.environ.get("THREADS", 8))

    print("=" * 60)
    print(" 🚀 EasyPayroll Production Server Starting")
    print(f" • Listening on: http://{host}:{port}")
    print(f" • Local Access: http://127.0.0.1:{port}")
    print(f" • Worker Threads: {threads}")
    print(" • Production Engine: Waitress WSGI")
    print("=" * 60)

    serve(app, host=host, port=port, threads=threads)
