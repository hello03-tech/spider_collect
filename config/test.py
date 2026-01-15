import os
from openai import OpenAI

# 配置环境变量
os.environ.setdefault('OPENAI_BASE_URL', 'http://14.103.60.158:3001/')
os.environ.setdefault('OPENAI_API_KEY', 'sk-g1S9X6sV6rfgmpoDYNFZV9YqD8lNQyRhhPu0hXs1ay8J25Hx')
os.environ.setdefault('MODEL',  "gemini-3-pro-preview")

def test_api_key():
    try:
        # 初始化客户端（使用自定义的 base_url）
        client = OpenAI(
            base_url=os.getenv('OPENAI_BASE_URL'),
            api_key=os.getenv('OPENAI_API_KEY')
        )

        # 发送简单的测试请求（兼容 OpenAI 格式的对话接口）
        response = client.chat.completions.create(
            model=os.getenv('MODEL'),
            messages=[
                {"role": "user", "content": "请返回「测试成功」四个字即可"}
            ],
            temperature=0.0,
            max_tokens=10
        )

        # 解析响应并验证
        content = response.choices[0].message.content.strip()
        print(f"✅ API Key 可用！响应内容：{content}")
        return True

    except Exception as e:
        print(f"❌ API Key 不可用或配置错误！错误信息：{str(e)}")
        return False

if __name__ == "__main__":
    test_api_key()