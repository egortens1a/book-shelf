"""Read-only проверка готовности процесса, в том числе для Docker Compose."""

import grpc

from recsys.config import ServerSettings
from recsys.proto import recommendations_pb2 as pb
from recsys.proto import recommendations_pb2_grpc as rpc


def main():
    target = f"127.0.0.1:{ServerSettings().port}"
    try:
        with grpc.insecure_channel(target) as channel:
            ready = rpc.RecommendationServiceStub(channel).Check(pb.HealthRequest(), timeout=2).ready
    except grpc.RpcError:
        raise SystemExit(1) from None
    raise SystemExit(0 if ready else 1)


if __name__ == "__main__":
    main()
