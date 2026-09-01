"""
snowflake_base62.py — 雪花算法 Base62 ID 生成器

全局唯一，无前缀。供各 skill 调用以生成节点 ID。

结构（64 bit）:
  1 bit   - 符号位，始终为 0
  41 bit  - 时间戳（毫秒级），相对 custom_epoch，约可用 69 年
  10 bit  - 机器 ID（0 ~ 1023）
  12 bit  - 序列号（0 ~ 4095），同一毫秒内递增

输出：Base62 字符串（0-9 A-Z a-z），比纯数字更短、URL-safe。

CLI 用法：
    python .claude/scripts/snowflake_base62.py -n 1 -q   # 安静模式，每行一个 id
"""

import time
import threading

# ── Base62 编码 ───────────────────────────────────────────────

BASE62_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = 62


def base62_encode(num: int) -> str:
    """将非负整数编码为 Base62 字符串。"""
    if num < 0:
        raise ValueError("只支持非负整数")
    if num == 0:
        return "0"
    chars = []
    while num:
        num, rem = divmod(num, BASE)
        chars.append(BASE62_CHARSET[rem])
    return "".join(reversed(chars))


# ── 雪花算法 ──────────────────────────────────────────────────

TIMESTAMP_BITS = 41
MACHINE_ID_BITS = 10
SEQUENCE_BITS = 12

MACHINE_ID_MAX = (1 << MACHINE_ID_BITS) - 1  # 1023
SEQUENCE_MAX = (1 << SEQUENCE_BITS) - 1  # 4095

TIMESTAMP_SHIFT = MACHINE_ID_BITS + SEQUENCE_BITS  # 22
MACHINE_ID_SHIFT = SEQUENCE_BITS  # 12


class SnowflakeGenerator:
    """
    线程安全的雪花 ID 生成器。

    Parameters
    ----------
    machine_id : int
        机器 / 实例标识（0 ~ 1023）。
    custom_epoch : int
        自定义纪元（毫秒时间戳），默认 2024-01-01 00:00:00 UTC。
    """

    def __init__(
        self,
        machine_id: int = 0,
        custom_epoch: int = 1704067200000,  # 2024-01-01 00:00:00 UTC
    ):
        if not (0 <= machine_id <= MACHINE_ID_MAX):
            raise ValueError(f"machine_id 必须在 0 ~ {MACHINE_ID_MAX} 之间")

        self.machine_id = machine_id
        self.custom_epoch = custom_epoch
        self._sequence = 0
        self._last_timestamp = -1
        self._lock = threading.Lock()

    # ── 内部方法 ────────────────────────────────────────────

    def _current_ms(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_ms(self, last: int) -> int:
        """自旋等待到下一毫秒。"""
        ts = self._current_ms()
        while ts <= last:
            time.sleep(0.0001)
            ts = self._current_ms()
        return ts

    def _generate_one(self) -> int:
        """生成单个雪花 ID（int），调用方须持有锁。"""
        ts = self._current_ms()

        if ts < self._last_timestamp:
            raise RuntimeError(
                f"时钟回拨: 当前 {ts} < 上次 {self._last_timestamp}"
            )

        if ts == self._last_timestamp:
            self._sequence = (self._sequence + 1) & SEQUENCE_MAX
            if self._sequence == 0:
                ts = self._wait_next_ms(ts)
        else:
            self._sequence = 0

        self._last_timestamp = ts

        delta = ts - self.custom_epoch
        return (
            (delta << TIMESTAMP_SHIFT)
            | (self.machine_id << MACHINE_ID_SHIFT)
            | self._sequence
        )

    # ── 公开 API ────────────────────────────────────────────

    def next_id(self) -> int:
        """生成下一个雪花 ID（int）。"""
        with self._lock:
            return self._generate_one()

    def next_id_base62(self) -> str:
        """生成下一个雪花 ID 并以 Base62 编码返回。"""
        return base62_encode(self.next_id())

    def batch(self, count: int) -> list[str]:
        """
        批量生成 Base62 编码的雪花 ID。

        一次性获取锁，在锁内连续生成，比逐个调用更高效。

        Parameters
        ----------
        count : int
            生成数量（≥ 1）。

        Returns
        -------
        list[str]
            Base62 编码的 ID 列表，长度 == count。
        """
        if count < 1:
            raise ValueError("count 必须 ≥ 1")
        with self._lock:
            return [base62_encode(self._generate_one()) for _ in range(count)]


# ── CLI 入口 ─────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="雪花算法 Base62 ID 生成器")
    parser.add_argument(
        "-n", "--count", type=int, default=5, help="生成数量（默认 5）"
    )
    parser.add_argument(
        "-m", "--machine-id", type=int, default=0, help="机器 ID（0~1023）"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="安静模式：仅输出 ID，每行一个"
    )
    args = parser.parse_args()

    gen = SnowflakeGenerator(machine_id=args.machine_id)
    ids = gen.batch(args.count)

    if args.quiet:
        for uid in ids:
            print(uid)
    else:
        print(f"生成 {args.count} 个 ID（machine_id={args.machine_id}）:")
        for i, uid in enumerate(ids, 1):
            print(f"  {i:>3}. {uid}")
