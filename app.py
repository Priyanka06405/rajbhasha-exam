import os
import csv
import random
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rajbhasha-secret-key-change-this')

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///exam.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

EXAM_MINUTES = 30
MARKS_PER_QUESTION = 1

class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    registration_id = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    attempts = db.relationship('Attempt', backref='participant', cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)

class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)
    status = db.Column(db.String(30), default='in_progress')
    score = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer, default=0)
    answers = db.Column(db.JSON, default=dict)
    answer_records = db.relationship('Answer', backref='attempt', cascade='all, delete-orphan')

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('attempt.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    selected_answer = db.Column(db.String(1), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)


def normalize_correct(value):
    value = (value or '').strip().upper()
    return {'क':'A', '(क)':'A', 'ख':'B', '(ख)':'B', 'ग':'C', '(ग)':'C', 'घ':'D', '(घ)':'D'}.get(value, value)


def sync_questions():
    path = os.path.join(os.path.dirname(__file__), 'questions.csv')
    if not os.path.exists(path):
        print('questions.csv not found')
        return
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    existing = Question.query.order_by(Question.id).all()
    # Reload when count differs or question text differs. This also picks up the 6 new MCQs.
    needs_reload = len(existing) != len(rows)
    if not needs_reload:
        for q, row in zip(existing, rows):
            if q.question_text.strip() != (row.get('question') or '').strip():
                needs_reload = True
                break
    if not needs_reload:
        return
    Answer.query.delete()
    Question.query.delete()
    db.session.commit()
    for row in rows:
        db.session.add(Question(
            question_text=(row.get('question') or '').strip(),
            option_a=(row.get('option_a') or '').strip(),
            option_b=(row.get('option_b') or '').strip(),
            option_c=(row.get('option_c') or '').strip(),
            option_d=(row.get('option_d') or '').strip(),
            correct_answer=normalize_correct(row.get('correct_answer')),
        ))
    db.session.commit()
    print(f'Loaded {len(rows)} questions.')


def initialize_database():
    with app.app_context():
        db.create_all()
        sync_questions()


def option_text(question, letter):
    return {
        'A': question.option_a,
        'B': question.option_b,
        'C': question.option_c,
        'D': question.option_d,
    }.get(letter, '')


def get_total_marks(attempt=None):
    return attempt.total_questions if attempt else Question.query.count()


def get_submitted_attempt(participant_id):
    return Attempt.query.filter_by(participant_id=participant_id, status='submitted').order_by(Attempt.id.desc()).first()

@app.route('/')
def home():
    if session.get('participant_id'):
        return redirect(url_for('start_exam'))
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        registration_id = request.form.get('registration_id','').strip()
        password = request.form.get('password','')
        if not name or not registration_id or not password:
            flash('Please fill all fields.')
            return render_template('register.html')
        if Participant.query.filter_by(registration_id=registration_id).first():
            flash('This Personal Number is already registered. Please login.')
            return redirect(url_for('login'))
        db.session.add(Participant(name=name, registration_id=registration_id, password_hash=generate_password_hash(password)))
        db.session.commit()
        flash('Registration successful. Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        registration_id = request.form.get('registration_id','').strip()
        password = request.form.get('password','')
        participant = Participant.query.filter_by(registration_id=registration_id).first()
        if participant and check_password_hash(participant.password_hash, password):
            session.clear()
            session['participant_id'] = participant.id
            return redirect(url_for('start_exam'))
        flash('Invalid Personal Number or password.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/start')
def start_exam():
    pid = session.get('participant_id')
    if not pid:
        return redirect(url_for('login'))
    participant = db.session.get(Participant, pid)
    if not participant:
        session.clear(); return redirect(url_for('login'))
    if get_submitted_attempt(pid):
        return redirect(url_for('already_submitted'))
    attempt = Attempt.query.filter_by(participant_id=pid, status='in_progress').order_by(Attempt.id.desc()).first()
    questions = Question.query.order_by(Question.id).all()
    if not questions:
        flash('No questions are available.')
        return redirect(url_for('login'))
    if not attempt:
        qids = [q.id for q in questions]
        random.shuffle(qids)
        data = {'_question_ids': qids}
        letters = ['A','B','C','D']
        for qid in qids:
            shuffled = letters[:]
            random.shuffle(shuffled)
            data[str(qid)] = {'mapping': dict(zip(letters, shuffled)), 'selected': None}
        attempt = Attempt(participant_id=pid, status='in_progress', total_questions=len(qids), answers=data)
        db.session.add(attempt); db.session.commit()
    session['attempt_id'] = attempt.id
    return redirect(url_for('quiz'))

@app.route('/quiz', methods=['GET','POST'])
def quiz():
    pid = session.get('participant_id')
    aid = session.get('attempt_id')
    if not pid or not aid:
        return redirect(url_for('login'))
    participant = db.session.get(Participant, pid)
    attempt = db.session.get(Attempt, aid)
    if not participant or not attempt or attempt.participant_id != pid:
        return redirect(url_for('start_exam'))
    if attempt.status == 'submitted':
        return redirect(url_for('already_submitted'))

    elapsed = (datetime.utcnow() - attempt.started_at).total_seconds()
    if request.method == 'POST':
        stored = attempt.answers or {}
        qids = stored.get('_question_ids', [])
        score = 0
        Answer.query.filter_by(attempt_id=attempt.id).delete()
        for qid in qids:
            q = db.session.get(Question, int(qid))
            if not q: continue
            selected_display = request.form.get(f'question_{q.id}')
            mapping = stored.get(str(q.id), {}).get('mapping', {})
            original = mapping.get(selected_display) if selected_display else None
            correct = original == q.correct_answer
            if correct: score += 1
            db.session.add(Answer(attempt_id=attempt.id, question_id=q.id, selected_answer=selected_display, is_correct=correct))
        attempt.score = score
        attempt.submitted_at = datetime.utcnow()
        attempt.status = 'submitted'
        db.session.commit()
        return redirect(url_for('submitted'))

    remaining = max(0, EXAM_MINUTES * 60 - int(elapsed))
    if remaining <= 0:
        # Client timer normally submits, but this prevents an expired attempt from being reopened.
        attempt.score = 0
        attempt.status = 'submitted'
        attempt.submitted_at = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('submitted'))

    qids = (attempt.answers or {}).get('_question_ids', [])
    question_data = []
    for qid in qids:
        q = db.session.get(Question, int(qid))
        if not q: continue
        mapping = (attempt.answers or {}).get(str(q.id), {}).get('mapping', {})
        options = [{'letter': d, 'text': option_text(q, orig)} for d, orig in mapping.items()]
        question_data.append({'id': q.id, 'question': q.question_text, 'options': options})
    return render_template('quiz.html', participant=participant, questions=question_data, remaining_seconds=remaining, total_marks=attempt.total_questions)

@app.route('/submitted')
def submitted():
    pid = session.get('participant_id')
    if not pid: return redirect(url_for('login'))
    participant = db.session.get(Participant, pid)
    attempt = get_submitted_attempt(pid)
    if not participant or not attempt: return redirect(url_for('start_exam'))
    return render_template('submitted.html', participant=participant, attempt=attempt, total_marks=get_total_marks(attempt))

@app.route('/already-submitted')
def already_submitted():
    pid = session.get('participant_id')
    if not pid: return redirect(url_for('login'))
    participant = db.session.get(Participant, pid)
    attempt = get_submitted_attempt(pid)
    if not participant: return redirect(url_for('login'))
    return render_template('already_submitted.html', participant=participant, attempt=attempt, total_marks=get_total_marks(attempt) if attempt else Question.query.count())

@app.route('/admin', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username','').strip() == 'admin' and request.form.get('password','') == 'admin123':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin username or password.')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    participants = Participant.query.order_by(Participant.id.asc()).all()
    participant_data=[]; completed=[]; completed_count=0; in_progress_count=0; not_attempted_count=0
    for p in participants:
        a = Attempt.query.filter_by(participant_id=p.id).order_by(Attempt.id.desc()).first()
        if not a:
            status='Not Attempted'; score='-'; not_attempted_count += 1
        elif a.status == 'submitted':
            status='Completed'; score=f'{a.score}/{a.total_questions}'; completed_count += 1
            completed.append((p,a))
        else:
            status='In Progress'; score='-'; in_progress_count += 1
        participant_data.append({'participant':p,'attempt':a,'status':status,'score':score})
    completed.sort(key=lambda x: (-x[1].score, x[1].submitted_at or datetime.max))
    ranking=[{'rank':i,'participant':p,'attempt':a} for i,(p,a) in enumerate(completed,1)]
    return render_template('admin_dashboard.html', participant_data=participant_data, total_registered=len(participants), completed_count=completed_count, in_progress_count=in_progress_count, not_attempted_count=not_attempted_count, ranking=ranking)

@app.route('/admin/result/<int:participant_id>')
def admin_result(participant_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    p=db.session.get(Participant, participant_id)
    if not p: flash('Participant not found.'); return redirect(url_for('admin_dashboard'))
    a=get_submitted_attempt(participant_id)
    if not a: flash('This participant has not submitted the exam.'); return redirect(url_for('admin_dashboard'))
    stored=a.answers or {}; qids=stored.get('_question_ids',[]); details=[]
    for qid in qids:
        q=db.session.get(Question,int(qid))
        if not q: continue
        ans=Answer.query.filter_by(attempt_id=a.id, question_id=q.id).first()
        mapping=stored.get(str(q.id),{}).get('mapping',{})
        selected=ans.selected_answer if ans else None
        original=mapping.get(selected) if selected else None
        correct_display=next((d for d,o in mapping.items() if o==q.correct_answer),'')
        details.append({'question':q,'selected_answer':selected,'selected_text':option_text(q,original) if original else '', 'correct_answer':correct_display,'correct_text':option_text(q,q.correct_answer),'is_correct':bool(ans and ans.is_correct)})
    return render_template('admin_result.html', participant=p, attempt=a, answer_details=details, total_marks=a.total_questions)

@app.route('/admin/reset/<int:participant_id>', methods=['POST','GET'])
def admin_reset(participant_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    p=db.session.get(Participant, participant_id)
    if not p: flash('Participant not found.'); return redirect(url_for('admin_dashboard'))
    for a in Attempt.query.filter_by(participant_id=participant_id).all(): db.session.delete(a)
    db.session.commit()
    flash(f'Exam attempt reset for {p.name}.')
    return redirect(url_for('admin_dashboard'))

initialize_database()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=True)
