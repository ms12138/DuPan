import os
import time
import re
import requests
import json
import logging
import sys
import random

# 从环境变量中获取相关参数
BAIDU_COOKIE = os.environ.get('BAIDU_COOKIE', '')
PUSH_PLUS_TOKEN = os.environ.get('PUSH_PLUS_TOKEN', '')

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# 请求头配置
HEADERS = {
    'Connection': 'keep-alive',
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'X-Requested-With': 'XMLHttpRequest',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Referer': 'https://pan.baidu.com/wap/main',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Origin': 'https://pan.baidu.com',
}

final_messages = []

def add_message(msg: str):
    """统一收集消息并打印"""
    print(msg)
    logger.info(msg)
    final_messages.append(msg)

def safe_request(url, headers, timeout=25, method='GET', retries=3, backoff_factor=2):
    """增强的请求函数，带指数退避重试机制"""
    for attempt in range(retries):
        try:
            # 随机延迟避免请求过于密集
            if attempt > 0:
                sleep_time = backoff_factor ** attempt + random.uniform(0.5, 1.5)
                add_message(f"🔄 第{attempt+1}次重试，等待{sleep_time:.1f}秒...")
                time.sleep(sleep_time)
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            else:
                response = requests.post(url, headers=headers, timeout=timeout)
            
            # 检查响应状态
            if response.status_code == 200:
                return response
            elif response.status_code in [403, 429]:
                add_message(f"⚠️ 请求被限制，状态码: {response.status_code}")
                if attempt < retries - 1:
                    continue
                else:
                    return response
            else:
                if attempt < retries - 1:
                    continue
                else:
                    return response
                    
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                add_message(f"⏰ 请求超时，准备重试...")
                continue
            else:
                raise requests.exceptions.Timeout(f"请求超时，已重试{retries}次")
        except requests.exceptions.ConnectionError:
            if attempt < retries - 1:
                add_message(f"🔌 连接错误，准备重试...")
                continue
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                add_message(f"⚠️ 请求异常: {str(e)[:50]}，准备重试...")
                continue
            else:
                raise

def validate_cookie():
    """验证Cookie格式和有效性"""
    if not BAIDU_COOKIE.strip():
        return False, "Cookie为空"
    
    # 检查必要的cookie字段
    required_fields = ['BDUSS', 'STOKEN', 'BAIDUID']
    cookie_fields = BAIDU_COOKIE.split(';')
    cookie_dict = {}
    
    for field in cookie_fields:
        if '=' in field:
            key, value = field.strip().split('=', 1)
            cookie_dict[key] = value
    
    missing = [field for field in required_fields if field not in cookie_dict]
    
    if missing:
        return False, f"缺少必要的Cookie字段: {missing}"
    
    return True, "Cookie格式正确"

def signin():
    """执行每日签到 - 增强稳定性"""
    if not BAIDU_COOKIE.strip():
        add_message("❌ 未检测到BAIDU_COOKIE，请检查环境变量配置")
        return False

    # 多个签到接口，增加接口数量
    signin_urls = [
        {
            'url': 'https://pan.baidu.com/rest/2.0/membership/level?method=signin',
            'name': '接口A'
        },
        {
            'url': 'https://pan.baidu.com/rest/2.0/membership/level?app_id=250528&web=5&method=signin',
            'name': '接口B'
        },
        {
            'url': 'https://pan.baidu.com/api/member/signin',
            'name': '接口C'
        }
    ]
    
    signed_headers = HEADERS.copy()
    signed_headers['Cookie'] = BAIDU_COOKIE
    
    for signin_info in signin_urls:
        url = signin_info['url']
        name = signin_info['name']
        
        add_message(f"🔄 尝试签到接口: {name}")
        
        try:
            resp = safe_request(url, signed_headers, timeout=20, retries=2)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    
                    # 检查是否有积分信息
                    if 'points' in data:
                        add_message(f"✅ 签到成功，获得积分: {data['points']}")
                        return True
                    elif 'error_msg' in data:
                        error_msg = data['error_msg']
                        if 'repeat' in error_msg.lower() or '已签到' in error_msg:
                            add_message("ℹ️ 今日已签到，无需重复签到")
                            return True
                        else:
                            add_message(f"ℹ️ 签到信息: {error_msg}")
                            return True
                    elif 'errno' in data and data['errno'] == 0:
                        add_message("✅ 签到成功")
                        return True
                    else:
                        # 尝试多种匹配方式
                        sign_point = re.search(r'points["\s:]+(\d+)', resp.text)
                        if sign_point:
                            add_message(f"✅ 签到成功，获得积分: {sign_point.group(1)}")
                            return True
                        elif 'success' in resp.text.lower() or 'errno":0' in resp.text:
                            add_message("✅ 签到成功")
                            return True
                        else:
                            add_message(f"⚠️ 签到接口响应异常: {resp.text[:100]}")
                            continue
                            
                except json.JSONDecodeError:
                    # JSON解析失败，尝试正则匹配
                    sign_point = re.search(r'points["\s:]+(\d+)', resp.text)
                    signin_error_msg = re.search(r'"error_msg":"(.*?)"', resp.text)

                    if sign_point:
                        add_message(f"✅ 签到成功，获得积分: {sign_point.group(1)}")
                        return True
                    elif signin_error_msg and signin_error_msg.group(1):
                        msg = signin_error_msg.group(1)
                        if 'repeat' in msg.lower() or '已签到' in msg:
                            add_message("ℹ️ 今日已签到，无需重复签到")
                            return True
                        else:
                            add_message(f"ℹ️ 签到信息: {msg}")
                            return True
                    elif 'success' in resp.text.lower():
                        add_message("✅ 签到成功")
                        return True
                    else:
                        add_message(f"⚠️ 签到接口响应格式异常")
                        continue
            else:
                add_message(f"⚠️ 签到接口 {name} 失败，状态码: {resp.status_code}")
                continue
                
        except Exception as e:
            add_message(f"⚠️ 签到接口 {name} 异常: {str(e)[:50]}")
            continue
        
        time.sleep(2)
    
    add_message("❌ 所有签到接口尝试失败")
    return False

