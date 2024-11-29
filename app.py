from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from teams_data import teams_data
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Ensure the instance folder exists
os.makedirs('instance', exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/matches.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    matches = db.relationship('Match', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    home_team = db.Column(db.String(100), nullable=False)
    away_team = db.Column(db.String(100), nullable=False)
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    competition = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Scheduled')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('signup'))

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('signup'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    competitions = sorted(teams_data.keys())
    return render_template('index.html', competitions=competitions, teams_data=teams_data)

@app.route('/matches')
@login_required
def matches():
    status_filter = request.args.get('status', '')
    competition_filter = request.args.get('competition', '')
    search = request.args.get('search', '').lower()
    
    query = Match.query.filter_by(user_id=session['user_id'])
    
    if status_filter:
        query = query.filter(Match.status == status_filter)
    if competition_filter:
        query = query.filter(Match.competition == competition_filter)
    if search:
        query = query.filter(
            db.or_(
                Match.home_team.ilike(f'%{search}%'),
                Match.away_team.ilike(f'%{search}%')
            )
        )
    
    matches = query.order_by(Match.date.desc()).all()
    competitions = sorted(set(match.competition for match in Match.query.filter_by(user_id=session['user_id']).all()))
    
    return render_template('matches.html', 
                         matches=matches, 
                         teams_data=teams_data,
                         competitions=competitions,
                         current_status=status_filter,
                         current_competition=competition_filter,
                         current_search=search)

@app.route('/add_match', methods=['POST'])
@login_required
def add_match():
    try:
        home_team = request.form.get('home_team')
        away_team = request.form.get('away_team')
        competition = request.form.get('competition')
        date_str = request.form.get('date')

        if not all([home_team, away_team, competition, date_str]):
            flash('All fields are required', 'error')
            return redirect(url_for('index'))

        if home_team == away_team:
            flash('Home team and away team cannot be the same', 'error')
            return redirect(url_for('index'))

        if competition in teams_data:
            if home_team not in teams_data[competition]:
                flash(f'{home_team} is not in {competition}', 'error')
                return redirect(url_for('index'))
            if away_team not in teams_data[competition]:
                flash(f'{away_team} is not in {competition}', 'error')
                return redirect(url_for('index'))

        try:
            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format', 'error')
            return redirect(url_for('index'))

        match = Match(
            home_team=home_team,
            away_team=away_team,
            competition=competition,
            date=date,
            user_id=session['user_id']
        )
        db.session.add(match)
        db.session.commit()
        flash('Match added successfully', 'success')
        return redirect(url_for('matches'))
        
    except Exception as e:
        flash(f'Error adding match: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/update_score/<int:match_id>', methods=['POST'])
@login_required
def update_score(match_id):
    try:
        match = Match.query.get_or_404(match_id)
        
        if match.user_id != session['user_id']:
            flash('You do not have permission to update this match', 'error')
            return redirect(url_for('matches'))
        
        try:
            home_score = int(request.form.get('home_score', 0))
            away_score = int(request.form.get('away_score', 0))
        except ValueError:
            flash('Invalid score values', 'error')
            return redirect(url_for('matches'))

        if home_score < 0 or away_score < 0:
            flash('Scores cannot be negative', 'error')
            return redirect(url_for('matches'))

        status = request.form.get('status')
        if status not in ['Scheduled', 'Live', 'Finished']:
            flash('Invalid status', 'error')
            return redirect(url_for('matches'))

        match.home_score = home_score
        match.away_score = away_score
        match.status = status
        db.session.commit()
        flash('Match updated successfully', 'success')
        return redirect(url_for('matches'))
        
    except Exception as e:
        flash(f'Error updating match: {str(e)}', 'error')
        return redirect(url_for('matches'))

@app.route('/delete_match/<int:match_id>', methods=['POST'])
@login_required
def delete_match(match_id):
    try:
        match = Match.query.get_or_404(match_id)
        
        if match.user_id != session['user_id']:
            flash('You do not have permission to delete this match', 'error')
            return redirect(url_for('matches'))
        
        db.session.delete(match)
        db.session.commit()
        flash('Match deleted successfully', 'success')
        return redirect(url_for('matches'))
        
    except Exception as e:
        flash(f'Error deleting match: {str(e)}', 'error')
        return redirect(url_for('matches'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=10000)
