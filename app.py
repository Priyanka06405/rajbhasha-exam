import os
import csv
import random
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "rajbhasha-exam-secret-key-change-this"
)

# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

database_url = os.environ.get("DATABASE_URL")

if database_url:
    # Render/PostgreSQL sometimes gives postgres://
    # SQLAlchemy requires postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url

else:
    # Local/testing database
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///exam.db"


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================================================
# DATABASE MODELS
# =========================================================

class Participant(db.Model):
    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(200),
        nullable=False
    )

    # Internally called registration_id.
    # On the website this is displayed as Personal Number.
    registration_id = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    registered_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    attempts = db.relationship(
        "Attempt",
        backref="participant",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    question_text = db.Column(
        db.Text,
        nullable=False
    )

    option_a = db.Column(
        db.Text,
        nullable=False
    )

    option_b = db.Column(
        db.Text,
        nullable=False
    )

    option_c = db.Column(
        db.Text,
        nullable=False
    )

    option_d = db.Column(
        db.Text,
        nullable=False
    )

    correct_answer = db.Column(
        db.String(1),
        nullable=False
    )


class Attempt(db.Model):
    __tablename__ = "attempts"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    participant_id = db.Column(
        db.Integer,
        db.ForeignKey("participants.id"),
        nullable=False
    )

    started_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    submitted_at = db.Column(
        db.DateTime,
        nullable=True
    )

    status = db.Column(
        db.String(30),
        default="IN_PROGRESS"
    )

    score = db.Column(
        db.Integer,
        default=0
    )

    total_questions = db.Column(
        db.Integer,
        default=0
    )

    # Stores answers such as:
    # {"1": "A", "2": "C", "3": "B"}
    answers = db.Column(
        db.JSON,
        default=dict
    )

    answer_records = db.relationship(
        "Answer",
        backref="attempt",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Answer(db.Model):
    __tablename__ = "answers"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    attempt_id = db.Column(
        db.Integer,
        db.ForeignKey("attempts.id"),
        nullable=False
    )

    question_id = db.Column(
        db.Integer,
        db.ForeignKey("questions.id"),
        nullable=False
    )

    selected_answer = db.Column(
        db.String(1),
        nullable=True
    )

    is_correct = db.Column(
        db.Boolean,
        default=False
    )


# =========================================================
# QUESTION LOADING
# =========================================================

def read_questions_from_csv():
    """
    Read all questions from questions.csv.
    Returns a list of dictionaries.
    """

    questions = []

    if not os.path.exists("questions.csv"):
        print("WARNING: questions.csv not found.")
        return questions

    with open(
        "questions.csv",
        "r",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            question_text = row.get("question", "").strip()
            option_a = row.get("option_a", "").strip()
            option_b = row.get("option_b", "").strip()
            option_c = row.get("option_c", "").strip()
            option_d = row.get("option_d", "").strip()
            correct_answer = row.get(
                "correct_answer",
                ""
            ).strip().upper()

            if not question_text:
                continue

            if not option_a:
                continue

            if not option_b:
                continue

            if not option_c:
                continue

            if not option_d:
                continue

            if correct_answer not in ["A", "B", "C", "D"]:
                print(
                    "WARNING: Invalid correct answer:",
                    correct_answer
                )
                continue

            questions.append({
                "question": question_text,
                "option_a": option_a,
                "option_b": option_b,
                "option_c": option_c,
                "option_d": option_d,
                "correct_answer": correct_answer
            })

    return questions


def sync_questions():
    """
    Synchronize the database with questions.csv.

    If the CSV question count is different from the database,
    the existing questions are replaced with the CSV questions.

    This is useful when we replace the sample 3 questions
    with the final 60 questions.
    """

    csv_questions = read_questions_from_csv()

    if not csv_questions:
        print("No questions found in questions.csv.")
        return

    database_count = Question.query.count()
    csv_count = len(csv_questions)

    print(
        f"Database questions: {database_count}"
    )

    print(
        f"CSV questions: {csv_count}"
    )

    # If counts are different, reload everything.
    if database_count != csv_count:

        print(
            "Question count changed. "
            "Reloading questions..."
        )

        # Delete existing questions
        Question.query.delete()

        db.session.commit()

        for item in csv_questions:

            question = Question(
                question_text=item["question"],
                option_a=item["option_a"],
                option_b=item["option_b"],
                option_c=item["option_c"],
                option_d=item["option_d"],
                correct_answer=item["correct_answer"]
            )

            db.session.add(question)

        db.session.commit()

        print(
            f"Questions loaded: {csv_count}"
        )

    else:
        print(
            "Question count matches CSV. "
            "No reload required."
        )


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def initialize_database():

    with app.app_context():

        db.create_all()

        print("")
        print("==============================")
        print("DATABASE TABLES READY")
        print("==============================")

        sync_questions()

        print("")
        print(
            f"Participants: {Participant.query.count()}"
        )

        print(
            f"Questions: {Question.query.count()}"
        )

        print("==============================")
        print("")


# Automatically initialize database
initialize_database()


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template(
        "login.html"
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        registration_id = request.form.get(
            "registration_id",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # ---------------------------------------------
        # Validate fields
        # ---------------------------------------------

        if not name:
            flash(
                "Please enter your full name."
            )

            return redirect(
                url_for("register")
            )

        if not registration_id:
            flash(
                "Please enter your Personal Number."
            )

            return redirect(
                url_for("register")
            )

        if not password:
            flash(
                "Please create a password."
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 4:
            flash(
                "Password must be at least 4 characters."
            )

            return redirect(
                url_for("register")
            )

        # ---------------------------------------------
        # Check duplicate Personal Number
        # ---------------------------------------------

        existing_participant = Participant.query.filter_by(
            registration_id=registration_id
        ).first()

        if existing_participant:

            flash(
                "This Personal Number is already registered. "
                "Please login instead."
            )

            return redirect(
                url_for("login")
            )

        # ---------------------------------------------
        # Create participant
        # ---------------------------------------------

        participant = Participant(
            name=name,
            registration_id=registration_id,
            password_hash=generate_password_hash(
                password
            )
        )

        db.session.add(participant)

        db.session.commit()

        flash(
            "Registration successful. "
            "Please login to continue."
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        registration_id = request.form.get(
            "registration_id",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        participant = Participant.query.filter_by(
            registration_id=registration_id
        ).first()

        if participant is None:

            flash(
                "Personal Number not found. "
                "Please register first."
            )

            return redirect(
                url_for("login")
            )

        if not check_password_hash(
            participant.password_hash,
            password
        ):

            flash(
                "Incorrect password."
            )

            return redirect(
                url_for("login")
            )

        # ---------------------------------------------
        # Login successful
        # ---------------------------------------------

        session.clear()

        session["participant_id"] = participant.id

        return redirect(
            url_for("start")
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out."
    )

    return redirect(
        url_for("login")
    )


# =========================================================
# START EXAM
# =========================================================

@app.route("/start")
def start():

    participant_id = session.get(
        "participant_id"
    )

    if not participant_id:

        return redirect(
            url_for("login")
        )

    participant = db.session.get(
        Participant,
        participant_id
    )

    if not participant:

        session.clear()

        return redirect(
            url_for("login")
        )

    # ---------------------------------------------
    # Check whether participant already submitted
    # ---------------------------------------------

    submitted_attempt = Attempt.query.filter_by(
        participant_id=participant.id,
        status="SUBMITTED"
    ).first()

    if submitted_attempt:

        return render_template(
            "already_submitted.html",
            participant=participant,
            attempt=submitted_attempt
        )

    # ---------------------------------------------
    # Resume existing attempt if present
    # ---------------------------------------------

    attempt = Attempt.query.filter_by(
        participant_id=participant.id,
        status="IN_PROGRESS"
    ).first()

    if attempt:

        question_ids = session.get(
            "question_ids"
        )

        if not question_ids:

            question_ids = [
                answer.question_id
                for answer in attempt.answer_records
            ]

            # If no answer records exist yet,
            # create a fresh question order.
            if not question_ids:

                questions = Question.query.all()

                question_ids = [
                    q.id for q in questions
                ]

                random.shuffle(
                    question_ids
                )

        session["attempt_id"] = attempt.id
        session["question_ids"] = question_ids

        return redirect(
            url_for("quiz")
        )

    # ---------------------------------------------
    # Create new attempt
    # ---------------------------------------------

    questions = Question.query.all()

    if not questions:

        flash(
            "No questions are available yet."
        )

        return redirect(
            url_for("login")
        )

    question_ids = [
        q.id for q in questions
    ]

    # Shuffle question order
    random.shuffle(
        question_ids
    )

    attempt = Attempt(
        participant_id=participant.id,
        started_at=datetime.utcnow(),
        status="IN_PROGRESS",
        score=0,
        total_questions=len(question_ids),
        answers={}
    )

    db.session.add(attempt)

    db.session.commit()

    session["attempt_id"] = attempt.id
    session["question_ids"] = question_ids

    return redirect(
        url_for("quiz")
    )


# =========================================================
# QUIZ
# =========================================================

@app.route(
    "/quiz",
    methods=["GET", "POST"]
)
def quiz():

    participant_id = session.get(
        "participant_id"
    )

    attempt_id = session.get(
        "attempt_id"
    )

    question_ids = session.get(
        "question_ids"
    )

    if not participant_id:

        return redirect(
            url_for("login")
        )

    if not attempt_id or not question_ids:

        return redirect(
            url_for("start")
        )

    participant = db.session.get(
        Participant,
        participant_id
    )

    attempt = db.session.get(
        Attempt,
        attempt_id
    )

    if not participant or not attempt:

        session.clear()

        return redirect(
            url_for("login")
        )

    # ---------------------------------------------
    # Already submitted
    # ---------------------------------------------

    if attempt.status == "SUBMITTED":

        return render_template(
            "already_submitted.html",
            participant=participant,
            attempt=attempt
        )

    # =====================================================
    # SUBMIT EXAM
    # =====================================================

    if request.method == "POST":

        answers = {}

        score = 0

        # ---------------------------------------------
        # Read submitted answers
        # ---------------------------------------------

        for question_id in question_ids:

            selected_answer = request.form.get(
                f"question_{question_id}"
            )

            if selected_answer:

                selected_answer = (
                    selected_answer
                    .strip()
                    .upper()
                )

                if selected_answer not in [
                    "A",
                    "B",
                    "C",
                    "D"
                ]:

                    selected_answer = None

            answers[str(question_id)] = (
                selected_answer
            )

        # ---------------------------------------------
        # Calculate score
        # ---------------------------------------------

        # Delete old answer records if any
        Answer.query.filter_by(
            attempt_id=attempt.id
        ).delete()

        for question_id in question_ids:

            question = db.session.get(
                Question,
                question_id
            )

            if not question:
                continue

            selected_answer = answers.get(
                str(question_id)
            )

            is_correct = (
                selected_answer is not None
                and
                selected_answer
                == question.correct_answer
            )

            if is_correct:
                score += 1

            answer_record = Answer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_answer=selected_answer,
                is_correct=is_correct
            )

            db.session.add(
                answer_record
            )

        # ---------------------------------------------
        # Save final result
        # ---------------------------------------------

        attempt.answers = answers

        attempt.score = score

        attempt.total_questions = len(
            question_ids
        )

        attempt.status = "SUBMITTED"

        attempt.submitted_at = datetime.utcnow()

        db.session.commit()

        # Clear exam session data
        session.pop(
            "attempt_id",
            None
        )

        session.pop(
            "question_ids",
            None
        )

        return redirect(
            url_for("submitted")
        )

    # =====================================================
    # DISPLAY EXAM
    # =====================================================

    questions = []

    for question_id in question_ids:

        question = db.session.get(
            Question,
            question_id
        )

        if question:
            questions.append(
                question
            )

    return render_template(
        "quiz.html",
        participant=participant,
        questions=questions,
        attempt=attempt
    )


# =========================================================
# SUBMITTED PAGE
# =========================================================

@app.route("/submitted")
def submitted():

    participant_id = session.get(
        "participant_id"
    )

    if not participant_id:

        return redirect(
            url_for("login")
        )

    participant = db.session.get(
        Participant,
        participant_id
    )

    attempt = Attempt.query.filter_by(
        participant_id=participant_id,
        status="SUBMITTED"
    ).order_by(
        Attempt.submitted_at.desc()
    ).first()

    if not attempt:

        return redirect(
            url_for("start")
        )

    return render_template(
        "submitted.html",
        participant=participant,
        attempt=attempt
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/admin", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Admin credentials
        ADMIN_USERNAME = "admin"
        ADMIN_PASSWORD = "admin123"

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        flash("Invalid admin username or password.")

    return render_template("admin_login.html")

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        admin_username = os.environ.get(
            "ADMIN_USERNAME",
            "admin"
        )

        admin_password = os.environ.get(
            "ADMIN_PASSWORD",
            "admin123"
        )

        if (
            username == admin_username
            and
            password == admin_password
        ):

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        flash(
            "Invalid admin username or password."
        )

    return render_template(
        "admin_login.html"
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin_login")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for("admin_login")
        )

    participants = Participant.query.order_by(
        Participant.name.asc()
    ).all()

    participant_data = []

    completed_count = 0
    in_progress_count = 0
    not_attempted_count = 0

    for participant in participants:

        # Get most recent attempt
        attempt = Attempt.query.filter_by(
            participant_id=participant.id
        ).order_by(
            Attempt.started_at.desc()
        ).first()

        if not attempt:

            status = "NOT ATTEMPTED"

            score = None

            total_questions = None

            not_attempted_count += 1

        elif attempt.status == "SUBMITTED":

            status = "COMPLETED"

            score = attempt.score

            total_questions = (
                attempt.total_questions
            )

            completed_count += 1

        else:

            status = "IN PROGRESS"

            score = None

            total_questions = (
                attempt.total_questions
            )

            in_progress_count += 1

        participant_data.append({
            "participant": participant,
            "attempt": attempt,
            "status": status,
            "score": score,
            "total_questions": total_questions
        })

    # ---------------------------------------------
    # Ranking
    # ---------------------------------------------

    completed_participants = [
        item
        for item in participant_data
        if item["status"] == "COMPLETED"
    ]

    completed_participants.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    ranking = {}

    current_rank = 0
    previous_score = None

    for index, item in enumerate(
        completed_participants,
        start=1
    ):

        if item["score"] != previous_score:

            current_rank = index

        ranking[
            item["participant"].id
        ] = current_rank

        previous_score = item["score"]

    total_registered = len(
        participants
    )

    return render_template(
        "admin_dashboard.html",
        participant_data=participant_data,
        total_registered=total_registered,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        not_attempted_count=not_attempted_count,
        ranking=ranking
    )


# =========================================================
# ADMIN INDIVIDUAL RESULT
# =========================================================

@app.route(
    "/admin/result/<int:participant_id>"
)
def admin_result(participant_id):

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for("admin_login")
        )

    participant = db.session.get(
        Participant,
        participant_id
    )

    if not participant:

        flash(
            "Participant not found."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    attempt = Attempt.query.filter_by(
        participant_id=participant.id
    ).order_by(
        Attempt.started_at.desc()
    ).first()

    answer_details = []

    if attempt:

        answer_records = Answer.query.filter_by(
            attempt_id=attempt.id
        ).all()

        for answer in answer_records:

            question = db.session.get(
                Question,
                answer.question_id
            )

            if not question:
                continue

            selected_text = ""

            if answer.selected_answer == "A":
                selected_text = question.option_a

            elif answer.selected_answer == "B":
                selected_text = question.option_b

            elif answer.selected_answer == "C":
                selected_text = question.option_c

            elif answer.selected_answer == "D":
                selected_text = question.option_d

            correct_text = ""

            if question.correct_answer == "A":
                correct_text = question.option_a

            elif question.correct_answer == "B":
                correct_text = question.option_b

            elif question.correct_answer == "C":
                correct_text = question.option_c

            elif question.correct_answer == "D":
                correct_text = question.option_d

            answer_details.append({
                "question": question,
                "selected_answer": answer.selected_answer,
                "selected_text": selected_text,
                "correct_answer": question.correct_answer,
                "correct_text": correct_text,
                "is_correct": answer.is_correct
            })

    return render_template(
        "admin_result.html",
        participant=participant,
        attempt=attempt,
        answer_details=answer_details
    )


# =========================================================
# ADMIN RESET ATTEMPT
# =========================================================

@app.route(
    "/admin/reset/<int:participant_id>",
    methods=["POST"]
)
def admin_reset(participant_id):

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for("admin_login")
        )

    participant = db.session.get(
        Participant,
        participant_id
    )

    if not participant:

        flash(
            "Participant not found."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    attempts = Attempt.query.filter_by(
        participant_id=participant.id
    ).all()

    for attempt in attempts:

        db.session.delete(
            attempt
        )

    db.session.commit()

    flash(
        "Exam attempt has been reset."
    )

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return "OK"


# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
