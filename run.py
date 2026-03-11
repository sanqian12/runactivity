import json
import base64
import random
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import requests
from datetime import datetime, timedelta, date
import logging
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# RSA公钥
RSA_PUBLIC_KEY = ""

RSA_PUBLIC_KEY1 = ""

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
]

def _env_bool(name, default=False):
    raw = str(os.environ.get(name, '')).strip().lower()
    if not raw:
        return default
    return raw in ('1', 'true', 'yes', 'y', 'on')

def _env_str(name, default=''):
    return (os.environ.get(name) or default).strip()

def _parse_student_codes(raw):
    raw = str(raw or '').strip()
    if not raw:
        return []
    parts = []
    for chunk in raw.replace('\n', ',').replace(';', ',').split(','):
        v = chunk.strip()
        if v:
            if '|' in v:
                v = v.split('|', 1)[0].strip()
                if not v:
                    continue
            parts.append(v)
    return parts

def _parse_expire_at(raw):
    raw = str(raw or '').strip()
    if not raw:
        return None

    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    try:
        d = datetime.strptime(raw, '%Y-%m-%d').date()
        return datetime.combine(d, datetime.strptime('23:59:59', '%H:%M:%S').time())
    except Exception:
        return None

def _parse_account_config(raw):
    raw = str(raw or '').strip()
    if not raw:
        return []

    rows = []
    for part in raw.replace('\n', ';').replace(',', ';').split(';'):
        item = part.strip()
        if not item:
            continue
        cols = [c.strip() for c in item.split('|')]
        if not cols or not cols[0]:
            continue
        student_code = cols[0]
        mode = (cols[1] if len(cols) > 1 else '').strip().lower() or None
        if mode not in (None, 'run', 'morning', 'both'):
            mode = None
        expire_raw = (cols[2] if len(cols) > 2 else '').strip()
        expire_at = _parse_expire_at(expire_raw) if expire_raw else None
        rows.append({
            'student_code': student_code,
            'mode': mode,
            'expire_at': expire_at,
            'expire_raw': expire_raw,
        })
    return rows



def get_route_b_running_route():
    return '[{}]'

