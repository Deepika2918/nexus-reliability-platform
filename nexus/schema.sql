-- NEXUS SQLite schema (see ARCHITECTURE.md)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    next_retry_at TEXT,
    assigned_worker_id TEXT,
    lease_expires_at TEXT,
    last_error TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_works_status ON works(status);
CREATE INDEX IF NOT EXISTS idx_works_next_retry ON works(next_retry_at);

CREATE TABLE IF NOT EXISTS completions (
    work_id TEXT PRIMARY KEY REFERENCES works(id),
    result TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    completion_count INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    restart_count INTEGER NOT NULL DEFAULT 0,
    max_restarts INTEGER NOT NULL DEFAULT 5,
    restart_window_start TEXT,
    last_heartbeat_at TEXT,
    last_failure_at TEXT,
    next_restart_at TEXT,
    failure_mode TEXT NOT NULL DEFAULT 'normal',
    release_version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_subject ON events(subject_type, subject_id);

CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    version TEXT NOT NULL,
    previous_version TEXT,
    status TEXT NOT NULL,
    deployed_at TEXT NOT NULL,
    rolled_back_at TEXT
);
