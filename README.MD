# Software Architecture SCS2303 – Microservices + Design Patterns

This project demonstrates a small university system built with three services (Student, Faculty, Administrator) and applies three classic design patterns: Observer, Factory Method, and Strategy. It includes an end-to-end test that validates the behaviors.

- Language/Framework: Python 3.11 + Flask
- Services: StudentService, FacultyService, AdminService
- Patterns:
  - Observer: decoupled notifications and roster updates via an EventBus
  - Factory Method: role-based UI and DTO creation
  - Strategy: pluggable enrollment validations and grade processing

## Repository layout

- `main.py` — all services, event bus, factories, strategies, and (optionally) a demo runner
- `tests/test_system.py` — end-to-end test suite that spins up services and exercises flows
- `SA-Assignment-3-2025.pdf` — assignment brief (if provided by course)

## Architecture (microservice-style)

Each service is a Flask app with its own routes and responsibilities. For assignment purposes, services run in the same Python process (easy to start together), but on different ports to simulate microservices. They communicate via HTTP and an in-process EventBus that mimics asynchronous eventing.

- StudentService (default port 5001)
  - Owns student-facing APIs: listing courses, enrollment, and dropping
  - Publishes events: `student_enrolled`, `student_dropped`
- FacultyService (default port 5002)
  - Owns faculty-facing APIs: rosters, grade submission
  - Subscribes to student events to auto-update rosters
  - Publishes events: `grade_submitted`
- AdminService (default port 5003)
  - Owns admin-facing APIs: create course, reports, system config updates
  - Publishes events: `course_created`, `system_config_updated`
- NotificationService
  - Subscribes to all events and prints notifications (advisor, billing, students, admins)

In a production setup you’d split these into separate deployables and replace the in-process EventBus with a broker (RabbitMQ/Kafka/NATS). For coursework, this structure suffices to show microservice separation and async Observer behavior.

## Design patterns mapping

- Observer (Behavioral)

  - EventBus: central pub/sub for domain events
  - StudentService publishes enroll/drop ->
    - FacultyService updates rosters
    - NotificationService informs advisor/billing and logs waitlist notifications
  - FacultyService publishes grade_submitted ->
    - NotificationService emails student and informs administrators
  - AdminService publishes course/system events ->
    - NotificationService notifies stakeholders

- Factory Method (Creational)

  - Role UI Factories: `StudentUIFactory`, `FacultyUIFactory`, `AdminUIFactory` return role-specific menus and permissions (served via `/ui`)
  - DTO Factories: `StudentDTOFactory`, `FacultyDTOFactory`, `AdminDTOFactory` format responses per role

- Strategy (Behavioral)
  - Enrollment validation strategies: `PrerequisiteValidationStrategy`, `CapacityValidationStrategy`, `ScheduleConflictValidationStrategy` are selected by context and executed before enrollment
  - Grade processing strategies: `LetterGradeStrategy`, `PassFailGradeStrategy` are chosen per course convention and validate grades before publishing events

## API endpoints

StudentService (5001)

- `GET /ui` — student UI (menus/permissions)
- `GET /courses` — list courses for students
- `POST /enroll` — enroll a student; body: `{ student_id, course_id }`
- `POST /drop` — drop a course; body: `{ student_id, course_id }`

FacultyService (5002)

- `GET /ui` — faculty UI
- `GET /my_courses` — list courses taught by faculty
- `GET /roster/<course_id>` — roster for a course
- `POST /submit_grades` — submit grades; body: `{ course_id, grades: [{ student_id, grade }, ...] }`

AdminService (5003)

- `GET /ui` — admin UI
- `GET /courses` — list courses for admins
- `POST /course` — create a course; body: `{ course_id, name, instructor, capacity, prerequisites }`
- `POST /config` — publish a system configuration update; body: `{ message }`
- `GET /reports/enrollment` — basic enrollment report (if implemented)

## How to run

These commands assume Windows PowerShell and that you created a virtual environment (recommended). If your course environment differs, adapt paths accordingly.

1. Install dependencies (one-time)

```powershell
# From repository root (nexus)
C:/Users/wwwka/OneDrive/Documents/repositories/nexus/.venv/Scripts/python.exe -m pip install -U flask requests pytest
```

1. Start the services and (optionally) the demo

```powershell
# From repository root (nexus)
cd C:\Users\wwwka\OneDrive\Documents\repositories\nexus
C:/Users/wwwka/OneDrive/Documents/repositories/nexus/.venv/Scripts/python.exe Software-Architecture-SCS2303/main.py
```

- Default ports: Student 5001, Faculty 5002, Admin 5003
- Stop with Ctrl+C

## Run the tests

The test suite starts services on test ports (5101–5103), exercises endpoints, and verifies expected outcomes.

```powershell
# From repository root (nexus)
C:/Users/wwwka/OneDrive/Documents/repositories/nexus/.venv/Scripts/python.exe -m pytest -q Software-Architecture-SCS2303/tests/test_system.py
```

If you want to run all tests in the folder:

```powershell
C:/Users/wwwka/OneDrive/Documents/repositories/nexus/.venv/Scripts/python.exe -m pytest -q Software-Architecture-SCS2303/tests
```

## Example flows (high level)

- Enrollment (Observer + Strategy):

  1. Student calls `POST /enroll`
  2. Strategies validate prerequisites, capacity, and conflicts
  3. On success, `student_enrolled` event is published
  4. FacultyService updates roster; NotificationService informs advisor and billing

- Grade submission (Observer + Strategy):

  1. Faculty submits grades via `POST /submit_grades`
  2. Grade strategy validates values (Letter or Pass/Fail)
  3. `grade_submitted` events are published
  4. NotificationService informs student and administrators

- System update (Observer):
  1. Admin posts `POST /config`
  2. `system_config_updated` event is published
  3. NotificationService notifies stakeholders

## Notes and assumptions

- In-memory data for simplicity; restarts reset state
- In-process EventBus for the assignment; replace with a real broker in production
- Minimal input validation to keep focus on pattern usage

## Troubleshooting

- “Address already in use”: Make sure ports 5001–5003 (or 5101–5103 for tests) aren’t used by another process.
- 400 errors on enroll: Check that the student meets prerequisites or choose a course without them (e.g., CS101).
- 400 errors on grades: Ensure grade values match the strategy (e.g., A/A-/B+, or P/F for pass/fail).

---

This implementation is tailored for a university assignment: it clearly demonstrates microservice-style separation and the application of Observer, Factory Method, and Strategy patterns, with tests to verify behavior.
