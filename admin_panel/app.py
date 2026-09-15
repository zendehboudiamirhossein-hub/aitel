import functools

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, jsonify
)

import config
import db


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def create_app():
    app = Flask(__name__)
    app.secret_key = config.FLASK_SECRET_KEY
    db.init_db()

    # -------------------------------------------------- auth

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if username == config.ADMIN_USER and password == config.ADMIN_PASS:
                session["logged_in"] = True
                return redirect(url_for("dashboard"))
            flash("نام کاربری یا رمز عبور اشتباه است.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # -------------------------------------------------- pages

    @app.route("/")
    @login_required
    def dashboard():
        stats = db.get_stats()
        recent_users = db.list_users(limit=8)
        recent_logs = db.get_logs(limit=8)
        return render_template("dashboard.html", stats=stats, recent_users=recent_users,
                                recent_logs=recent_logs)

    @app.route("/users")
    @login_required
    def users():
        search = request.args.get("q", "").strip() or None
        user_list = db.list_users(limit=300, search=search)
        return render_template("users.html", users=user_list, search=search or "")

    @app.route("/users/<int:telegram_id>/ban", methods=["POST"])
    @login_required
    def ban_user(telegram_id):
        db.set_ban(telegram_id, True)
        return redirect(url_for("users"))

    @app.route("/users/<int:telegram_id>/unban", methods=["POST"])
    @login_required
    def unban_user(telegram_id):
        db.set_ban(telegram_id, False)
        return redirect(url_for("users"))

    @app.route("/users/<int:telegram_id>/promote", methods=["POST"])
    @login_required
    def promote_user(telegram_id):
        db.set_admin(telegram_id, True)
        return redirect(url_for("users"))

    @app.route("/users/<int:telegram_id>/demote", methods=["POST"])
    @login_required
    def demote_user(telegram_id):
        db.set_admin(telegram_id, False)
        return redirect(url_for("users"))

    @app.route("/broadcast", methods=["GET", "POST"])
    @login_required
    def broadcast():
        if request.method == "POST":
            message = request.form.get("message", "").strip()
            if message:
                db.queue_broadcast(message)
                flash("پیام در صف ارسال قرار گرفت و طی چند ثانیه برای همه کاربران ارسال می‌شود.", "success")
            else:
                flash("متن پیام نمی‌تواند خالی باشد.", "error")
            return redirect(url_for("broadcast"))
        history = db.list_broadcasts(limit=15)
        return render_template("broadcast.html", history=history)

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            model = request.form.get("default_model", "").strip()
            prompt = request.form.get("system_prompt", "").strip()
            if model:
                db.set_setting("default_model", model)
            if prompt:
                db.set_setting("system_prompt", prompt)
            flash("تنظیمات ذخیره شد.", "success")
            return redirect(url_for("settings"))
        current_model = db.get_setting("default_model", config.ANYMODEL_CHAT_MODEL)
        current_prompt = db.get_setting("system_prompt", config.DEFAULT_SYSTEM_PROMPT)
        return render_template(
            "settings.html",
            current_model=current_model,
            current_prompt=current_prompt,
            available_models=config.AVAILABLE_CHAT_MODELS,
        )

    @app.route("/logs")
    @login_required
    def logs():
        log_list = db.get_logs(limit=300)
        return render_template("logs.html", logs=log_list)

    @app.route("/api/stats")
    @login_required
    def api_stats():
        return jsonify(db.get_stats())

    @app.route("/health")
    def health():
        # Railway health-check target; also handy to confirm the web process is alive
        return jsonify({"status": "ok"})

    return app
