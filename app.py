from flask import Flask, render_template, request, redirect, url_for, session, flash
import os, random, sqlite3, smtplib
from werkzeug.utils import secure_filename
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from instagrapi import Client
from instagrapi.exceptions import FeedbackRequired
from moviepy.editor import VideoFileClip
import yt_dlp, requests, facebook as fb
import shutil

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads'
EMAIL_LIST_FOLDER = 'email_lists'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EMAIL_LIST_FOLDER, exist_ok=True)

DATABASE = 'database.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            email_api TEXT,
            ig_id TEXT,
            ig_pass TEXT,
            linkedin_token TEXT,
            linkedin_urn TEXT,
            facebook_token TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    if 'user' in session:
        return render_template('home.html', user=session['user'])
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        data = (
            request.form['name'],
            request.form['email'],
            request.form['password'],
            request.form['email_api'],
            request.form['ig_id'],
            request.form['ig_pass'],
            request.form['linkedin_token'],
            request.form['linkedin_urn'],
            request.form['facebook_token']
        )
        try:
            conn = sqlite3.connect(DATABASE)
            conn.execute('''
                INSERT INTO users
                  (name,email,password,email_api,ig_id,ig_pass,linkedin_token,linkedin_urn,facebook_token)
                VALUES (?,?,?,?,?,?,?,?,?)''', data)
            conn.commit()
            conn.close()
            flash('Registered successfully—please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already registered.', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pw = request.form['password']
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=? AND password=?", (email, pw))
        user = cur.fetchone()
        conn.close()
        if user:
            session['user'] = user
            return redirect(url_for('home'))
        flash('Invalid credentials.', 'danger')
        return render_template('login.html', show_forgot_password=True)
    return render_template('login.html', show_forgot_password=False)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        conn.close()
        if not user:
            flash('Email not found.', 'danger')
        else:
            otp = str(random.randint(100000, 999999))
            session['otp'] = otp
            session['reset_email'] = email
            msg = MIMEText(f'Your OTP is {otp}')
            msg['Subject'] = 'MultiPost Password Reset'
            msg['From'] = user[2]
            msg['To'] = email
            try:
                s = smtplib.SMTP('smtp.gmail.com', 587)
                s.starttls()
                s.login(user[2], user[4])
                s.send_message(msg)
                s.quit()
                flash('OTP sent—check your email.', 'success')
                return redirect(url_for('verify_otp'))
            except:
                flash('Failed to send OTP. Check credentials.', 'danger')
    return render_template('forgot_password.html')

@app.route('/verify_otp', methods=['GET','POST'])
def verify_otp():
    if request.method == 'POST':
        entered = request.form['otp']
        if session.get('otp') == entered:
            session.pop('otp', None)
            flash('OTP verified.', 'success')
            return redirect(url_for('reset_password'))
        flash('Invalid OTP.', 'danger')
    return render_template('verify_otp.html')

@app.route('/reset_password', methods=['GET','POST'])
def reset_password():
    if request.method == 'POST':
        pw1 = request.form['new_password']
        pw2 = request.form['confirm_password']
        if pw1 != pw2:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('reset_password'))
        email = session.pop('reset_email', None)
        if not email:
            flash('Session expired—start again.', 'danger')
            return redirect(url_for('forgot_password'))
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("UPDATE users SET password=? WHERE email=?", (pw1, email))
        conn.commit()
        conn.close()
        flash('Password reset—please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/email_posting', methods=['GET','POST'])