def get_daily_question():
    """获取每日问题 - 增强稳定性"""
    if not BAIDU_COOKIE.strip():
        return None, None

    # 多个问题接口
    question_urls = [
        "https://pan.baidu.com/act/v2/membergrowv2/getdailyquestion?app_id=250528&web=5&clienttype=0",
        "https://pan.baidu.com/act/v2/membergrowv2/getdailyquestion"
    ]
    
    signed_headers = HEADERS.copy()
    signed_headers['Cookie'] = BAIDU_COOKIE
    
    for url in question_urls:
        try:
            add_message(f"🔍 尝试问题接口: {url.split('?')[0]}")
            resp = safe_request(url, signed_headers, timeout=25, retries=2)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    
                    if data.get('errno') == 0:
                        question_data = data.get('data', {})
                        answer_status = question_data.get('answer_status')
                        
                        if answer_status == 1:
                            add_message("ℹ️ 今日问题已回答，无需重复答题")
                            return None, None
                        
                        answer = question_data.get('answer')
                        ask_id = question_data.get('ask_id')
                        
                        if answer is not None and ask_id is not None:
                            question = question_data.get('question', '未知问题')
                            add_message(f"📝 今日问题: {question}")
                            add_message(f"✅ 正确答案: {answer}")
                            return str(answer), str(ask_id)
                        
                        add_message("ℹ️ 未获取到可回答的问题")
                        return None, None
                        
                    else:
                        errno = data.get('errno')
                        if errno == 11000:
                            add_message("ℹ️ 今日问题已回答，无需重复答题")
                            return None, None
                        else:
                            add_message(f"ℹ️ 获取问题失败，错误码: {errno}")
                            continue
                            
                except json.JSONDecodeError:
                    add_message("⚠️ 答题接口响应格式异常，尝试下一个接口")
                    continue
                    
            elif resp.status_code == 404:
                add_message("ℹ️ 答题接口不存在，尝试下一个接口")
                continue
            else:
                add_message(f"⚠️ 获取问题失败，状态码: {resp.status_code}，尝试下一个接口")
                continue
                
        except Exception as e:
            add_message(f"⚠️ 获取问题请求异常: {e}，尝试下一个接口")
            continue
    
    add_message("❌ 所有问题接口尝试失败")
    return None, None

def answer_question(answer, ask_id):
    """回答每日问题 - 增强稳定性"""
    if not BAIDU_COOKIE.strip() or not answer or not ask_id:
        add_message("❌ 答题参数不完整")
        return False

    # 多个答题接口
    answer_urls = [
        f"https://pan.baidu.com/act/v2/membergrowv2/answerquestion?app_id=250528&web=5&ask_id={ask_id}&answer={answer}",
        f"https://pan.baidu.com/act/v2/membergrowv2/answerquestion?ask_id={ask_id}&answer={answer}"
    ]
    
    signed_headers = HEADERS.copy()
    signed_headers['Cookie'] = BAIDU_COOKIE
    
    for url in answer_urls:
        try:
            add_message(f"📤 尝试答题接口: {url.split('?')[0]}")
            resp = safe_request(url, signed_headers, timeout=25, retries=2)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    
                    if data.get('errno') == 0:
                        question_data = data.get('data', {})
                        score = question_data.get('score')
                        
                        if score:
                            add_message(f"🎉 答题成功，获得积分: {score}")
                        else:
                            add_message("✅ 答题成功")
                        
                        show_msg = data.get('show_msg')
                        if show_msg:
                            add_message(f"ℹ️ {show_msg}")
                        
                        return True
                        
                    else:
                        errno = data.get('errno')
                        show_msg = data.get('show_msg', '')
                        
                        if errno == 11000 or '已答' in show_msg:
                            add_message("ℹ️ 今日问题已回答，无需重复答题")
                            return True
                        else:
                            add_message(f"❌ 答题失败，错误码: {errno}")
                            if show_msg:
                                add_message(f"ℹ️ {show_msg}")
                            continue
                            
                except json.JSONDecodeError:
                    add_message("⚠️ 答题接口响应格式异常，尝试下一个接口")
                    continue
            else:
                add_message(f"❌ 答题失败，状态码: {resp.status_code}，尝试下一个接口")
                continue
                
        except Exception as e:
            add_message(f"⚠️ 答题请求异常: {e}，尝试下一个接口")
            continue
    
    add_message("❌ 所有答题接口尝试失败")
    return False

