"""Local web server for the browser UI in webui/ (started by web.py).

Modules:
    config    paths, limits, job folder lookup and small shared helpers
    jobs      read-only views of job folders: summaries, details, progress, posters
    runner    starting new videos, versions and resumes in background threads
    library   renaming, deleting to the trash and restoring
    voices    the Edge TTS voice list, labelled by accent
    uploads   saving attached documents
    system    provider and footage status for the header
    server    the request handler (routes only; the work happens in the modules above)
    app       command-line entry point
"""
