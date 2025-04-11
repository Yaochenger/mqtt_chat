import paho.mqtt.client as mqtt
import json
import os
from openai import OpenAI
from dotenv import load_dotenv
import uuid

# 加载环境变量
load_dotenv()

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    print("错误: DEEPSEEK_API_KEY 未设置")
    exit(1)

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# MQTT 配置
MQTT_BROKER = "broker.emqx.io"  # 使用 EMQX 公共服务器
MQTT_PORT = 1883
MQTT_TOPIC = "deepseek/chat"
CLIENT_ID = f"deepseek-mqtt-{uuid.uuid4()}"

# 存储会话历史
conversations = {}

def get_deepseek_response(user_id, message):
    """获取 DeepSeek API 的响应"""
    try:
        # 如果用户没有会话历史，初始化
        if user_id not in conversations:
            conversations[user_id] = [
                {"role": "system", "content": "你是一个乐于助人的 AI 助手。"}
            ]
        
        # 添加用户消息到会话历史
        conversations[user_id].append({"role": "user", "content": message})
        
        # 保留最近 5 条消息以控制上下文长度
        if len(conversations[user_id]) > 5:
            conversations[user_id] = conversations[user_id][-5:]
        
        # 调用 DeepSeek API
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=conversations[user_id],
            stream=False
        )
        
        # 获取 AI 的响应
        ai_response = response.choices[0].message.content
        
        # 将 AI 响应添加到会话历史
        conversations[user_id].append({"role": "assistant", "content": ai_response})
        
        return ai_response
    except Exception as e:
        error_msg = f"DeepSeek API 错误: {str(e)}"
        print(error_msg)
        return error_msg

def on_connect(client, userdata, flags, reason_code, properties=None):
    """连接到 MQTT 服务器时的回调函数"""
    print(f"连接结果代码: {reason_code}")
    if reason_code == 0:
        client.subscribe(MQTT_TOPIC)
        print(f"已订阅主题: {MQTT_TOPIC}")
    else:
        print("MQTT 连接失败")

def on_message(client, userdata, msg):
    """接收到消息时的回调函数"""
    try:
        payload_str = msg.payload.decode()
        print(f"收到 MQTT 消息: {payload_str}")
        
        user_id = "anonymous"
        message = None
        
        # 尝试解析 JSON 格式
        try:
            payload = json.loads(payload_str)
            user_id = payload.get("user_id", "anonymous")
            message = payload.get("message", "")
        except json.JSONDecodeError:
            # 如果不是 JSON 格式，直接将消息作为纯文本处理
            print("消息不是 JSON 格式，尝试作为纯文本处理")
            message = payload_str.strip()
        
        if not message:
            print("消息为空，忽略")
            return
        
        # 获取 DeepSeek 的响应
        response = get_deepseek_response(user_id, message)
        
        # 准备响应消息（始终以 JSON 格式返回）
        response_payload = {
            "user_id": user_id,
            "response": response,
            "original_message": message
        }
        
        # 将响应发布回 MQTT 主题
        print(f"发布响应: {response_payload}")
        client.publish(MQTT_TOPIC, json.dumps(response_payload))
        
    except Exception as e:
        print(f"处理消息时出错: {str(e)}")

def main():
    # 初始化 MQTT 客户端，指定回调 API 版本
    mqtt_client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    # 连接到 MQTT 服务器
    print(f"尝试连接 MQTT 服务器: {MQTT_BROKER}:{MQTT_PORT}")
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"无法连接到 MQTT 服务器: {str(e)}")
        return
    
    print(f"在主题 {MQTT_TOPIC} 上启动 DeepSeek MQTT 聊天服务")
    
    # 启动 MQTT 循环
    mqtt_client.loop_forever()

if __name__ == "__main__":
    main()
