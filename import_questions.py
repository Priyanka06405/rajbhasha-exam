import csv

from app import app, db, Question


def import_questions():

    with app.app_context():

        # Remove existing questions
        Question.query.delete()

        db.session.commit()

        # Read CSV file
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

        print(
            f"Successfully imported {count} questions."
        )


if __name__ == "__main__":
    import_questions()