def submit_run_request(student_code, client_ip, route_key='default', is_morning=False):
    student_code = str(student_code or '').strip()
    route_key = (route_key or 'default').strip() or 'default'

    mile = round(random.uniform(2.0, 5.0), 1)
    speed = random.randint(6, 12)
    time_hours = mile / speed
    time_seconds = int(time_hours * 3600)

    if is_morning:
        logger.info(
            f"【晨跑】运动数据提交 - 账号: {student_code}, IP: {client_ip}, 里程: {mile}公里, 速度: {speed}km/h, 时间: {time_seconds}秒"
        )
    else:
        logger.info(
            f"运动数据提交 - 账号: {student_code}, IP: {client_ip}, 里程: {mile}公里, 速度: {speed}km/h, 时间: {time_seconds}秒"
        )

    now_dt = datetime.now()
    if is_morning:
        today_val = date.today()
        earliest_start_dt = datetime.combine(today_val, datetime.strptime("06:30", "%H:%M").time())
        latest_end_dt = datetime.combine(today_val, datetime.strptime("08:00", "%H:%M").time())
        latest_start_dt = latest_end_dt - timedelta(seconds=time_seconds)
        if latest_start_dt < earliest_start_dt:
            latest_start_dt = earliest_start_dt
        available_seconds = int((latest_start_dt - earliest_start_dt).total_seconds())
        if available_seconds < 0:
            available_seconds = 0
        offset_seconds = random.randint(0, available_seconds)
        start_dt = earliest_start_dt + timedelta(seconds=offset_seconds)
        end_dt = start_dt + timedelta(seconds=time_seconds)
        start_time = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        end_time = now_dt.strftime('%Y-%m-%d %H:%M:%S')
        start_time = (now_dt - timedelta(seconds=time_seconds)).strftime('%Y-%m-%d %H:%M:%S')

    exercise_id = build_exercise_id(student_code)
    if route_key != 'route_b':
        return {
            'ok': False,
            'error': '仅支持 route=route_b',
            'mile': mile,
            'speed': speed,
            'time_seconds': time_seconds,
        }

    running_route = get_route_b_running_route()

    original_data = [{
    }]

    encrypted_data = encrypt_exercise_data(original_data)
    response = send_request(encrypted_data, student_code)
    if not response:
        if is_morning:
            logger.error(f"【晨跑】运动数据提交失败 - 账号: {student_code}, IP: {client_ip}, 请求失败")
        else:
            logger.error(f"运动数据提交失败 - 账号: {student_code}, IP: {client_ip}, 请求失败")
        return {
            'ok': False,
            'error': '请求失败',
            'mile': mile,
            'speed': speed,
            'time_seconds': time_seconds,
        }

    try:
        response_data = response.json()
    except Exception:
        response_data = None

    if is_morning:
        logger.info(f"【晨跑】服务器响应 - 账号: {student_code}, 响应内容: {response_data}")
    else:
        logger.info(f"服务器响应 - 账号: {student_code}, 响应内容: {response_data}")

    if not isinstance(response_data, dict):
        if is_morning:
            logger.error(f"【晨跑】运动数据提交失败 - 账号: {student_code}, IP: {client_ip}, 响应格式不正确")
        else:
            logger.error(f"运动数据提交失败 - 账号: {student_code}, IP: {client_ip}, 响应格式不正确")
        return {
            'ok': False,
            'error': '响应格式不正确',
            'mile': mile,
            'speed': speed,
            'time_seconds': time_seconds,
        }

    response_id = None
    try:
        if response_data.get('data') and response_data['data'].get('id'):
            response_id = response_data['data']['id']
    except Exception:
        response_id = None

    if not response_id or str(response_id) == '0':
        if is_morning:
            logger.warning(f"【晨跑】运动数据提交失败 - 账号: {student_code}, IP: {client_ip}, 响应ID为0")
        else:
            logger.warning(f"运动数据提交失败 - 账号: {student_code}, IP: {client_ip}, 响应ID为0")
        return {
            'ok': False,
            'error': '提交失败',
            'response': response_data,
            'mile': mile,
            'speed': speed,
            'time_seconds': time_seconds,
        }

    if is_morning:
        logger.info(f"【晨跑】运动数据提交成功 - 账号: {student_code}, IP: {client_ip}, 里程: {mile}公里, 速度: {speed}km/h")
    else:
        logger.info(f"运动数据提交成功 - 账号: {student_code}, IP: {client_ip}, 里程: {mile}公里, 速度: {speed}km/h")

    text = f"✅ 提交成功！本次运动数据：里程 {mile} 公里，速度 {speed} km/h"

    return {
        'ok': True,
        'text': text,
        'response': response_data,
        'mile': mile,
        'speed': speed,
        'time_seconds': time_seconds,
    }

