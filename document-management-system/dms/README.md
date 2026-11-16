# Digital Document Management System

A simple Flask + SQLite base project.

## Features
- User registration / login (hashed passwords)
- Upload documents with title and category (type + 16 MB limit)
- Search by title/filename, filter by category
- Download and delete (each user only sees their own files)

## Run
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000 and register an account.

## Structure
    app.py            routes, database, auth, upload logic
    templates/        base.html, auth.html, index.html
    uploads/          stored files (auto-created)
    dms.db            SQLite database (auto-created)

## Ideas to extend
Version history, sharing/roles, tags, OCR/full-text search, cloud storage, audit log.
