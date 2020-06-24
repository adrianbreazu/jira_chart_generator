create table if not exists project (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT
);

create table if not exists type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
);

create table if not exists status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
);

create table if not exists resolution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
);

create table if not exists sprint (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id TEXT,
    name TEXT,
    sequence TEXT,
    state TEXT,
    goal TEXT,
    start_date TEXT,
    end_date TEXT,
    complete_date TEXT
);

create table if not exists version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id TEXT,
    name TEXT,
    archived TEXT,
    released TEXT,
    start_date TEXT,
    released_date TEXT
);

create table if not exists issue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT,
    summary TEXT,
    epic_name TEXT,
    labels TEXT,
    creation_date TEXT,
    resolution_date TEXT,
    updated_date TEXT,
    start_date TEXT,
    due_date TEXT,
    priority TEXT,
    assignee TEXT,
    reporter TEXT,
    components TEXT,
    epic_link TEXT,
    story_points TEXT,
    tshirt_size TEXT,
    linked_theme TEXT,
    resolution_id INTEGER,
    status_id INTEGER,
    type_id INTEGER,
    project_id INTEGER,
    raw_value TEXT,
    FOREIGN KEY (resolution_id) REFERENCES resolution(id),
    FOREIGN KEY (status_id) REFERENCES status(id),
    FOREIGN KEY (type_id) REFERENCES type(id),
    FOREIGN KEY (project_id) REFERENCES project(id)
);

create table if not exists issue_sprints (
    issue_id INTEGER NOT NULL,
    sprint_id INTEGER NOT NULL,
    FOREIGN KEY (issue_id) REFERENCES issue(id),
    FOREIGN KEY (sprint_id) REFERENCES sprint(id)
);

create table if not exists issue_fix_version (
    issue_id INTEGER NOT NULL,
    version_id INTEGER NOT NULL,
    FOREIGN KEY (issue_id) REFERENCES issue(id),
    FOREIGN KEY (version_id) REFERENCES version(id)
);

create table if not exists issue_affects_version (
    issue_id INTEGER NOT NULL,
    version_id INTEGER NOT NULL,
    FOREIGN KEY (issue_id) REFERENCES issue(id),
    FOREIGN KEY (version_id) REFERENCES version(id)
);