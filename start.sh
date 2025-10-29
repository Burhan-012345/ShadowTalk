#!/bin/bash
echo "🚀 Starting ShadowTalk Production Server"
exec gunicorn --config deploy/gunicorn.conf.py app:app
