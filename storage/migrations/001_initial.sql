CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK(state IN ('PENDING','RUNNING','CANCEL_REQUESTED','COMPLETED','FAILED','CANCELLED','INTERRUPTED')),
    config_json TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    profile_sha256 TEXT NOT NULL,
    platform_sha TEXT NOT NULL,
    sut_sha TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    error_json TEXT
);
CREATE TABLE task_cases (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    logical_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    strategy TEXT NOT NULL,
    input_json TEXT NOT NULL,
    expectation_json TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('PENDING','RUNNING','PASSED','FAILED','ERROR','CANCELLED')),
    UNIQUE(task_id, ordinal),
    UNIQUE(task_id, logical_id)
);
CREATE TABLE case_results (
    case_id TEXT PRIMARY KEY REFERENCES task_cases(id) ON DELETE CASCADE,
    assertion_status TEXT NOT NULL CHECK(assertion_status IN ('PASSED','FAILED','ERROR','CANCELLED')),
    actual_json TEXT,
    reason TEXT NOT NULL,
    duration_ms REAL NOT NULL CHECK(duration_ms >= 0),
    attempt_count INTEGER NOT NULL CHECK(attempt_count >= 0),
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL
);
CREATE TABLE reports (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    format TEXT NOT NULL CHECK(format IN ('html','json')),
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(task_id, format)
);
CREATE INDEX tasks_created ON tasks(created_at DESC, id);
