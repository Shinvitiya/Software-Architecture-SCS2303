from flask import Flask, request, jsonify
from abc import ABC, abstractmethod
from datetime import datetime
import threading
import queue
import json
import requests
from typing import List, Dict, Any, Optional, Callable
import time

# ==================== SHARED MODELS AND INTERFACES ====================

class User:
    def __init__(self, user_id: str, name: str, email: str, user_type: str):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.user_type = user_type

class Course:
    def __init__(self, course_id: str, name: str, instructor: str, capacity: int, 
                 enrolled: int = 0, prerequisites: Optional[List[str]] = None):
        self.course_id = course_id
        self.name = name
        self.instructor = instructor
        self.capacity = capacity
        self.enrolled = enrolled
        self.prerequisites = prerequisites or []
        self.schedule = {"days": ["Mon", "Wed"], "time": "10:00-11:30", "location": "Room 101"}

class Event:
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.now()

# ==================== DESIGN PATTERN 1: OBSERVER PATTERN (EVENT-DRIVEN) ====================

class EventBus:
    """Singleton Event Bus for microservices communication"""
    _instance = None
    _lock = threading.Lock()
    # Type declarations to satisfy static checkers
    subscribers: Dict[str, List[Callable]]
    event_queue: queue.Queue
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.subscribers = {}
                    cls._instance.event_queue = queue.Queue()
                    cls._instance._start_event_processor()
        return cls._instance
    
    def subscribe(self, event_type: str, callback):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
    
    def publish(self, event: Event):
        self.event_queue.put(event)
    
    def _start_event_processor(self):
        def process_events():
            while True:
                try:
                    event = self.event_queue.get(timeout=1)
                    if event.event_type in self.subscribers:
                        for callback in self.subscribers[event.event_type]:
                            try:
                                callback(event)
                            except Exception as e:
                                print(f"Error processing event {event.event_type}: {e}")
                    self.event_queue.task_done()
                except queue.Empty:
                    continue
        
        thread = threading.Thread(target=process_events, daemon=True)
        thread.start()

# ==================== DESIGN PATTERN 2: FACTORY METHOD PATTERN ====================

class DTOFactory(ABC):
    @abstractmethod
    def create_response_dto(self, data: Any) -> Dict[str, Any]:
        pass

class StudentDTOFactory(DTOFactory):
    def create_response_dto(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, Course):
            return {
                "course_id": data.course_id,
                "name": data.name,
                "instructor": data.instructor,
                "available_seats": data.capacity - data.enrolled,
                "schedule": data.schedule,
                "prerequisites": data.prerequisites,
                "can_enroll": True  # Student-specific field
            }
        elif isinstance(data, list):  # List of courses
            return {"courses": [self.create_response_dto(course) for course in data]}
        return {"error": "Unsupported data type"}

class FacultyDTOFactory(DTOFactory):
    def create_response_dto(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, Course):
            return {
                "course_id": data.course_id,
                "name": data.name,
                "enrollment_count": data.enrolled,
                "capacity": data.capacity,
                "enrollment_percentage": round((data.enrolled / data.capacity) * 100, 2)
            }
        elif isinstance(data, dict) and "students" in data:  # Roster data
            return {
                "course_id": data.get("course_id"),
                "students": data["students"],
                "total_enrolled": len(data["students"])
            }
        return {"error": "Unsupported data type"}

class AdminDTOFactory(DTOFactory):
    def create_response_dto(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, Course):
            return {
                "course_id": data.course_id,
                "name": data.name,
                "instructor": data.instructor,
                "capacity": data.capacity,
                "enrolled": data.enrolled,
                "utilization_rate": round((data.enrolled / data.capacity) * 100, 2),
                "schedule": data.schedule,
                "prerequisites": data.prerequisites,
                "status": "active"
            }
        elif isinstance(data, dict) and "report_type" in data:  # Report data
            return {
                "report_type": data["report_type"],
                "generated_at": datetime.now().isoformat(),
                "data": data.get("data", []),
                "summary": data.get("summary", {})
            }
        return {"error": "Unsupported data type"}

# ==================== FACTORY METHOD (ROLE UI FACTORY) ====================

class RoleUIFactory(ABC):
    @abstractmethod
    def create_ui(self) -> Dict[str, Any]:
        pass

