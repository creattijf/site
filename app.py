import os
import sqlite3
import re
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from datetime import datetime, timedelta, time

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = '8330079994:AAFYWuhvIPi_6aFb1JamPfO99RKfMsOhNc4'
TELEGRAM_CHAT_ID = '-4910910068'
ADMIN_PASSWORD = '123456' 
SECRET_URL_PART = "lord-dashboard-secret-777"
ABUSE_COOLDOWN_HOURS = 2

app = Flask(__name__)
app.secret_key = 'fdkfu' 

# --- Вспомогательные функции ---

def escape_markdown(text: str) -> str:
    """Экранирует все специальные символы для MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-.=|{}!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def send_telegram_notification(message_text: str):
    """Отправляет уведомление с надежной обработкой ошибок."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message_text, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        print("Уведомление в Telegram успешно отправлено.")
    except requests.exceptions.RequestException as e:
        print(f"!!! ОШИБКА отправки Telegram: {e}")
        if e.response is not None:
            print(f"!!! Ответ от API: {e.response.text}")

def get_db_connection():
    conn = sqlite3.connect('bookings.db'); conn.row_factory = sqlite3.Row; return conn

def init_db():
    conn = get_db_connection()
    # === ВОЗВРАЩАЕМ client_id В СТРУКТУРУ БАЗЫ ===
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY,
            booking_datetime TEXT NOT NULL UNIQUE,
            client_name TEXT NOT NULL,
            client_phone TEXT NOT NULL,
            service_name TEXT NOT NULL,
            client_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_client_id ON bookings(client_id)')
    conn.execute('CREATE TABLE IF NOT EXISTS user_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_address TEXT NOT NULL, action_type TEXT NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.execute('CREATE TABLE IF NOT EXISTS ip_cooldown (ip_address TEXT PRIMARY KEY, cooldown_until TIMESTAMP NOT NULL)')
    conn.commit()
    conn.close()

def log_user_action(conn, ip, action_type):
    conn.execute('INSERT INTO user_actions (ip_address, action_type) VALUES (?, ?)', (ip, action_type))

def check_abuse_cooldown(conn, ip):
    cooldown = conn.execute('SELECT cooldown_until FROM ip_cooldown WHERE ip_address = ?', (ip,)).fetchone()
    if cooldown and datetime.now() < datetime.fromisoformat(cooldown['cooldown_until']):
        return True
    return False

def check_and_apply_abuse_rule(conn, ip):
    actions = [row['action_type'] for row in conn.execute('SELECT action_type FROM user_actions WHERE ip_address = ? ORDER BY timestamp DESC LIMIT 4', (ip,)).fetchall()]
    if actions == ['cancel', 'book', 'cancel', 'book']:
        cooldown_until = datetime.now() + timedelta(hours=ABUSE_COOLDOWN_HOURS)
        conn.execute('INSERT OR REPLACE INTO ip_cooldown (ip_address, cooldown_until) VALUES (?, ?)', (ip, cooldown_until.isoformat()))
        print(f"IP {ip} заблокирован до {cooldown_until.isoformat()} за подозрительную активность.")

def generate_time_slots():
    conn = get_db_connection()
    booked_slots = {row['booking_datetime'] for row in conn.execute('SELECT booking_datetime FROM bookings').fetchall()}
    conn.close()

    available_slots = {}
    today = (datetime.utcnow() + timedelta(hours=3)).date()  # МСК
    for i in range(2):
        day = today + timedelta(days=i)
        day_str = day.strftime("%A, %d %B")
        slots_for_day = []
        current_slot_dt = datetime.combine(day, time(10, 0))
        while current_slot_dt.time() < time(22, 0):
            slot_iso = current_slot_dt.isoformat()
            now = datetime.utcnow() + timedelta(hours=3)  # текущее время по МСК
            status = 'available'
            if current_slot_dt < now:
                status = 'past'
            elif slot_iso in booked_slots:
                status = 'taken'
            slots_for_day.append({
                'time': current_slot_dt.strftime("%H:%M"),
                'datetime_iso': slot_iso,
                'status': status
            })
            current_slot_dt += timedelta(minutes=30)
        available_slots[day_str] = slots_for_day
    return available_slots


# --- ОБЫЧНЫЕ МАРШРУТЫ ---

@app.route('/')
def index():
    services_list = [{"name": "Королевское бритье", "price": "2000₽"}, {"name": "Мужская стрижка", "price": "1500₽"}, {"name": "Стрижка + Борода", "price": "2500₽"}]
    return render_template('index.html', services=services_list, available_slots=generate_time_slots(), ABUSE_COOLDOWN_HOURS=ABUSE_COOLDOWN_HOURS)

@app.route('/book', methods=['POST'])
def handle_booking():
    conn = get_db_connection()
    ip = request.remote_addr
    try:
        if check_abuse_cooldown(conn, ip):
            return jsonify({'message': f'Вы были временно заблокированы на {ABUSE_COOLDOWN_HOURS} часа.'}), 429

        data = request.get_json()
        phone = data.get('phone', '').strip(); name = data.get('name', '').strip(); service = data.get('service', '').strip(); booking_dt = data.get('booking_datetime', '').strip()
        client_id = data.get('client_id', '').strip()

        if not all([phone, name, service, booking_dt, client_id]):
            return jsonify({'message': 'Все поля должны быть заполнены.'}), 400

        now_iso = datetime.now().isoformat()
        existing_by_id = conn.execute('SELECT * FROM bookings WHERE client_id = ? AND booking_datetime > ?', (client_id, now_iso)).fetchone()
        if existing_by_id:
            return jsonify({'message': f"С этого устройства уже есть запись на имя {existing_by_id['client_name']}."}), 409

        if conn.execute('SELECT id FROM bookings WHERE booking_datetime = ?', (booking_dt,)).fetchone():
            return jsonify({'message': 'Это время уже занято.'}), 409

        conn.execute('INSERT INTO bookings (booking_datetime, client_name, client_phone, service_name, client_id) VALUES (?, ?, ?, ?, ?)',(booking_dt, name, phone, service, client_id))
        log_user_action(conn, ip, 'book')
        check_and_apply_abuse_rule(conn, ip)
        conn.commit()

        dt_str = datetime.fromisoformat(booking_dt).strftime("%d %B at %H:%M")
        msg = f"✅ *New Booking\\!*\n\n👤 *Name:* {escape_markdown(name)}\n📞 *Phone:* `{escape_markdown(phone)}`\n🛠️ *Service:* {escape_markdown(service)}\n🗓️ *Time:* {escape_markdown(dt_str)}"
        send_telegram_notification(msg)
        return jsonify({'message': 'Вы успешно записаны!'}), 201
    except Exception as e:
        conn.rollback(); print("Ошибка в /book:", e); return jsonify({'message': 'Ошибка сервера.'}), 500
    finally:
        conn.close()

@app.route('/cancel', methods=['POST'])
def cancel():
    conn = get_db_connection()
    ip = request.remote_addr
    try:
        phone = request.get_json().get('phone', '').strip()
        if not phone: return jsonify({'message': 'Укажите номер телефона.'}), 400
        
        row = conn.execute('SELECT * FROM bookings WHERE client_phone = ? AND booking_datetime > ? ORDER BY booking_datetime ASC LIMIT 1', (phone, datetime.now().isoformat())).fetchone()
        if not row: return jsonify({'message': 'Активных записей не найдено.'}), 404
        
        conn.execute('DELETE FROM bookings WHERE id = ?', (row['id'],))
        log_user_action(conn, ip, 'cancel')
        check_and_apply_abuse_rule(conn, ip)
        conn.commit()

        dt_str = datetime.fromisoformat(row['booking_datetime']).strftime("%d %B at %H:%M")
        msg = f"❌ *Booking Cancelled by User\\!*\n\n👤 *Client:* {escape_markdown(row['client_name'])} \KATEX_INLINE_OPEN`{escape_markdown(row['client_phone'])}`\KATEX_INLINE_CLOSE\n🗓️ *Cancelled for:* {escape_markdown(dt_str)}"
        send_telegram_notification(msg)
        return jsonify({'message': 'Запись отменена.'}), 200
    except Exception as e:
        conn.rollback(); print("Ошибка в /cancel:", e); return jsonify({'message': 'Ошибка сервера.'}), 500
    finally:
        conn.close()

# === МАРШРУТЫ ДЛЯ СКРЫТОЙ АДМИН-ПАНЕЛИ ===

@app.route(f'/{SECRET_URL_PART}', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True; return redirect(url_for('admin'))
        else:
            flash('Неверный пароль!', 'error'); return redirect(url_for('admin'))

    if 'admin_logged_in' in session:
        conn = get_db_connection()
        bookings = conn.execute('SELECT * FROM bookings WHERE booking_datetime > ? ORDER BY booking_datetime ASC', (datetime.now().isoformat(),)).fetchall()
        conn.close()
        processed_bookings = []
        for booking in bookings:
            booking_dict = dict(booking); dt_obj = datetime.fromisoformat(booking_dict['booking_datetime'])
            booking_dict['formatted_date'] = dt_obj.strftime("%d %B (%A)"); booking_dict['formatted_time'] = dt_obj.strftime("%H:%M")
            processed_bookings.append(booking_dict)
        return render_template('admin.html', bookings=processed_bookings)
    
    return render_template('admin_login.html')

@app.route(f'/{SECRET_URL_PART}/cancel/<int:booking_id>', methods=['POST'])
def admin_cancel(booking_id):
    if 'admin_logged_in' not in session: return redirect(url_for('admin'))
    
    conn = get_db_connection()
    try:
        booking_to_delete = conn.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,)).fetchone()
        if booking_to_delete:
            conn.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
            conn.commit()
            dt_str = datetime.fromisoformat(booking_to_delete['booking_datetime']).strftime("%d %B at %H:%M")
            
            # --- ИСПРАВЛЕНА ОШИБКА С KATEX ---
            msg = (f"🗑️ *Booking Cancelled by Admin\\!*\n\n"
                   f"👤 *Client:* {escape_markdown(booking_to_delete['client_name'])} \KATEX_INLINE_OPEN{escape_markdown(booking_to_delete['client_phone'])}\KATEX_INLINE_CLOSE\n"
                   f"🗓️ *Time:* {escape_markdown(dt_str)}")
            # ---------------------------------
            send_telegram_notification(msg)
            flash('Запись успешно отменена.', 'success')
        else:
            flash('Запись не найдена.', 'error')
    except Exception as e:
        conn.rollback(); print(f"Ошибка в /admin/cancel: {e}"); flash('Произошла ошибка при отмене записи.', 'error')
    finally:
        conn.close()
        
    return redirect(url_for('admin'))

@app.route(f'/{SECRET_URL_PART}/logout')
def logout():
    session.pop('admin_logged_in', None)
    flash('Вы успешно вышли.', 'success')
    return redirect(url_for('admin'))

# ============================================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')