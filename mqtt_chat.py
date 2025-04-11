import paho.mqtt.client as mqtt
import os
from openai import OpenAI
from dotenv import load_dotenv
import uuid

# 加载环境变量
load_dotenv()

# 豆包 API 配置
DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY")
if not DOUBAO_API_KEY:
    print("错误: DOUBAO_API_KEY 未设置")
    exit(1)

# 初始化 OpenAI 客户端以连接豆包 API
openai_client = OpenAI(
    api_key=DOUBAO_API_KEY,
    base_url="https://ark.cn-beijing.volces.com/api/v3"
)

# MQTT 配置
MQTT_BROKER = "broker.emqx.io"  # 使用 EMQX 公共服务器
MQTT_PORT = 1883
BASE_TOPIC = "doubao/chat"
SUBSCRIBE_TOPIC = f"{BASE_TOPIC}/sub"
PUBLISH_TOPIC = f"{BASE_TOPIC}/pub"
CLIENT_ID = f"doubao-mqtt-{uuid.uuid4()}"
MODEL_ID = "ep-20250411160545-vmvmf"  # 使用你的豆包推理接入点 ID

# 存储会话历史
conversations = {}


def get_doubao_response(user_id, message):
    """获取豆包 API 的流式响应"""
    try:
        # 如果用户没有会话历史，初始化
        if user_id not in conversations:
            conversations[user_id] = [
                {"role": "system", "content": "你是人工智能助手"}
            ]

        # 添加用户消息到会话历史
        conversations[user_id].append({"role": "user", "content": message})

        # 保留最近 5 条消息以控制上下文长度
        if len(conversations[user_id]) > 5:
            conversations[user_id] = conversations[user_id][-5:]

        # 调用豆包 API 进行流式响应
        response_stream = openai_client.chat.completions.create(
            model=MODEL_ID,
            messages=conversations[user_id],
            stream=True
        )

        full_response = ""
        for chunk in response_stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                # 注释掉这行，不打印部分响应内容
                # print(content, end='', flush=True)

        # 将 AI 响应添加到会话历史
        conversations[user_id].append({"role": "assistant", "content": full_response})

        # 发布完整响应到 pub 主题
        mqtt_client.publish(PUBLISH_TOPIC, full_response)

        return full_response
    except Exception as e:
        error_msg = f"豆包 API 错误: {str(e)}"
        print(error_msg)
        # 发布错误响应到 pub 主题
        mqtt_client.publish(PUBLISH_TOPIC, error_msg)
        return error_msg


def on_connect(client, userdata, flags, reason_code, properties=None):
    """连接到 MQTT 服务器时的回调函数"""
    if reason_code == 0:
        client.subscribe(SUBSCRIBE_TOPIC)
        print(f"\033[91m:连接成功！\033[0m")
        print(f"服务器: {MQTT_BROKER}:{MQTT_PORT}")
        print(f"订阅主题: {SUBSCRIBE_TOPIC}")
        print(f"发布主题: {PUBLISH_TOPIC}")
        print(f"API URL: {openai_client.base_url}")
        print(f"模型 ID: {MODEL_ID}")
        print("\033[91m: Ctrl+C 退出\033[0m") 
    else:
        print(f"MQTT 连接失败，错误码: {reason_code}")


def on_message(client, userdata, msg):
    """接收到消息时的回调函数"""
    try:
        message = msg.payload.decode().strip()
        if not message:
            return

        user_id = "anonymous"
        # 获取豆包的响应
        get_doubao_response(user_id, message)
        # 注释掉这行，不打印空行
        # print()
    except Exception as e:
        print(f"处理消息时出错: {str(e)}")


def main():
    global mqtt_client
    # 初始化 MQTT 客户端，指定回调 API 版本
    mqtt_client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # 连接到 MQTT 服务器
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"无法连接到 MQTT 服务器: {str(e)}")
        return

    # 启动 MQTT 循环
    mqtt_client.loop_forever()


if __name__ == "__main__":
    main()