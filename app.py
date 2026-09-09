import json
import hmac
import os
import re
import secrets
import tempfile
import time
from datetime import timedelta

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("CODEPUZZLE_SECRET") or secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=30)
app.config.update(
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("CODEPUZZLE_COOKIE_SECURE", "0") == "1",
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LANGUAGES = [
    {"slug": "python", "name": "Python", "file": "python.json", "color": "#f2c94c", "description": "Build a strong foundation with clear, readable code."},
    {"slug": "java", "name": "Java", "file": "java.json", "color": "#ef8354", "description": "Practice structured, object-oriented programming."},
    {"slug": "c", "name": "C", "file": "c.json", "color": "#7aa2f7", "description": "Learn the fundamentals close to the machine."},
    {"slug": "cpp", "name": "C++", "file": "cpp.json", "color": "#c084fc", "description": "Explore powerful systems programming patterns."},
    {"slug": "reactjs", "name": "React JS", "file": "reactjs.json", "color": "#61dafb", "description": "Create modern interfaces with reusable components."},
    {"slug": "rust", "name": "Rust", "file": "rust.json", "color": "#f97316", "description": "Write fast software with fearless memory safety."},
    {"slug": "sql", "name": "SQL", "file": "sql.json", "color": "#38bdf8", "description": "Turn data into useful answers with queries."},
    {"slug": "csharp", "name": "C#", "file": "csharp.json", "color": "#a3e635", "description": "Build versatile applications with a modern language."},
    {"slug": "php", "name": "PHP", "file": "php.json", "color": "#a78bfa", "description": "Learn the language behind countless web applications."},
    {"slug": "golang", "name": "Golang", "file": "golang.json", "color": "#22d3ee", "description": "Keep backend code simple, fast, and concurrent."},
]
LANGUAGE_BY_SLUG = {language["slug"]: language for language in LANGUAGES}
DATASETS = {}
for language in LANGUAGES:
    if language["file"]:
        with open(os.path.join(DATA_DIR, language["file"]), "r", encoding="utf-8") as file:
            dataset = json.load(file)
        DATASETS[language["slug"]] = [puzzle for part in dataset["parts"] for puzzle in part["items"]]

STARTER_PUZZLE = {
    "topic": "Getting started",
    "syntax": "print(\"Hello, CodePuzzle!\")",
    "puzzle": "print(\"Hello, CodePuzzle!\")",
    "output": "Hello, CodePuzzle!",
}
USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")
PLACEHOLDER = re.compile(r"_{2,}")
LOGIN_ATTEMPTS = {}
MAX_USERNAME_LENGTH = 80


def normalize_code(code):
    """Compare code by meaning, ignoring formatting outside quoted strings."""
    normalized = []
    quote = None
    escaped = False
    for character in code.casefold():
        if quote:
            normalized.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
            normalized.append(character)
        elif not character.isspace():
            normalized.append(character)
    return "".join(normalized)


def whole_line_answer_matches(puzzle, answers):
    """Allow pasting a complete missing line into one blank field."""
    non_empty = [str(answer).strip() for answer in answers if str(answer).strip()]
    if len(non_empty) != 1:
        return False

    total_blanks = len(PLACEHOLDER.findall(puzzle["puzzle"]))
    for puzzle_line, syntax_line in zip(
        puzzle["puzzle"].splitlines(), puzzle["syntax"].splitlines()
    ):
        if (
            len(PLACEHOLDER.findall(puzzle_line)) == total_blanks
            and normalize_code(non_empty[0]) == normalize_code(syntax_line)
        ):
            return True
    return False


def user_without_password(user):
    return {key: value for key, value in user.items() if key != "password"}


def save_users(users):
    directory = os.path.dirname(USERS_FILE)
    fd, temporary_file = tempfile.mkstemp(dir=directory, prefix="users-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(users, file, indent=4)
            file.write("\n")
        os.replace(temporary_file, USERS_FILE)
    finally:
        if os.path.exists(temporary_file):
            os.remove(temporary_file)


def load_users():
    with open(USERS_FILE, "r", encoding="utf-8") as file:
        users = json.load(file)
    migrated = False
    for user in users:
        password = user.get("password", "")
        if password and not password.startswith("scrypt:") and not password.startswith("pbkdf2:"):
            user["password"] = generate_password_hash(password)
            migrated = True
    if migrated:
        save_users(users)
    return users


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.context_processor
def inject_security_context():
    return {"csrf_token": csrf_token()}


@app.before_request
def protect_state_changes():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    submitted = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
    expected = session.get("csrf_token")
    if not expected or not submitted or not hmac.compare_digest(submitted, expected):
        if request.path.startswith("/api/"):
            return jsonify({"message": "Invalid security token. Refresh the page and try again."}), 400
        return render_template("login.html", error="Your session expired. Please try again."), 400
    return None


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
    )
    return response


def request_is_rate_limited():
    now = time.monotonic()
    key = request.remote_addr or "unknown"
    attempts = [stamp for stamp in LOGIN_ATTEMPTS.get(key, []) if now - stamp < 300]
    LOGIN_ATTEMPTS[key] = attempts
    return len(attempts) >= 10


def record_login_attempt():
    key = request.remote_addr or "unknown"
    LOGIN_ATTEMPTS.setdefault(key, []).append(time.monotonic())


def current_user():
    username = session.get("username")
    if not username:
        return None
    user = next((user for user in load_users() if user["name"] == username), None)
    return user_without_password(user) if user else None


def require_user():
    user = current_user()
    if user is None:
        return redirect(url_for("login"))
    return user


def puzzles_for(language):
    return DATASETS.get(language) or [STARTER_PUZZLE]


def puzzle_for_level(language, level):
    puzzles = puzzles_for(language)
    puzzle = puzzles[level]
    pieces = []
    last_end = 0

    for match in PLACEHOLDER.finditer(puzzle["puzzle"]):
        if match.start() > last_end:
            pieces.append({"type": "text", "value": puzzle["puzzle"][last_end:match.start()]})
        pieces.append({"type": "input", "value": "", "length": len(match.group())})
        last_end = match.end()

    if last_end < len(puzzle["puzzle"]):
        pieces.append({"type": "text", "value": puzzle["puzzle"][last_end:]})

    lines = [[]]
    for piece in pieces:
        if piece["type"] == "input":
            lines[-1].append(piece)
            continue

        text_parts = piece["value"].split("\n")
        for index, text_part in enumerate(text_parts):
            if text_part:
                lines[-1].append({"type": "text", "value": text_part})
            if index < len(text_parts) - 1:
                lines.append([])

    return {
        "level": level + 1,
        "total": len(puzzles),
        "language": LANGUAGE_BY_SLUG[language],
        "topic": puzzle["topic"],
        "output": puzzle["output"],
        "pieces": pieces,
        "lines": lines,
    }


@app.get("/")
def index():
    user = current_user()
    progress = get_progress(user) if user else {}
    return render_template("home.html", user=user, languages=language_cards(progress))


@app.get("/play/<language>")
def play(language):
    user = require_user()
    if not isinstance(user, dict):
        return user
    if language not in LANGUAGE_BY_SLUG:
        return redirect(url_for("index"))

    level = min(get_progress(user, language)["current_level"], len(puzzles_for(language)) - 1)
    return render_template("game.html", puzzle=puzzle_for_level(language, level), user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if current_user():
            return redirect(url_for("index"))
        return render_template("login.html")

    username = request.form.get("name", "").strip()
    password = request.form.get("password", "")
    if request_is_rate_limited():
        return render_template("login.html", error="Too many login attempts. Try again later."), 429
    if not username or not password or len(username) > MAX_USERNAME_LENGTH or len(password) > 256:
        return render_template("login.html", error="Enter both a username and password."), 400

    record_login_attempt()
    users = load_users()
    user = next((item for item in users if item["name"].casefold() == username.casefold()), None)
    if user and not check_password_hash(user.get("password", ""), password):
        return render_template("login.html", error="That username and password do not match."), 401

    if user is None:
        user = {
            "name": username,
            "password": generate_password_hash(password),
            "current_level": 0,
            "completed_level": 0,
            "skipped_count": 0,
        }
        users.append(user)
        save_users(users)

    session.clear()
    session.permanent = True
    session["username"] = user["name"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/profile")
def profile():
    user = require_user()
    if not isinstance(user, dict):
        return user
    cards = language_cards(get_progress(user))
    completed = sum(item["completed"] for item in cards)
    total = sum(item["total"] for item in cards)
    return render_template(
        "profile.html",
        user=user,
        completed=completed,
        total=total,
        percentage=round(completed / total * 100) if total else 0,
        languages=cards,
    )


def get_progress(user, language=None):
    progress = user.setdefault("progress", {})
    if "python" not in progress:
        progress["python"] = {
            "current_level": user.get("current_level", 0),
            "completed_level": user.get("completed_level", user.get("current_level", 0)),
            "skipped_count": user.get("skipped_count", 0),
        }
    if language:
        return progress.setdefault(language, {"current_level": 0, "completed_level": 0, "skipped_count": 0})
    return progress


def language_cards(progress):
    cards = []
    for language in LANGUAGES:
        item = progress.get(language["slug"], {})
        total = len(puzzles_for(language["slug"]))
        completed = min(item.get("completed_level", 0), total)
        cards.append({**language, "completed": completed, "total": total, "percentage": round(completed / total * 100) if total else 0})
    return cards


@app.post("/api/previous")
def previous_puzzle():
    user = current_user()
    if user is None:
        return jsonify({"message": "Please log in first."}), 401
    language = request.args.get("language", "python")
    if language not in LANGUAGE_BY_SLUG:
        return jsonify({"message": "Unknown language."}), 400
    users = load_users()
    stored_user = next(item for item in users if item["name"] == user["name"])
    progress = get_progress(stored_user, language)
    level = max(progress.get("current_level", 0) - 1, 0)
    progress["current_level"] = level
    save_users(users)
    return jsonify({"puzzle": puzzle_for_level(language, level)})


@app.post("/api/skip")
def skip_puzzle():
    user = current_user()
    if user is None:
        return jsonify({"message": "Please log in first."}), 401

    language = request.args.get("language", "python")
    if language not in LANGUAGE_BY_SLUG:
        return jsonify({"message": "Unknown language."}), 400
    puzzles = puzzles_for(language)
    level = get_progress(user, language).get("current_level", 0)
    if level >= len(puzzles):
        return jsonify({"completed": True, "message": "All puzzles are complete."})

    users = load_users()
    stored_user = next(item for item in users if item["name"] == user["name"])
    progress = get_progress(stored_user, language)
    progress["completed_level"] = progress.get("completed_level", level)
    progress["current_level"] = level + 1
    progress["skipped_count"] = progress.get("skipped_count", 0) + 1
    save_users(users)
    finished = progress["current_level"] >= len(puzzles)
    return jsonify({
        "skipped": True,
        "message": "Puzzle skipped. It does not count toward progress.",
        "completed": finished,
        "next": None if finished else puzzle_for_level(language, progress["current_level"]),
    })


@app.post("/api/answer")
def check_answer():
    user = current_user()
    if user is None:
        return jsonify({"message": "Please log in first."}), 401

    language = request.args.get("language", "python")
    if language not in LANGUAGE_BY_SLUG:
        return jsonify({"message": "Unknown language."}), 400
    puzzles = puzzles_for(language)
    level = get_progress(user, language).get("current_level", 0)
    if level >= len(puzzles):
        return jsonify({"completed": True, "message": "All puzzles are complete."})

    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers", [])
    if not isinstance(answers, list):
        return jsonify({"correct": False, "message": "Enter an answer for every blank."}), 400

    puzzle = puzzles[level]
    answer_index = 0

    def fill_placeholder(match):
        nonlocal answer_index
        answer = str(answers[answer_index]).strip() if answer_index < len(answers) else ""
        answer_index += 1
        return answer

    completed_code = PLACEHOLDER.sub(fill_placeholder, puzzle["puzzle"])
    correct = (
        answer_index == len(answers)
        and normalize_code(completed_code) == normalize_code(puzzle["syntax"])
    )
    if not correct:
        correct = whole_line_answer_matches(puzzle, answers)

    if not correct:
        return jsonify({
            "correct": False,
            "message": "That code does not match the expected syntax yet.",
            "code": completed_code,
        })

    users = load_users()
    stored_user = next(item for item in users if item["name"] == user["name"])
    progress = get_progress(stored_user, language)
    progress["current_level"] = level + 1
    progress["completed_level"] = max(
        progress.get("completed_level", progress.get("current_level", 0)),
        level + 1,
    )
    save_users(users)
    finished = progress["current_level"] >= len(puzzles)
    return jsonify({
        "correct": True,
        "message": "Correct!",
        "output": puzzle["output"],
        "completed": finished,
        "next": None if finished else puzzle_for_level(language, progress["current_level"]),
    })


if __name__ == "__main__":
    app.run(debug=False)