class StudentUIFactory(RoleUIFactory):
    def create_ui(self) -> Dict[str, Any]:
        return {
            "role": "student",
            "menus": ["Dashboard", "Courses", "Enrollments"],
            "permissions": ["view_courses", "enroll", "drop"],
            "routes": {"list_courses": "/courses", "enroll": "/enroll", "drop": "/drop"}
        }

class FacultyUIFactory(RoleUIFactory):
    def create_ui(self) -> Dict[str, Any]:
        return {
            "role": "faculty",
            "menus": ["My Courses", "Rosters", "Grades"],
            "permissions": ["view_rosters", "submit_grades"],
            "routes": {"my_courses": "/my_courses/<faculty_id>", "roster": "/roster/<course_id>", "submit_grades": "/submit_grades"}
        }

class AdminUIFactory(RoleUIFactory):
    def create_ui(self) -> Dict[str, Any]:
        return {
            "role": "administrator",
            "menus": ["Courses", "Reports", "System Config"],
            "permissions": ["create_course", "view_reports", "update_system_config"],
            "routes": {"courses": "/courses", "create_course": "/course", "report": "/reports/enrollment", "config": "/config"}
        }

# ==================== DESIGN PATTERN 3: STRATEGY PATTERN ====================

class ValidationStrategy(ABC):
    @abstractmethod
    def validate(self, student_id: str, course_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        pass

class PrerequisiteValidationStrategy(ValidationStrategy):
    def validate(self, student_id: str, course_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        course = context.get("course")
        student_courses = context.get("student_completed_courses", [])
        
        if not course or not course.prerequisites:
            return {"valid": True, "message": "No prerequisites required"}
        
        missing_prereqs = [prereq for prereq in course.prerequisites if prereq not in student_courses]
        
        if missing_prereqs:
            return {
                "valid": False, 
                "message": f"Missing prerequisites: {', '.join(missing_prereqs)}"
            }
        return {"valid": True, "message": "Prerequisites satisfied"}

class CapacityValidationStrategy(ValidationStrategy):
    def validate(self, student_id: str, course_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        course = context.get("course")
        
        if not course:
            return {"valid": False, "message": "Course not found"}
        
        if course.enrolled >= course.capacity:
            return {"valid": False, "message": "Course is at full capacity"}
        
        return {"valid": True, "message": "Capacity available"}

class ScheduleConflictValidationStrategy(ValidationStrategy):
    def validate(self, student_id: str, course_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Simplified schedule conflict check
        student_schedule = context.get("student_current_courses", [])
        course = context.get("course")
        
        if not course:
            return {"valid": False, "message": "Course not found"}
        
        # In a real implementation, we would check for time conflicts
        # For this demo, we'll simulate by checking if student has more than 5 courses
        if len(student_schedule) >= 5:
            return {"valid": False, "message": "Schedule conflict: Maximum 5 courses allowed"}
        
        return {"valid": True, "message": "No schedule conflicts"}

class ValidationContext:
    def __init__(self):
        self.strategies = []
    
    def add_strategy(self, strategy: ValidationStrategy):
        self.strategies.append(strategy)
    
    def validate_all(self, student_id: str, course_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        results = []
        for strategy in self.strategies:
            result = strategy.validate(student_id, course_id, context)
            results.append(result)
            if not result["valid"]:
                break  # Stop on first validation failure
        return results

# ==================== STRATEGY PATTERN FOR GRADES ====================

class GradeProcessingStrategy(ABC):
    @abstractmethod
    def process(self, grades_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass

class LetterGradeStrategy(GradeProcessingStrategy):
    VALID = {"A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"}

    def process(self, grades_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        invalid = [g for g in grades_data if g.get("grade") not in self.VALID]
        return {
            "scheme": "letter",
            "valid": len(invalid) == 0,
            "invalid_entries": invalid
        }

class PassFailGradeStrategy(GradeProcessingStrategy):
    VALID = {"P", "F"}

    def process(self, grades_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        invalid = [g for g in grades_data if g.get("grade") not in self.VALID]
        return {
            "scheme": "pass_fail",
            "valid": len(invalid) == 0,
            "invalid_entries": invalid
        }

class GradeProcessor:
    def __init__(self, strategy: GradeProcessingStrategy):
        self.strategy = strategy
    
    def process(self, grades_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.strategy.process(grades_data)

# ==================== ADMIN NOTIFICATION FACTORY ====================

class NotificationFactory(ABC):
    @abstractmethod
    def create(self, notification_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

class AdminNotificationFactory(NotificationFactory):
    def create(self, notification_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        base: Dict[str, Any] = {"type": notification_type, "timestamp": datetime.now().isoformat()}
        if notification_type == "system_config_updated":
            base["message"] = data.get("message", "System configuration updated")
            base["recipients"] = ["students", "faculty", "administrators"]
        elif notification_type == "course_created":
            base["message"] = f"Course {data.get('course_id')} created"
            base["recipients"] = ["administrators", "faculty"]
        else:
            base["message"] = data.get("message", "Notification")
        return base

# ==================== NOTIFICATION SERVICE ====================

class NotificationService:
    def __init__(self):
        self.event_bus = EventBus()
        self._setup_event_subscriptions()

    def _setup_event_subscriptions(self):
        # Observer pattern: Subscribe to various events
        self.event_bus.subscribe("student_enrolled", self._handle_enrollment_notification)
        self.event_bus.subscribe("student_dropped", self._handle_drop_notification)
        self.event_bus.subscribe("grade_submitted", self._handle_grade_notification)
        self.event_bus.subscribe("course_created", self._handle_course_created_notification)
        self.event_bus.subscribe("system_config_updated", self._handle_system_config_notification)

    def _handle_enrollment_notification(self, event: Event):
        data = event.data
        print(f"NOTIFICATION: Student {data['student_id']} enrolled in {data['course_id']}")
        print(f"   → Notifying advisor: {data.get('advisor_email', 'advisor@university.edu')}")
        print(f"   → Updating billing system for course fees")

    def _handle_drop_notification(self, event: Event):
        data = event.data
        print(f"NOTIFICATION: Student {data['student_id']} dropped {data['course_id']}")
        print(f"   → Notifying waitlisted students")

    def _handle_grade_notification(self, event: Event):
        data = event.data
        print(f"NOTIFICATION: Grade {data['grade']} submitted for student {data['student_id']} in {data['course_id']}")
        print(f"   → Emailing student {data['student_id']}")
        print(f"   → Informing department administrator")

    def _handle_course_created_notification(self, event: Event):
        data = event.data
        print(f"NOTIFICATION: New course {data['course_id']} created by admin")

    def _handle_system_config_notification(self, event: Event):
        data = event.data
        msg = data.get("message", "Configuration changed")
        print(f"SYSTEM CONFIG UPDATE: {msg}")
        print("   → Notifying all stakeholders: students, faculty, administrators")

# ==================== STUDENT SERVICE ====================

class StudentService:
    def __init__(self, port=5001):
        self.app = Flask(__name__)
        self.port = port
        self.dto_factory = StudentDTOFactory()
        self.ui_factory = StudentUIFactory()
        self.event_bus = EventBus()

        # Mock data
        self.courses = {
            "CS101": Course("CS101", "Intro to Programming", "Dr. Smith", 30, 25, []),
            "CS201": Course("CS201", "Data Structures", "Dr. Johnson", 25, 20, ["CS101"]),
            "CS301": Course("CS301", "Algorithms", "Dr. Brown", 20, 15, ["CS101", "CS201"])
        }

        self.student_data = {
            "STU001": {
                "completed_courses": ["CS101"],
                "current_courses": ["CS201"],
                "enrollment_history": []
            }
        }

        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.route('/ui', methods=['GET'])
        def get_ui():
            return jsonify(self.ui_factory.create_ui())

        @self.app.route('/courses', methods=['GET'])
        def get_courses():
            """Get all available courses (Factory Method Pattern)"""
            courses_list = list(self.courses.values())
            response = self.dto_factory.create_response_dto(courses_list)
            return jsonify(response)
        
        @self.app.route('/enroll', methods=['POST'])
        def enroll_student():
            """Enroll student in course (Strategy Pattern + Observer Pattern)"""
            data = request.get_json(silent=True) or {}
            student_id = data.get('student_id')
            course_id = data.get('course_id')
            if not isinstance(student_id, str) or not isinstance(course_id, str):
                return jsonify({"error": "Invalid payload"}), 400
            
            course = self.courses.get(course_id)
            if not course:
                return jsonify({"error": "Course not found"}), 404
            
            # Strategy Pattern: Validate enrollment
            validator = ValidationContext()
            # Add prerequisite strategy only if applicable to the course
            if course.prerequisites:
                validator.add_strategy(PrerequisiteValidationStrategy())
            validator.add_strategy(CapacityValidationStrategy())
            validator.add_strategy(ScheduleConflictValidationStrategy())
            
            context = {
                "course": course,
                "student_completed_courses": self.student_data.get(student_id, {}).get("completed_courses", []),
                "student_current_courses": self.student_data.get(student_id, {}).get("current_courses", [])
            }
            
            validation_results = validator.validate_all(student_id, course_id, context)
            
            # Check if all validations passed
            if not all(result["valid"] for result in validation_results):
                failed_validation = next(result for result in validation_results if not result["valid"])
                return jsonify({
                    "success": False, 
                    "message": failed_validation["message"],
                    "validation_results": validation_results
                }), 400
            
            # Enroll student
            course.enrolled += 1
            if student_id not in self.student_data:
                self.student_data[student_id] = {"completed_courses": [], "current_courses": [], "enrollment_history": []}
            
            self.student_data[student_id]["current_courses"].append(course_id)
            self.student_data[student_id]["enrollment_history"].append({
                "course_id": course_id,
                "action": "enrolled",
                "timestamp": datetime.now().isoformat()
            })
            
            # Observer Pattern: Publish enrollment event
            event = Event("student_enrolled", {
                "student_id": student_id,
                "course_id": course_id,
                "advisor_email": f"advisor_{student_id}@university.edu"
            })
            self.event_bus.publish(event)
            
            return jsonify({
                "success": True,
                "message": f"Successfully enrolled in {course.name}",
                "validation_results": validation_results
            })
        
        @self.app.route('/drop', methods=['POST'])
        def drop_course():
            """Drop a course (Observer Pattern)"""
            data = request.get_json(silent=True) or {}
            student_id = data.get('student_id')
            course_id = data.get('course_id')
            if not isinstance(student_id, str) or not isinstance(course_id, str):
                return jsonify({"error": "Invalid payload"}), 400
            
            course = self.courses.get(course_id)
            if not course:
                return jsonify({"error": "Course not found"}), 404
            
            if student_id in self.student_data and course_id in self.student_data[student_id]["current_courses"]:
                course.enrolled -= 1
                self.student_data[student_id]["current_courses"].remove(course_id)
                
                # Observer Pattern: Publish drop event
                event = Event("student_dropped", {
                    "student_id": student_id,
                    "course_id": course_id
                })
                self.event_bus.publish(event)
                
                return jsonify({"success": True, "message": f"Successfully dropped {course.name}"})
            
            return jsonify({"error": "Student not enrolled in this course"}), 400
    
    def run(self):
        print(f"🎓 Student Service running on port {self.port}")
        self.app.run(port=self.port, debug=False, use_reloader=False)

# ==================== FACULTY SERVICE ====================

class FacultyService:
    def __init__(self, port=5002):
        self.app = Flask(__name__)
        self.port = port
        self.dto_factory = FacultyDTOFactory()
        self.ui_factory = FacultyUIFactory()
        self.event_bus = EventBus()

        # Mock data
        self.courses = {
            "CS101": Course("CS101", "Intro to Programming", "Dr. Smith", 30, 25),
            "CS201": Course("CS201", "Data Structures", "Dr. Johnson", 25, 20)
        }

        self.rosters = {
            "CS101": ["STU001", "STU002", "STU003"],
            "CS201": ["STU001", "STU004", "STU005"]
        }

        self.grades = {}

        # Subscribe to enrollment/drop events to keep rosters updated (Observer)
        self.event_bus.subscribe("student_enrolled", self._on_student_enrolled)
        self.event_bus.subscribe("student_dropped", self._on_student_dropped)

        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.route('/ui', methods=['GET'])
        def get_ui():
            return jsonify(self.ui_factory.create_ui())

        @self.app.route('/roster/<course_id>', methods=['GET'])
        def get_roster(course_id):
            """Get class roster (Factory Method Pattern)"""
            if course_id not in self.rosters:
                return jsonify({"error": "Course not found"}), 404
            
            roster_data = {
                "course_id": course_id,
                "students": [{"student_id": sid, "name": f"Student {sid}"} for sid in self.rosters[course_id]]
            }
            
            response = self.dto_factory.create_response_dto(roster_data)
            return jsonify(response)
        
        @self.app.route('/submit_grades', methods=['POST'])
        def submit_grades():
            """Submit grades for a course (Observer Pattern)"""
            data = request.get_json(silent=True) or {}
            course_id = data.get('course_id')
            grades_data = data.get('grades')  # List of {student_id, grade}
            
            if course_id not in self.courses:
                return jsonify({"error": "Course not found"}), 404
            if not isinstance(grades_data, list):
                return jsonify({"error": "Invalid grades payload"}), 400

            # Strategy Pattern: grade processing (letter vs pass/fail)
            strategy: GradeProcessingStrategy = LetterGradeStrategy()
            if course_id.startswith("PF"):
                strategy = PassFailGradeStrategy()
            processor = GradeProcessor(strategy)
            processed = processor.process(grades_data)
            if not processed["valid"]:
                return jsonify({"success": False, "error": "Invalid grade entries", "details": processed}), 400
            
            # Store grades
            if course_id not in self.grades:
                self.grades[course_id] = {}
            
            for grade_entry in grades_data:
                student_id = grade_entry['student_id']
                grade = grade_entry['grade']
                self.grades[course_id][student_id] = grade
                
                # Observer Pattern: Publish grade submission event
                event = Event("grade_submitted", {
                    "student_id": student_id,
                    "course_id": course_id,
                    "grade": grade
                })
                self.event_bus.publish(event)
            
            return jsonify({
                "success": True,
                "message": f"Grades submitted for {len(grades_data)} students in {course_id}",
                "processing": processed
            })
        
        @self.app.route('/my_courses/<faculty_id>', methods=['GET'])
        def get_faculty_courses(faculty_id):
            """Get courses taught by faculty member (Factory Method Pattern)"""
            # In this demo, we'll return all courses
            faculty_courses = list(self.courses.values())
            response_courses = []
            
            for course in faculty_courses:
                response_courses.append(self.dto_factory.create_response_dto(course))
            
            return jsonify({"courses": response_courses})

    # Observer callbacks within FacultyService
    def _on_student_enrolled(self, event: Event):
        data = event.data
        cid = data.get("course_id")
        sid = data.get("student_id")
        if not isinstance(cid, str) or not isinstance(sid, str):
            return
        if cid in self.rosters and sid not in self.rosters[cid]:
            self.rosters[cid].append(sid)
            print(f"FACULTY SERVICE: Added {sid} to roster for {cid}")

    def _on_student_dropped(self, event: Event):
        data = event.data
        cid = data.get("course_id")
        sid = data.get("student_id")
        if not isinstance(cid, str) or not isinstance(sid, str):
            return
        if cid in self.rosters and sid in self.rosters[cid]:
            self.rosters[cid].remove(sid)
            print(f"FACULTY SERVICE: Removed {sid} from roster for {cid}")
    
    def run(self):
        print(f"Faculty Service running on port {self.port}")
        self.app.run(port=self.port, debug=False, use_reloader=False)

# ==================== ADMINISTRATOR SERVICE ====================

class AdminService:
    def __init__(self, port=5003):
        self.app = Flask(__name__)
        self.port = port
        self.dto_factory = AdminDTOFactory()
        self.ui_factory = AdminUIFactory()
        self.notification_factory = AdminNotificationFactory()
        self.event_bus = EventBus()

        # Mock data
        self.courses = {
            "CS101": Course("CS101", "Intro to Programming", "Dr. Smith", 30, 25),
            "CS201": Course("CS201", "Data Structures", "Dr. Johnson", 25, 20),
            "CS301": Course("CS301", "Algorithms", "Dr. Brown", 20, 15)
        }

        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.route('/ui', methods=['GET'])
        def get_ui():
            return jsonify(self.ui_factory.create_ui())

        @self.app.route('/courses', methods=['GET'])
        def get_all_courses():
            """Get all courses with admin view (Factory Method Pattern)"""
            courses_list = list(self.courses.values())
            admin_courses = [self.dto_factory.create_response_dto(course) for course in courses_list]
            return jsonify({"courses": admin_courses})
        
        @self.app.route('/course', methods=['POST'])
        def create_course():
            """Create a new course (Observer Pattern)"""
            data = request.get_json(silent=True) or {}
            course_id = data.get('course_id')
            name = data.get('name')
            instructor = data.get('instructor')
            capacity = data.get('capacity', 20)
            prerequisites = data.get('prerequisites', [])
            # Validate and narrow types
            if not isinstance(course_id, str):
                return jsonify({"error": "Invalid payload: course_id"}), 400
            if not isinstance(name, str):
                return jsonify({"error": "Invalid payload: name"}), 400
            if not isinstance(instructor, str):
                return jsonify({"error": "Invalid payload: instructor"}), 400
            if not isinstance(capacity, int):
                try:
                    capacity = int(capacity)
                except Exception:
                    capacity = 20
            if not isinstance(prerequisites, list):
                prerequisites = []
            else:
                prerequisites = [str(p) for p in prerequisites]

            course_id_str: str = course_id
            name_str: str = name
            instructor_str: str = instructor
            
            if course_id_str in self.courses:
                return jsonify({"error": "Course already exists"}), 400
            
            new_course = Course(course_id_str, name_str, instructor_str, capacity, 0, prerequisites)
            self.courses[course_id_str] = new_course
            
            # Observer Pattern: Publish course creation event
            payload = {
                "course_id": course_id,
                "name": name,
                "instructor": instructor,
                "notification": self.notification_factory.create("course_created", {"course_id": course_id})
            }
            event = Event("course_created", payload)
            self.event_bus.publish(event)
            
            response = self.dto_factory.create_response_dto(new_course)
            return jsonify({"success": True, "course": response})
        
        @self.app.route('/reports/enrollment', methods=['GET'])
        def generate_enrollment_report():
            """Generate enrollment report (Factory Method Pattern + Strategy Pattern)"""
            # Strategy Pattern could be used here for different report types
            total_capacity = sum(course.capacity for course in self.courses.values())
            total_enrolled = sum(course.enrolled for course in self.courses.values())
            
            report_data = {
                "report_type": "enrollment_summary",
                "data": [
                    {
                        "course_id": course.course_id,
                        "name": course.name,
                        "enrolled": course.enrolled,
                        "capacity": course.capacity,
                        "utilization": round((course.enrolled / course.capacity) * 100, 2)
                    }
                    for course in self.courses.values()
                ],
                "summary": {
                    "total_courses": len(self.courses),
                    "total_capacity": total_capacity,
                    "total_enrolled": total_enrolled,
                    "overall_utilization": round((total_enrolled / total_capacity) * 100, 2)
                }
            }
            
            response = self.dto_factory.create_response_dto(report_data)
            return jsonify(response)

        @self.app.route('/config', methods=['POST'])
        def update_system_config():
            """Simulate a system-wide configuration change (Observer Pattern + Factory Method for notifications)."""
            data = request.get_json(silent=True) or {}
            message = data.get('message', 'System maintenance scheduled')
            notification = self.notification_factory.create("system_config_updated", {"message": message})
            # Publish a system-wide change event
            event = Event("system_config_updated", {"message": message, "notification": notification})
            self.event_bus.publish(event)
            return jsonify({"success": True, "message": message})
    
    def run(self):
        print(f"Admin Service running on port {self.port}")
        self.app.run(port=self.port, debug=False, use_reloader=False)

# ==================== MAIN APPLICATION AND DEMO ====================

def run_service_in_thread(service):
    """Helper function to run each service in its own thread"""
    thread = threading.Thread(target=service.run, daemon=True)
    thread.start()
    return thread

def demo_system():
    """Demonstrate the system functionality"""
    print("\n" + "="*60)
    print("🎓 NEXUS ENROLL SYSTEM DEMO")
    print("="*60)
    
    # Wait for services to start
    time.sleep(2)
    
    base_urls = {
        "student": "http://localhost:5001",
        "faculty": "http://localhost:5002", 
        "admin": "http://localhost:5003"
    }
    
    try:
        # 0. Fetch role-based UIs (Factory Method: UI creation)
        print("\n0. Fetching role-based UIs...")
        ui_student = requests.get(f"{base_urls['student']}/ui").json()
        ui_faculty = requests.get(f"{base_urls['faculty']}/ui").json()
        ui_admin = requests.get(f"{base_urls['admin']}/ui").json()
        print(f"   Student UI menus: {ui_student['menus']}")
        print(f"   Faculty UI menus: {ui_faculty['menus']}")
        print(f"   Admin UI menus: {ui_admin['menus']}")
        # 1. Admin creates a new course
        print("\n1. ADMIN: Creating a new course...")
        admin_response = requests.post(f"{base_urls['admin']}/course", json={
            "course_id": "CS401",
            "name": "Advanced Software Engineering", 
            "instructor": "Dr. Wilson",
            "capacity": 15,
            "prerequisites": ["CS201", "CS301"]
        })
        print(f"   Response: {admin_response.json()}")
        
        # 2. Student views available courses
        print("\n2. STUDENT: Viewing available courses...")
        courses_response = requests.get(f"{base_urls['student']}/courses")
        print(f"   Found {len(courses_response.json()['courses'])} courses")
        
        # 3. Student attempts enrollment (should succeed for CS201)
        print("\n3. STUDENT: Attempting to enroll in CS201...")
        enroll_response = requests.post(f"{base_urls['student']}/enroll", json={
            "student_id": "STU001",
            "course_id": "CS201"
        })
        print(f"   Response: {enroll_response.json()}")
        
        # 4. Student attempts enrollment in advanced course (should fail - missing prerequisites)
        print("\n4. STUDENT: Attempting to enroll in CS401 (should fail)...")
        enroll_fail_response = requests.post(f"{base_urls['student']}/enroll", json={
            "student_id": "STU002", 
            "course_id": "CS401"
        })
        print(f"   Response: {enroll_fail_response.json()}")
        
        # 5. Faculty views roster
        print("\n5. FACULTY: Viewing CS101 roster...")
        roster_response = requests.get(f"{base_urls['faculty']}/roster/CS101")
        print(f"   Response: {roster_response.json()}")
        
        # 6. Faculty submits grades
        print("\n6. FACULTY: Submitting grades...")
        grades_response = requests.post(f"{base_urls['faculty']}/submit_grades", json={
            "course_id": "CS101",
            "grades": [
                {"student_id": "STU001", "grade": "A"},
                {"student_id": "STU002", "grade": "B+"}
            ]
        })
        print(f"   Response: {grades_response.json()}")
        
        # 7. Admin generates report
        print("\n7. Generating enrollment report...")
        report_response = requests.get(f"{base_urls['admin']}/reports/enrollment")
        report_data = report_response.json()
        print(f"   Total Courses: {report_data['summary']['total_courses']}")
        print(f"   Overall Utilization: {report_data['summary']['overall_utilization']}%")
        
        # 8. Student drops a course
        print("\n8. STUDENT: Dropping CS201...")
        drop_response = requests.post(f"{base_urls['student']}/drop", json={
            "student_id": "STU001",
            "course_id": "CS201"
        })
        print(f"   Response: {drop_response.json()}")
        
        # 9. Admin performs a system-wide configuration update
        print("\n9. ADMIN: Updating system configuration...")
        cfg_response = requests.post(f"{base_urls['admin']}/config", json={
            "message": "System will undergo maintenance at 11 PM"
        })
        print(f"   Response: {cfg_response.json()}")
        
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: {e}")
        print("Make sure all services are running...")
    except Exception as e:
        print(f"Demo error: {e}")
    
    print("\n" + "="*60)
    print("DEMO COMPLETED")
    print("="*60)
    print("\nDesign Patterns Demonstrated:")
    print("Observer Pattern: Event-driven notifications between services")
    print("Factory Method: Service-specific DTO creation") 
    print("Strategy Pattern: Pluggable validation strategies")
    print("\nMicroservices Architecture:")
    print("Independent services with separate concerns")
    print("RESTful API communication")
    print("Event-driven inter-service communication")

if __name__ == "__main__":
    print("Starting NexusEnroll Microservices...")
    
    # Initialize notification service (Observer pattern)
    notification_service = NotificationService()
    
    # Create and start all services
    student_service = StudentService(5001)
    faculty_service = FacultyService(5002) 
    admin_service = AdminService(5003)
    
    # Run services in separate threads
    student_thread = run_service_in_thread(student_service)
    faculty_thread = run_service_in_thread(faculty_service)
    admin_thread = run_service_in_thread(admin_service)
    
    print("All services started successfully!")
    print("\nService URLs:")
    print("Student Service: http://localhost:5001")
    print("Faculty Service: http://localhost:5002") 
    print("Admin Service: http://localhost:5003")
    
    # Run demo
    demo_system()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down services...")