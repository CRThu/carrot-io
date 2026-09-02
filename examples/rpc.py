"""
跨网络 RPC 硬件透传代理示例 (RpcServer & RpcRemoteTransport)
"""
import asyncio
import cio


async def main():
    # 1. 启动本地轻量级 RPC 网关守护进程 (监听 127.0.0.1:8999)
    server = await cio.start_rpc_server("127.0.0.1", 8999)
    print("[RPC Server] 网关已启动，正在监听 127.0.0.1:8999...")

    try:
        # 2. 客户端通过 rpc+mock:// 建立透明 RPC 代理连接
        async with cio.connect("rpc+mock://127.0.0.1:8999", timeout=2.0) as remote_dev:
            await remote_dev.write(b"HELLO_REMOTE_DEVICE\n")
            print("远程写入成功，最近历史记录:")
            print(remote_dev.dump_history(limit=1))
    finally:
        # 3. 关闭网关服务
        await server.stop()
        print("[RPC Server] 服务已停止。")


if __name__ == "__main__":
    asyncio.run(main())