def get_user_info():
    """获取用户信息 - 简化版"""
    if not BAIDU_COOKIE.strip():
        add_message("❌ 未检测到Cookie，跳过用户信息获取")
        return False

    url = "https://pan.baidu.com/rest/2.0/membership/user?app_id=250528&web=5&method=query"
    signed_headers = HEADERS.copy()
    signed_headers['Cookie'] = BAIDU_COOKIE
    
    try:
        resp = safe_request(url, signed_headers, timeout=15, retries=1)
        
        if resp.status_code == 200:
            # 简化解析逻辑
            text = resp.text
            current_level_match = re.search(r'current_level["\s:]+(\d+)', text)
            current_value_match = re.search(r'current_value["\s:]+(\d+)', text)
            
            if current_level_match and current_value_match:
                add_message(f"📊 当前会员等级: {current_level_match.group(1)}, 成长值: {current_value_match.group(1)}")
                return True
            else:
                add_message("ℹ️ 用户信息解析失败，已跳过")
                return False
        else:
            add_message(f"⚠️ 用户信息接口失败，状态码: {resp.status_code}")
            return False
            
    except Exception as e:
        add_message(f"⚠️ 用户信息请求异常，已跳过: {str(e)[:50]}")
        return False

def send_pushplus_once(message):
    """推送消息到pushPlus"""
    if not PUSH_PLUS_TOKEN.strip():
        print("未提供PUSH_PLUS_TOKEN，无法发送通知")
        return

    url = "http://www.pushplus.plus/send"
    payload = {
        'token': PUSH_PLUS_TOKEN,
        'title': '百度网盘签到通知',
        'content': message,
        'template': 'txt'
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('code') == 200:
                add_message("📤 消息推送成功")
            else:
                add_message(f"❌ 消息推送失败: {result.get('msg', '未知错误')}")
        else:
            add_message(f"❌ 消息推送失败，状态码: {resp.status_code}")
    except Exception as e:
        add_message(f"⚠️ 发送推送消息时出现异常: {e}")

def main():
    """脚本主流程"""
    add_message("=" * 40)
    add_message("🚀 百度网盘签到脚本开始执行")
    add_message("=" * 40)
    
    # 验证Cookie
    is_valid, msg = validate_cookie()
    if not is_valid:
        add_message(f"❌ {msg}")
        add_message("脚本停止执行")
        if final_messages:
            summary_msg = "\n".join(final_messages)
            send_pushplus_once(summary_msg)
        return
    
    add_message(f"✅ {msg}")
    
    # 增加随机延迟，避免请求过于集中
    delay = random.uniform(2, 8)
    add_message(f"⏳ 随机延迟 {delay:.1f} 秒...")
    time.sleep(delay)
    
    # 执行签到
    add_message("\n1️⃣ 执行每日签到...")
    signin_success = signin()
    time.sleep(3)
    
    # 获取并回答问题
    add_message("\n2️⃣ 获取每日问题...")
    answer, ask_id = get_daily_question()
    
    question_success = False
    if answer and ask_id:
        add_message(f"📝 正在回答问题ID: {ask_id}")
        time.sleep(2)
        add_message("\n3️⃣ 提交答案...")
        question_success = answer_question(answer, ask_id)
    else:
        add_message("ℹ️ 跳过答题步骤")
        question_success = True  # 没有问题时不算失败
    
    # 获取用户信息
    time.sleep(2)
    add_message("\n4️⃣ 尝试获取用户信息...")
    get_user_info()
    
    add_message("\n" + "=" * 40)
    add_message("🏁 脚本执行完成")
    add_message("=" * 40)
    
    # 统计执行结果
    success_count = sum(1 for msg in final_messages if '✅' in msg or '🎉' in msg or '📤' in msg)
    info_count = sum(1 for msg in final_messages if 'ℹ️' in msg or '📊' in msg or '📝' in msg)
    warning_count = sum(1 for msg in final_messages if '⚠️' in msg or '⏰' in msg or '🔄' in msg)
    error_count = sum(1 for msg in final_messages if '❌' in msg)
    
    summary = f"\n📊 执行统计:\n"
    summary += f"✅ 成功: {success_count}\n"
    summary += f"ℹ️ 信息: {info_count}\n"
    summary += f"⚠️ 警告: {warning_count}\n"
    summary += f"❌ 错误: {error_count}\n"
    summary += f"📈 总体状态: {'成功' if signin_success and question_success else '部分成功'}"
    
    add_message(summary)
    
    # 推送汇总信息
    if final_messages:
        summary_msg = "\n".join(final_messages)
        send_pushplus_once(summary_msg)

if __name__ == "__main__":
    main()

def handler(event, context):
    main()
