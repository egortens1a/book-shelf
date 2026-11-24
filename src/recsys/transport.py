"""Общие лимиты транспорта, без ML-зависимостей в API."""

MAX_MESSAGE_BYTES = 16 * 1024 * 1024
GRPC_OPTIONS = (
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
)
