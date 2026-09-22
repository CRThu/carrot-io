"""
多通道数据采集与实时落盘教学示例 (DataCollector / Collector)

展示使用单一 collect() 方法进行：
- 多通道同时打点 (CH1=5.01, CH2=3.32)
- 单点指定物理单位打点
- 批量波形数据展开注入
- 实时流式落盘与汇总统计看板
"""
import asyncio
import cio

# 1. 异步原生采集示例 (推荐，适合大型异步自动化测试)
async def async_demo():
    print("--- 1. 原生异步多通道采集 (Async) ---")

    # 打开收集器 (指定文件则实时流式追加落盘，Crash-Safe)
    with cio.Collector("async_run.csv", transform=lambda raw: float(raw) * 1.002) as col:
        # 模拟 3 次采样循环
        for i in range(3):
            # 关键字多通道同时打点
            col.collect(CH1=5.0 + i * 0.1, CH2=3.3 - i * 0.05, TEMP=25.0 + i)
            await asyncio.sleep(0.05)

        # 注入一段波形数据 (向量列表默认自动展开)
        col.collect([1.1, 1.2, 1.3, 1.4], tag="WAVE", unit="V")

        # 打印包含 Median 的 ASCII 汇总统计看板
        col.print_summary()


# 2. 便捷同步模式 (常规线性测试脚本)
def sync_demo():
    print("\n--- 2. 便捷同步多通道采集 (Sync) ---")

    with cio.Collector("sync_run.csv") as col:
        # 单点打点 (指定通道与单位)
        col.collect(5.02, tag="VBUS", unit="V")
        col.collect(0.48, tag="IBUS", unit="A")

        # 也可以像函数一样直接调用
        col(VBUS=4.98, IBUS=0.52)

        print("VBUS 均值 (Mean):", col.mean("VBUS"))
        print("VBUS 中位数 (Median):", col.median("VBUS"))
        print("IBUS 最大值 (Max):", col.max("IBUS"))


if __name__ == "__main__":
    asyncio.run(async_demo())
    sync_demo()
