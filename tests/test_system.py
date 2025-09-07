import time
import requests
import threading
import importlib.util
from pathlib import Path


MAIN_PY = Path(__file__).resolve().parents[1] / "main.py"


def load_main_module():
    spec = importlib.util.spec_from_file_location("nexus_main", str(MAIN_PY))
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_service_in_thread(service):
    t = threading.Thread(target=service.run, daemon=True)
    t.start()
    return t


def wait_for_ready(url: str, timeout: float = 10.0):
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=1.5)
            if r.status_code in (200, 404):
                return True
        except Exception as e: 
            last_err = e
        time.sleep(0.2)
    raise AssertionError(f"Service at {url} not ready: {last_err}")


def setup_services():
    mod = load_main_module()
    _notif = mod.NotificationService()
    student = mod.StudentService(port=5101)
    faculty = mod.FacultyService(port=5102)
    admin = mod.AdminService(port=5103)

    ts = [
        run_service_in_thread(student),
        run_service_in_thread(faculty),
        run_service_in_thread(admin),
    ]

    wait_for_ready("http://localhost:5101/ui")
    wait_for_ready("http://localhost:5102/ui")
    wait_for_ready("http://localhost:5103/ui")

    return {
        "threads": ts,
        "base": {
            "student": "http://localhost:5101",
            "faculty": "http://localhost:5102",
            "admin": "http://localhost:5103",
        },
    }


def test_end_to_end_system():
    ctx = setup_services()
    base = ctx["base"]

    # 1) UI endpoints (Factory Method: role UIs)
    ui_student = requests.get(f"{base['student']}/ui").json()
    ui_faculty = requests.get(f"{base['faculty']}/ui").json()
    ui_admin = requests.get(f"{base['admin']}/ui").json()
    assert ui_student.get("role") == "student"
    assert ui_faculty.get("role") == "faculty"
    assert ui_admin.get("role") == "administrator"

    # 2) Admin: create a new course
    resp = requests.post(
        f"{base['admin']}/course",
        json={
            "course_id": "CS999",
            "name": "Systems Integration",
            "instructor": "Dr. Test",
            "capacity": 10,
            "prerequisites": ["CS201"],
        },
        timeout=5,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("success") is True
    assert data.get("course", {}).get("course_id") == "CS999"

    # 3) Admin: invalid payload
    bad = requests.post(
        f"{base['admin']}/course", json={"course_id": 123, "name": None, "instructor": []}, timeout=5
    )
    assert bad.status_code == 400

    # 4) Student: list courses
    courses = requests.get(f"{base['student']}/courses", timeout=5).json()
    assert "courses" in courses and isinstance(courses["courses"], list)
    assert any(c.get("course_id") == "CS101" for c in courses["courses"]) 

    # 5) Student: enroll success (Observer + Strategy validations)
    enroll = requests.post(
        f"{base['student']}/enroll", json={"student_id": "STU004", "course_id": "CS101"}, timeout=5
    )
    assert enroll.status_code == 200, enroll.text
    ej = enroll.json()
    assert ej.get("success") is True

    # 6) Faculty: roster reflects enrollment via observer
    for _ in range(20):
        roster = requests.get(f"{base['faculty']}/roster/CS101", timeout=5)
        if roster.status_code == 200:
            students = roster.json().get("students", [])
            if any(s.get("student_id") == "STU004" for s in students):
                break
        time.sleep(0.2)
    else:
        raise AssertionError("STU004 not added to CS101 roster via observer")

    # 7) Student: enroll failure (missing prereqs)
    fail = requests.post(
        f"{base['student']}/enroll", json={"student_id": "STU002", "course_id": "CS201"}, timeout=5
    )
    assert fail.status_code == 400
    fj = fail.json()
    assert fj.get("success") is False
    assert "Missing prerequisites" in fj.get("message", "")

    # 8) Faculty: submit invalid grades
    invalid_grades = requests.post(
        f"{base['faculty']}/submit_grades",
        json={"course_id": "CS101", "grades": [{"student_id": "STU004", "grade": "Z"}]},
        timeout=5,
    )
    assert invalid_grades.status_code == 400

    # 9) Faculty: submit valid grades
    valid_grades = requests.post(
        f"{base['faculty']}/submit_grades",
        json={
            "course_id": "CS101",
            "grades": [
                {"student_id": "STU004", "grade": "A"},
                {"student_id": "STU001", "grade": "B+"},
            ],
        },
        timeout=5,
    )
    assert valid_grades.status_code == 200, valid_grades.text
    vg = valid_grades.json()
    assert vg.get("success") is True

    # 10) Student: drop course and roster reflects removal
    drop = requests.post(
        f"{base['student']}/drop", json={"student_id": "STU004", "course_id": "CS101"}, timeout=5
    )
    assert drop.status_code == 200, drop.text
    for _ in range(20):
        roster2 = requests.get(f"{base['faculty']}/roster/CS101", timeout=5)
        students2 = roster2.json().get("students", [])
        if all(s.get("student_id") != "STU004" for s in students2):
            break
        time.sleep(0.2)
    else:
        raise AssertionError("STU004 not removed from CS101 roster via observer after drop")

    # 11) Admin: system config update
    cfg = requests.post(f"{base['admin']}/config", json={"message": "Testing config"}, timeout=5)
    assert cfg.status_code == 200
