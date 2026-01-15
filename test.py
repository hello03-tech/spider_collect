import os
import requests

# 使用正确的密钥
os.environ["OPENAI_API_KEY"] = "sk-g1S9X6sV6rfgmpoDYNFZV9YqD8lNQyRhhPu0hXs1ay8J25Hx"

BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://14.103.60.158:3001/")
API_KEY = os.environ["OPENAI_API_KEY"]
MODEL = os.environ.get("MODEL", "gemini-3-pro-preview")

# 测试API是否可用
try:
    response = requests.post(
        f"{BASE_URL.rstrip('/')}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "hi"}],
        },
        timeout=30,
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应头: {response.headers}")
    
    response.raise_for_status()
    
    result = response.json()
    print("成功响应:")
    print(result)
    
except requests.exceptions.HTTPError as e:
    print(f"HTTP错误: {e}")
    if response.status_code == 401:
        print("认证失败！请检查：")
        print("1. API密钥是否正确")
        print("2. API密钥是否过期")
        print("3. 服务器是否需要其他认证方式")
        print(f"使用的密钥前几位: {API_KEY[:20]}...")
    
except Exception as e:
    print(f"其他错误: {type(e).__name__}: {e}")