def rsa_encrypt(text):
    try:
        public_key = RSA.import_key(base64.b64decode(RSA_PUBLIC_KEY))
        cipher = PKCS1_v1_5.new(public_key)
        encrypted = cipher.encrypt(text.encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')
    except Exception as e:
        return None

def rsa_encrypt1(text):
    try:
        public_key = RSA.import_key(base64.b64decode(RSA_PUBLIC_KEY1))
        cipher = PKCS1_v1_5.new(public_key)
        encrypted = cipher.encrypt(text.encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')
    except Exception as e:
        return None

def rsa_encrypt_long(data, public_key_str, chunk_size=117):
    """对超长数据进行分段RSA加密，返回逗号分隔的base64加密串"""
    try:
        public_key = RSA.import_key(base64.b64decode(public_key_str))
        cipher = PKCS1_v1_5.new(public_key)
        data_bytes = data.encode('utf-8')
        encrypted_chunks = []
        for i in range(0, len(data_bytes), chunk_size):
            chunk = data_bytes[i:i+chunk_size]
            encrypted = cipher.encrypt(chunk)
            encrypted_chunks.append(base64.b64encode(encrypted).decode('utf-8'))
        return ''.join(encrypted_chunks)
    except Exception as e:
        print(f"分段加密失败: {e}")
        return None

def encrypt_exercise_data(data_list):
    """所有字段名都加密，runningRoute内容明文，其它内容加密"""
    encrypted_list = []
    for item in data_list:
        encrypted_item = {}
        for key, value in item.items():
            encrypted_key = rsa_encrypt(str(key))
            if key == 'runningRoute':
                encrypted_item[encrypted_key] = value  # 内容明文
            else:
                encrypted_value = rsa_encrypt(str(value)) if value else value
                encrypted_item[encrypted_key] = encrypted_value
        encrypted_list.append(encrypted_item)
    return encrypted_list

def send_request(encrypted_data, student_code):
    """发送HTTP请求"""
    url = ""

    headers = { }
    
    # 构造请求体
    data = {
        'list': json.dumps(encrypted_data)
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        logger.info(f"请求状态码: {response.status_code}")
        logger.info(f"响应内容: {response.text}")
        return response
    except Exception as e:
        logger.error(f"请求失败: {e}")
        return None

def main():
    account_rows = _parse_account_config(_env_str('ACCOUNT_CONFIG', ''))
    if account_rows:
        student_codes = [r['student_code'] for r in account_rows]
        account_map = {r['student_code']: r for r in account_rows}
    else:
        raw_codes = _env_str('AIIT_STUDENT_CODES', '') or _env_str('STUDENT_CODES', '')
        account_rows = _parse_account_config(raw_codes) if '|' in raw_codes else []
        if account_rows:
            student_codes = [r['student_code'] for r in account_rows]
            account_map = {r['student_code']: r for r in account_rows}
        else:
            student_codes = _parse_student_codes(raw_codes)
            account_map = {}

    if not student_codes:
        logger.error('未配置学号列表，请设置环境变量 ACCOUNT_CONFIG 或 AIIT_STUDENT_CODES/STUDENT_CODES')
        return

    global_expire_raw = _env_str('EXPIRE_AT', '')
    global_expire_at = _parse_expire_at(global_expire_raw)
    if global_expire_at is None and global_expire_raw:
        logger.error('EXPIRE_AT 格式错误，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS')
        return

    global_run_mode = (_env_str('RUN_MODE', 'both') or 'both').strip().lower()
    client_ip = _env_str('CLIENT_IP', '127.0.0.1')

    allow_forbidden_time = _env_bool('ALLOW_FORBIDDEN_TIME', default=True)
    if not allow_forbidden_time and not check_time_restriction():
        logger.warning('当前时间段禁止提交，已跳过')
        return

    random_delay_enable = _env_bool('RANDOM_DELAY_ENABLE', default=True)
    try:
        random_delay_max = int(_env_str('RANDOM_DELAY_MAX_SECONDS', '600') or '600')
    except Exception:
        random_delay_max = 600
    if random_delay_max < 0:
        random_delay_max = 0



    for student_code in student_codes:
        row = account_map.get(student_code) or {}
        run_mode = (row.get('mode') or global_run_mode or 'both').strip().lower()
        expire_at = row.get('expire_at') if 'expire_at' in row else global_expire_at
        expire_raw = row.get('expire_raw') if 'expire_raw' in row else global_expire_raw

        if expire_at is None and expire_raw:
            logger.error(f'{student_code} EXPIRE_AT 格式错误：{expire_raw}')
            continue

        if expire_at is not None and datetime.now() > expire_at:
            logger.warning(f'{student_code} 已过期，跳过执行：{expire_at.strftime("%Y-%m-%d %H:%M:%S")}')
            continue

        if run_mode in ('run', 'normal', 'both'):
            result = submit_run_request(student_code, client_ip, route_key='route_b', is_morning=False)
            logger.info(result.get('text') or result)

        if run_mode in ('morning', 'am', 'both'):
            result = submit_run_request(student_code, client_ip, route_key='route_b', is_morning=True)
            logger.info(result.get('text') or result)

def check_time_restriction():
    now = datetime.now()
    current_time = now.time()
    forbidden_start = datetime.strptime('22:30', '%H:%M').time()
    forbidden_end = datetime.strptime('07:00', '%H:%M').time()
    if current_time >= forbidden_start or current_time <= forbidden_end:
        return False
    return True

if __name__ == '__main__':
    main()