def email_posting():
    if 'user' not in session:
        return redirect(url_for('login'))
    files = [f for f in os.listdir(EMAIL_LIST_FOLDER) if f.endswith('.txt')]
    if request.method == 'POST':
        user = session['user']
        sender, api = user[2], user[4]
        subj = request.form['subject']
        body = request.form['message']
        fname = request.form['email_file']
        atts = request.files.getlist('attachment[]')
        path = os.path.join(EMAIL_LIST_FOLDER, fname)
        with open(path) as f:
            all_emails = [l.strip() for l in f if l.strip()]
        total_count = len(all_emails)
        unique_emails = list(set(all_emails))
        duplicate_count = total_count - len(unique_emails)
        sent_count = 0
        for r in unique_emails:
            try:
                m = MIMEMultipart()
                m['From'], m['To'], m['Subject'] = sender, r, subj
                m.attach(MIMEText(body, 'plain'))
                for a in atts:
                    if a.filename:
                        fn = secure_filename(a.filename)
                        upath = os.path.join(UPLOAD_FOLDER, fn)
                        a.save(upath)
                        with open(upath, 'rb') as fp:
                            p = MIMEApplication(fp.read(), Name=fn)
                            p['Content-Disposition'] = f'attachment; filename="{fn}"'
                            m.attach(p)
                s = smtplib.SMTP('smtp.gmail.com', 587)
                s.starttls()
                s.login(sender, api)
                s.send_message(m)
                s.quit()
                sent_count += 1
            except:
                pass
        # Show messages one by one
        flash(f"✅ Sent: {sent_count}",'info')
        flash(f"✉️ Total Emails: {total_count}",'info')
        flash(f"❗ Duplicates Skipped: {duplicate_count}", 'info')

        # Clean up the upload folder after sending
        for file in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        
        return redirect(url_for('email_posting'))
    return render_template('email_posting.html', email_files=files, user=session['user'])

@app.route('/social_posting', methods=['GET', 'POST'])
def social_posting():
    if 'user' not in session:
        return redirect(url_for('login'))
    result = {}
    if request.method == 'POST':
        u = session['user']
        title, desc = request.form['title'], request.form['description']
        url = request.form['video_url']
        plats = request.form.getlist('platforms')
        vp = os.path.join(UPLOAD_FOLDER, 'video.mp4')
        try:
            with yt_dlp.YoutubeDL({'format': 'best[ext=mp4]', 'outtmpl': vp}) as dl:
                dl.download([url])
            clip = VideoFileClip(vp)
            if clip.duration > 60:
                clip.subclip(0, 60).write_videofile(vp, codec='libx264')
        except:
            result['video'] = 'failed'
        if 'instagram' in plats:
            try:
                cl = Client()
                cl.login(u[5], u[6])
                cl.video_upload(vp, caption=desc)
                result['instagram'] = 'success'
            except FeedbackRequired:
                result['instagram'] = 'success'
            except Exception as e:
                result['instagram'] = str(e)
        if 'linkedin' in plats:
            try:
                req = requests.post(
                    'https://api.linkedin.com/v2/assets?action=registerUpload',
                    headers={'Authorization': f'Bearer {u[7]}', 'Content-Type': 'application/json'},
                    json={
                        'registerUploadRequest': {
                            'recipes': ['urn:li:digitalmediaRecipe:feedshare-video'],
                            'owner': u[8],
                            'serviceRelationships': [{'relationshipType': 'OWNER', 'identifier': 'urn:li:userGeneratedContent'}]
                        }
                    }
                )
                jd = req.json()
                asset = jd['value']['asset']
                upurl = jd['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
                requests.put(upurl, data=open(vp, 'rb'),
                             headers={'Authorization': f'Bearer {u[7]}', 'Content-Type': 'application/octet-stream'})
                payload = {
                    'author': u[8],
                    'lifecycleState': 'PUBLISHED',
                    'specificContent': {'com.linkedin.ugc.ShareContent': {
                        'shareCommentary': {'text': desc},
                        'shareMediaCategory': 'VIDEO',
                        'media': [{'status': 'READY', 'media': asset}]
                    }},
                    'visibility': {'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'}
                }
                post = requests.post('https://api.linkedin.com/v2/ugcPosts',
                                     headers={'Authorization': f'Bearer {u[7]}', 'Content-Type': 'application/json'},
                                     json=payload)
                result['linkedin'] = 'success' if post.status_code == 201 else post.text
            except Exception as e:
                result['linkedin'] = str(e)
        if 'facebook' in plats:
            try:
                graph = fb.GraphAPI(u[9])
                graph.put_object('me', 'feed', message=desc)
                result['facebook'] = 'success'
            except Exception as e:
                result['facebook'] = str(e)
        
        # Clean up the upload folder after posting
        for file in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        
        return render_template('social_posting.html', result=result, user=session['user'])
    return render_template('social_posting.html', result={}, user=session['user'])

if __name__ == '__main__':
    app.run(debug=True)
