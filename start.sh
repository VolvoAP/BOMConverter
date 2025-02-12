#!/bin/bash
# Start the web server with Gunicorn
gunicorn app:app --workers=1 --threads=4 --timeout 300 &

# Start your secondary Python script
python "ARO_RIPPER_HTML.py"

# Wait for both processes to finish
wait
