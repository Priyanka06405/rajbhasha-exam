import csv

from app import app, db, Participant, Question
from werkzeug.security import generate_password_hash


def load_questions():
    """
    Load questions from questions.csv
    """

    Question.query.delete()

    with open(
        "questions.csv",
        "r",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        count = 0

        for row in reader:

            question = Question(
                question_text=row["question"].strip(),
                option_a=row["option_a"].strip(),
                option_b=row["option_b"].strip(),
                option_c=row["option_c"].strip(),
                option_d=row["option_d"].strip(),
                correct_answer=row[
                    "correct_answer"
                ].strip().upper()
            )

            db.session.add(question)

            count += 1

    db.session.commit()

    print(f"Questions loaded: {count}")


def load_participants():
    """
    Load authorized participants from participants.csv
    """

    with open(
        "participants.csv",
        "r",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        count = 0

        for row in reader:

            name = row["name"].strip()

            registration_id = row[
                "registration_id"
            ].strip()

            # Check whether participant already exists
            participant = Participant.query.filter_by(
                registration_id=registration_id
            ).first()

            if participant:
                continue

            # Temporary password
            #
            # We will replace this system before
            # the real examination.
            password = registration_id

            participant = Participant(
                name=name,
                registration_id=registration_id,
                password_hash=generate_password_hash(
                    password
                )
            )

            db.session.add(participant)

            count += 1

    db.session.commit()

    print(f"Participants added: {count}")


def setup_database():

    with app.app_context():

        # Create all database tables
        db.create_all()

        print("Database tables created.")

        # Load questions
        load_questions()

        # Load participants

        load_participants()

        print("")
        print("==============================")
        print("DATABASE SETUP COMPLETE")
        print("==============================")
        print("")
        print(
            f"Participants: "
            f"{Participant.query.count()}"
        )
        print(
            f"Questions: "
            f"{Question.query.count()}"
        )


if __name__ == "__main__":

    setup_database()
