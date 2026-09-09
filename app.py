import os
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


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-before-production"
)

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------
# On Render we will use PostgreSQL through DATABASE_URL.
# For testing, SQLite can be used as a fallback.
# ------------------------------------------------------------

database_url = os.environ.get("DATABASE_URL")

if database_url:
    # Render may provide postgres:// instead of postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url

else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///exam.db"


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ============================================================
# DATABASE MODELS
# ============================================================

class Participant(db.Model):
    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False)

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

    # Relationship with attempts
    attempts = db.relationship(
        "Attempt",
        backref="participant",
        lazy=True
    )


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)

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

    # Stores A, B, C or D
    correct_answer = db.Column(
        db.String(1),
        nullable=False
    )


class Attempt(db.Model):
    __tablename__ = "attempts"

    id = db.Column(db.Integer, primary_key=True)

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
        nullable=True
    )

    total_questions = db.Column(
        db.Integer,
        default=60
    )

    answers = db.relationship(
        "Answer",
        backref="attempt",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Answer(db.Model):
    __tablename__ = "answers"

    id = db.Column(db.Integer, primary_key=True)

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

    # Stores the displayed option letter
    selected_answer = db.Column(
        db.String(1),
        nullable=True
    )

    is_correct = db.Column(
        db.Boolean,
        default=False
    )


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

with app.app_context():
    db.create_all()


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():
    return redirect(url_for("register"))


# ============================================================
# PARTICIPANT REGISTRATION
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        registration_id = request.form.get(
            "registration_id",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # Basic validation
        if not name or not registration_id or not password:
            flash(
                "Please fill in all the fields.",
                "error"
            )
            return redirect(url_for("register"))

        # Check duplicate registration ID
        existing = Participant.query.filter_by(
            registration_id=registration_id
        ).first()

        if existing:
            flash(
                "This Registration ID is already registered.",
                "error"
            )
            return redirect(url_for("register"))

        # Create participant
        participant = Participant(
            name=name,
            registration_id=registration_id,
            password_hash=generate_password_hash(password)
        )

        db.session.add(participant)
        db.session.commit()

        flash(
            "Registration successful. You can now log in.",
            "success"
        )

        return redirect(url_for("login"))

    return render_template("register.html")


# ============================================================
# PARTICIPANT LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
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

        if participant and check_password_hash(
            participant.password_hash,
            password
        ):

            session["participant_id"] = participant.id

            return redirect(url_for("start_exam"))

        flash(
            "Invalid Registration ID or password.",
            "error"
        )

    return render_template("login.html")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.pop("participant_id", None)

    return redirect(url_for("login"))


# ============================================================
# START EXAM
# ============================================================

@app.route("/start")
def start_exam():

    participant_id = session.get("participant_id")

    if not participant_id:
        return redirect(url_for("login"))

    participant = db.session.get(
        Participant,
        participant_id
    )

    if not participant:
        session.pop("participant_id", None)
        return redirect(url_for("login"))

    # Check whether participant already has an attempt
    attempt = Attempt.query.filter_by(
        participant_id=participant.id
    ).first()

    if attempt:

        if attempt.status == "SUBMITTED":
            return redirect(url_for("already_submitted"))

        session["attempt_id"] = attempt.id

        return redirect(url_for("quiz"))

    # Create a new attempt
    questions_count = Question.query.count()

    attempt = Attempt(
        participant_id=participant.id,
        status="IN_PROGRESS",
        total_questions=questions_count
    )

    db.session.add(attempt)
    db.session.commit()

    session["attempt_id"] = attempt.id

    # Randomize question order
    question_ids = [
        q.id for q in Question.query.all()
    ]

    random.shuffle(question_ids)

    session["question_order"] = question_ids

    return redirect(url_for("quiz"))


# ============================================================
# QUIZ
# ============================================================

@app.route("/quiz", methods=["GET", "POST"])
def quiz():

    participant_id = session.get("participant_id")
    attempt_id = session.get("attempt_id")

    if not participant_id or not attempt_id:
        return redirect(url_for("login"))

    attempt = db.session.get(
        Attempt,
        attempt_id
    )

    if not attempt:
        return redirect(url_for("login"))

    if attempt.status == "SUBMITTED":
        return redirect(url_for("already_submitted"))

    # --------------------------------------------------------
    # Get question order
    # --------------------------------------------------------

    question_order = session.get("question_order")

    if not question_order:

        question_order = [
            q.id for q in Question.query.all()
        ]

        random.shuffle(question_order)

        session["question_order"] = question_order

    # --------------------------------------------------------
    # Save answers
    # --------------------------------------------------------

    if request.method == "POST":

        for question_id in question_order:

            selected = request.form.get(
                f"question_{question_id}"
            )

            if selected:

                answer = Answer.query.filter_by(
                    attempt_id=attempt.id,
                    question_id=question_id
                ).first()

                if not answer:

                    answer = Answer(
                        attempt_id=attempt.id,
                        question_id=question_id
                    )

                    db.session.add(answer)

                answer.selected_answer = selected

        db.session.commit()

        # Final submission
        if request.form.get("submit_test") == "yes":

            score = 0

            answers = Answer.query.filter_by(
                attempt_id=attempt.id
            ).all()

            for answer in answers:

                question = db.session.get(
                    Question,
                    answer.question_id
                )

                if question:

                    if answer.selected_answer == question.correct_answer:

                        answer.is_correct = True
                        score += 1

                    else:

                        answer.is_correct = False

            attempt.score = score
            attempt.status = "SUBMITTED"
            attempt.submitted_at = datetime.utcnow()

            db.session.commit()

            session.pop("question_order", None)

            return redirect(
                url_for(
                    "submitted",
                    score=score,
                    total=len(question_order)
                )
            )

    # --------------------------------------------------------
    # Prepare questions
    # --------------------------------------------------------

    questions = []

    for question_id in question_order:

        question = db.session.get(
            Question,
            question_id
        )

        if question:
            questions.append(question)

    return render_template(
        "quiz.html",
        questions=questions,
        participant=attempt.participant
    )


# ============================================================
# SUBMITTED PAGE
# ============================================================

@app.route("/submitted")
def submitted():

    participant_id = session.get("participant_id")

    if not participant_id:
        return redirect(url_for("login"))

    participant = db.session.get(
        Participant,
        participant_id
    )

    attempt = Attempt.query.filter_by(
        participant_id=participant_id
    ).first()

    if not attempt:
        return redirect(url_for("login"))

    return render_template(
        "submitted.html",
        participant=participant,
        attempt=attempt
    )


# ============================================================
# ALREADY SUBMITTED
# ============================================================

@app.route("/already-submitted")
def already_submitted():

    return render_template(
        "already_submitted.html"
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route("/admin", methods=["GET", "POST"])
def admin_login():

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
            and password == admin_password
        ):

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        flash(
            "Invalid admin username or password.",
            "error"
        )

    return render_template(
        "admin_login.html"
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin_logged_in", None)

    return redirect(url_for("admin_login"))


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    participants = Participant.query.order_by(
        Participant.registered_at.asc()
    ).all()

    attempts = Attempt.query.all()

    attempt_by_participant = {
        attempt.participant_id: attempt
        for attempt in attempts
    }

    completed = 0
    in_progress = 0
    not_attempted = 0

    for participant in participants:

        attempt = attempt_by_participant.get(
            participant.id
        )

        if not attempt:
            not_attempted += 1

        elif attempt.status == "SUBMITTED":
            completed += 1

        else:
            in_progress += 1

    # Results sorted by score
    completed_attempts = Attempt.query.filter_by(
        status="SUBMITTED"
    ).order_by(
        Attempt.score.desc()
    ).all()

    return render_template(
        "admin_dashboard.html",
        participants=participants,
        attempt_by_participant=attempt_by_participant,
        completed=completed,
        in_progress=in_progress,
        not_attempted=not_attempted,
        total=len(participants),
        completed_attempts=completed_attempts
    )


# ============================================================
# ADMIN VIEW INDIVIDUAL RESULT
# ============================================================

@app.route("/admin/result/<int:participant_id>")
def admin_result(participant_id):

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    participant = db.session.get(
        Participant,
        participant_id
    )

    if not participant:
        return "Participant not found", 404

    attempt = Attempt.query.filter_by(
        participant_id=participant.id
    ).first()

    answers = []

    if attempt:

        answers = Answer.query.filter_by(
            attempt_id=attempt.id
        ).all()

    return render_template(
        "admin_result.html",
        participant=participant,
        attempt=attempt,
        answers=answers
    )


# ============================================================
# ADMIN: DELETE/RESET ATTEMPT
# ============================================================

@app.route(
    "/admin/reset/<int:participant_id>",
    methods=["POST"]
)
def admin_reset(participant_id):

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    participant = db.session.get(
        Participant,
        participant_id
    )

    if not participant:
        return "Participant not found", 404

    attempt = Attempt.query.filter_by(
        participant_id=participant.id
    ).first()

    if attempt:

        db.session.delete(attempt)
        db.session.commit()

    flash(
        "Participant attempt has been reset.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
