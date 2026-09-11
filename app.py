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

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "rajbhasha-secret-key-change-later"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Render/PostgreSQL sometimes gives postgres://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///exam.db"


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================================================
# DATABASE MODELS
# =========================================================

class Participant(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), nullable=False)

    # This is the Personal Number shown to the participant
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
        cascade="all, delete-orphan"
    )


class Question(db.Model):

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

    # Stores A / B / C / D
    correct_answer = db.Column(
        db.String(1),
        nullable=False
    )


class Attempt(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    participant_id = db.Column(
        db.Integer,
        db.ForeignKey("participant.id"),
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
        default="in_progress"
    )

    score = db.Column(
        db.Integer,
        default=0
    )

    total_questions = db.Column(
        db.Integer,
        default=0
    )

    # Stores question order and answer-position mapping
    answers = db.Column(
        db.JSON,
        default=dict
    )

    answer_records = db.relationship(
        "Answer",
        backref="attempt",
        cascade="all, delete-orphan"
    )


class Answer(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    attempt_id = db.Column(
        db.Integer,
        db.ForeignKey("attempt.id"),
        nullable=False
    )

    question_id = db.Column(
        db.Integer,
        db.ForeignKey("question.id"),
        nullable=False
    )

    # IMPORTANT:
    # This stores the DISPLAYED answer letter
    # that the participant actually clicked.
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

def sync_questions():

    csv_file = "questions.csv"

    if not os.path.exists(csv_file):
        print("questions.csv not found.")
        return

    try:

        with open(
            csv_file,
            "r",
            encoding="utf-8-sig"
        ) as file:

            reader = csv.DictReader(file)

            rows = list(reader)

        if not rows:
            print("questions.csv is empty.")
            return

        # -------------------------------------------------
        # If the number of questions is different,
        # reload all questions.
        # -------------------------------------------------

        database_count = Question.query.count()

        if database_count == len(rows):
            print(
                f"Question database already contains "
                f"{database_count} questions."
            )
            return

        print(
            f"Loading {len(rows)} questions from CSV..."
        )

        Question.query.delete()

        for row in rows:

            question_text = (
                row.get("question")
                or row.get("Question")
                or row.get("question_text")
                or ""
            ).strip()

            option_a = (
                row.get("option_a")
                or row.get("A")
                or row.get("(A)")
                or ""
            ).strip()

            option_b = (
                row.get("option_b")
                or row.get("B")
                or row.get("(B)")
                or ""
            ).strip()

            option_c = (
                row.get("option_c")
                or row.get("C")
                or row.get("(C)")
                or ""
            ).strip()

            option_d = (
                row.get("option_d")
                or row.get("D")
                or row.get("(D)")
                or ""
            ).strip()

            correct_answer = (
                row.get("correct_answer")
                or row.get("answer")
                or row.get("correct")
                or ""
            ).strip().upper()

            # Handle forms such as:
            # (A), A, (क), क
            if correct_answer in ["क", "(क)"]:
                correct_answer = "A"

            elif correct_answer in ["ख", "(ख)"]:
                correct_answer = "B"

            elif correct_answer in ["ग", "(ग)"]:
                correct_answer = "C"

            elif correct_answer in ["घ", "(घ)"]:
                correct_answer = "D"

            question = Question(
                question_text=question_text,
                option_a=option_a,
                option_b=option_b,
                option_c=option_c,
                option_d=option_d,
                correct_answer=correct_answer
            )

            db.session.add(question)

        db.session.commit()

        print(
            f"Successfully loaded {len(rows)} questions."
        )

    except Exception as e:

        db.session.rollback()

        print(
            "Error loading questions:",
            e
        )


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def initialize_database():

    with app.app_context():

        db.create_all()

        sync_questions()


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    if session.get("participant_id"):
        return redirect(url_for("start_exam"))

    return redirect(url_for("login"))


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

        if not name or not registration_id or not password:

            flash(
                "Please fill all fields."
            )

            return redirect(
                url_for("register")
            )

        existing = Participant.query.filter_by(
            registration_id=registration_id
        ).first()

        if existing:

            flash(
                "This Personal Number is already registered. Please login."
            )

            return redirect(
                url_for("login")
            )

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
            "Registration successful. Please login."
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

        if (
            participant
            and check_password_hash(
                participant.password_hash,
                password
            )
        ):

            session.clear()

            session["participant_id"] = participant.id

            return redirect(
                url_for("start_exam")
            )

        flash(
            "Invalid Personal Number or password."
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

    return redirect(
        url_for("login")
    )


# =========================================================
# START EXAM
# =========================================================

@app.route("/start")
def start_exam():

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

    # -----------------------------------------------------
    # Check whether participant already submitted
    # -----------------------------------------------------

    submitted_attempt = Attempt.query.filter_by(
        participant_id=participant.id,
        status="submitted"
    ).first()

    if submitted_attempt:

        return redirect(
            url_for(
                "already_submitted"
            )
        )

    # -----------------------------------------------------
    # Find an existing in-progress attempt
    # -----------------------------------------------------

    attempt = Attempt.query.filter_by(
        participant_id=participant.id,
        status="in_progress"
    ).first()

    questions = Question.query.all()

    if not questions:

        flash(
            "No questions are available."
        )

        return redirect(
            url_for("login")
        )

    # =====================================================
    # EXISTING ATTEMPT
    # =====================================================

    if attempt:

        stored_answers = attempt.answers or {}

        # Get stored question order
        question_ids = stored_answers.get(
            "_question_ids"
        )

        if not question_ids:

            question_ids = [
                q.id for q in questions
            ]

            random.shuffle(
                question_ids
            )

            stored_answers["_question_ids"] = (
                question_ids
            )

            attempt.answers = stored_answers

            db.session.commit()

    # =====================================================
    # NEW ATTEMPT
    # =====================================================

    else:

        question_ids = [
            q.id for q in questions
        ]

        # Random question order
        random.shuffle(
            question_ids
        )

        answers_data = {}

        answers_data["_question_ids"] = (
            question_ids
        )

        # -------------------------------------------------
        # Create a RANDOM mapping for every question.
        #
        # Example:
        #
        # Display A -> original C
        # Display B -> original A
        # Display C -> original D
        # Display D -> original B
        #
        # This mapping is saved permanently for this attempt.
        # -------------------------------------------------

        original_letters = [
            "A",
            "B",
            "C",
            "D"
        ]

        for question_id in question_ids:

            shuffled_letters = (
                original_letters.copy()
            )

            random.shuffle(
                shuffled_letters
            )

            mapping = {
                "A": shuffled_letters[0],
                "B": shuffled_letters[1],
                "C": shuffled_letters[2],
                "D": shuffled_letters[3]
            }

            answers_data[
                str(question_id)
            ] = {
                "mapping": mapping,
                "selected": None,
                "original": None
            }

        attempt = Attempt(
            participant_id=participant.id,
            status="in_progress",
            total_questions=len(
                question_ids
            ),
            answers=answers_data
        )

        db.session.add(attempt)

        db.session.commit()

    # Store attempt ID in session
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

    if not participant_id:

        return redirect(
            url_for("login")
        )

    if not attempt_id:

        return redirect(
            url_for("start_exam")
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

    # -----------------------------------------------------
    # Do not allow already submitted attempt
    # -----------------------------------------------------

    if attempt.status == "submitted":

        return redirect(
            url_for(
                "already_submitted"
            )
        )

    stored_answers = attempt.answers or {}

    question_ids = stored_answers.get(
        "_question_ids"
    )

    if not question_ids:

        return redirect(
            url_for("start_exam")
        )

    # =====================================================
    # SUBMIT EXAM
    # =====================================================

    if request.method == "POST":

        score = 0

        # Remove any previous answer records
        Answer.query.filter_by(
            attempt_id=attempt.id
        ).delete()

        for question_id in question_ids:

            question = db.session.get(
                Question,
                int(question_id)
            )

            if not question:
                continue

            question_data = stored_answers.get(
                str(question_id),
                {}
            )

            mapping = question_data.get(
                "mapping",
                {}
            )

            # -------------------------------------------------
            # This is the letter the participant ACTUALLY saw
            # and clicked.
            # -------------------------------------------------

            selected_display = request.form.get(
                f"question_{question_id}"
            )

            original_answer = None

            if selected_display:

                original_answer = mapping.get(
                    selected_display
                )

            is_correct = (
                original_answer
                == question.correct_answer
            )

            if is_correct:
                score += 1

            # Save displayed answer and original answer
            question_data["selected"] = (
                selected_display
            )

            question_data["original"] = (
                original_answer
            )

            stored_answers[
                str(question_id)
            ] = question_data

            answer_record = Answer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_answer=selected_display,
                is_correct=is_correct
            )

            db.session.add(
                answer_record
            )

        # -----------------------------------------------------
        # Mark attempt as submitted
        # -----------------------------------------------------

        attempt.answers = stored_answers

        attempt.score = score

        attempt.total_questions = len(
            question_ids
        )

        attempt.status = "submitted"

        attempt.submitted_at = (
            datetime.utcnow()
        )

        db.session.commit()

        return redirect(
            url_for("submitted")
        )

    # =====================================================
    # DISPLAY QUIZ
    # =====================================================

    question_data = []

    for question_id in question_ids:

        question = db.session.get(
            Question,
            int(question_id)
        )

        if not question:
            continue

        question_info = stored_answers.get(
            str(question.id),
            {}
        )

        mapping = question_info.get(
            "mapping"
        )

        # -------------------------------------------------
        # Safety fallback
        # -------------------------------------------------

        if not mapping:

            original_letters = [
                "A",
                "B",
                "C",
                "D"
            ]

            shuffled_letters = (
                original_letters.copy()
            )

            random.shuffle(
                shuffled_letters
            )

            mapping = {
                "A": shuffled_letters[0],
                "B": shuffled_letters[1],
                "C": shuffled_letters[2],
                "D": shuffled_letters[3]
            }

            question_info["mapping"] = (
                mapping
            )

            stored_answers[
                str(question.id)
            ] = question_info

        original_options = {

            "A": question.option_a,

            "B": question.option_b,

            "C": question.option_c,

            "D": question.option_d
        }

        display_options = []

        for display_letter in [
            "A",
            "B",
            "C",
            "D"
        ]:

            original_letter = mapping.get(
                display_letter
            )

            option_text = original_options.get(
                original_letter,
                ""
            )

            display_options.append({

                "letter": display_letter,

                "text": option_text
            })

        question_data.append({

            "id": question.id,

            "question": question.question_text,

            "options": display_options

        })

    # Save any fallback mappings
    attempt.answers = stored_answers

    db.session.commit()

    return render_template(
        "quiz.html",
        participant=participant,
        questions=question_data
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
        status="submitted"
    ).order_by(
        Attempt.id.desc()
    ).first()

    if not attempt:

        return redirect(
            url_for("start_exam")
        )

    return render_template(
        "submitted.html",
        participant=participant,
        attempt=attempt
    )


# =========================================================
# ALREADY SUBMITTED
# =========================================================

@app.route("/already-submitted")
def already_submitted():

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
        status="submitted"
    ).order_by(
        Attempt.id.desc()
    ).first()

    return render_template(
        "already_submitted.html",
        participant=participant,
        attempt=attempt
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
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

        # -------------------------------------------------
        # Current admin credentials
        # -------------------------------------------------

        ADMIN_USERNAME = "admin"

        ADMIN_PASSWORD = "admin123"

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session["admin_logged_in"] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
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
        Participant.id.asc()
    ).all()

    participant_data = []

    completed_count = 0

    in_progress_count = 0

    not_attempted_count = 0

    for participant in participants:

        attempt = Attempt.query.filter_by(
            participant_id=participant.id
        ).order_by(
            Attempt.id.desc()
        ).first()

        if not attempt:

            status = "Not Attempted"

            score_display = "-"

            not_attempted_count += 1

        elif attempt.status == "submitted":

            status = "Completed"

            score_display = (
                f"{attempt.score}/"
                f"{attempt.total_questions}"
            )

            completed_count += 1

        else:

            status = "In Progress"

            score_display = "-"

            in_progress_count += 1

        participant_data.append({

            "participant": participant,

            "attempt": attempt,

            "status": status,

            "score": score_display

        })

    # -----------------------------------------------------
    # Ranking
    # -----------------------------------------------------

    completed_attempts = []

    for participant in participants:

        attempt = Attempt.query.filter_by(
            participant_id=participant.id,
            status="submitted"
        ).order_by(
            Attempt.score.desc(),
            Attempt.submitted_at.asc()
        ).first()

        if attempt:

            completed_attempts.append({

                "participant": participant,

                "attempt": attempt

            })

    completed_attempts.sort(
        key=lambda x: (
            -x["attempt"].score,
            x["attempt"].submitted_at
            or datetime.max
        )
    )

    ranking = []

    for index, item in enumerate(
        completed_attempts,
        start=1
    ):

        ranking.append({

            "rank": index,

            "participant": item["participant"],

            "attempt": item["attempt"]

        })

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
# ADMIN RESULT
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
        participant_id=participant.id,
        status="submitted"
    ).order_by(
        Attempt.id.desc()
    ).first()

    if not attempt:

        flash(
            "This participant has not submitted the exam."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    stored_answers = attempt.answers or {}

    answer_details = []

    # -----------------------------------------------------
    # Use the original stored question order
    # -----------------------------------------------------

    question_ids = stored_answers.get(
        "_question_ids",
        []
    )

    for question_id in question_ids:

        question = db.session.get(
            Question,
            int(question_id)
        )

        if not question:
            continue

        answer = Answer.query.filter_by(
            attempt_id=attempt.id,
            question_id=question.id
        ).first()

        if not answer:
            continue

        question_data = stored_answers.get(
            str(question.id),
            {}
        )

        mapping = question_data.get(
            "mapping",
            {}
        )

        # -------------------------------------------------
        # Participant's displayed selection
        # -------------------------------------------------

        selected_display = (
            answer.selected_answer
        )

        selected_text = ""

        if selected_display:

            original_selected = mapping.get(
                selected_display
            )

            if original_selected == "A":

                selected_text = (
                    question.option_a
                )

            elif original_selected == "B":

                selected_text = (
                    question.option_b
                )

            elif original_selected == "C":

                selected_text = (
                    question.option_c
                )

            elif original_selected == "D":

                selected_text = (
                    question.option_d
                )

        # -------------------------------------------------
        # Correct answer in DISPLAYED position
        # -------------------------------------------------

        correct_display = ""

        for display_letter, original_letter in mapping.items():

            if (
                original_letter
                == question.correct_answer
            ):

                correct_display = (
                    display_letter
                )

                break

        # -------------------------------------------------
        # Correct answer text
        # -------------------------------------------------

        if question.correct_answer == "A":

            correct_text = (
                question.option_a
            )

        elif question.correct_answer == "B":

            correct_text = (
                question.option_b
            )

        elif question.correct_answer == "C":

            correct_text = (
                question.option_c
            )

        else:

            correct_text = (
                question.option_d
            )

        answer_details.append({

            "question": question,

            "selected_answer": selected_display,

            "selected_text": selected_text,

            "correct_answer": correct_display,

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
# ADMIN RESET PARTICIPANT
# =========================================================

@app.route(
    "/admin/reset/<int:participant_id>",
    methods=["POST", "GET"]
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

    # Delete all attempts.
    # This also deletes answer records because
    # of the cascade relationship.

    Attempt.query.filter_by(
        participant_id=participant.id
    ).delete(
        synchronize_session=False
    )

    db.session.commit()

    flash(
        f"Exam attempt reset for {participant.name}."
    )

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# RUN APPLICATION
# =========================================================

initialize_database()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=True
    )
