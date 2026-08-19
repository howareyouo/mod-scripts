import random
import struct
import sys

ROUNDS = 12
ROUND_KEYS = 2 * (ROUNDS + 1)

CK_NAME = 0x7A21C951691CD470
CK_KEY = -5408575981733630035


def to_int32(x):
    x &= 0xFFFFFFFF
    if x >= 0x80000000:
        x -= 0x100000000
    return x


def to_uint32(x):
    return x & 0xFFFFFFFF


def to_int64(x):
    x &= 0xFFFFFFFFFFFFFFFF
    if x >= 0x8000000000000000:
        x -= 0x10000000000000000
    return x


def to_uint64(x):
    return x & 0xFFFFFFFFFFFFFFFF


def rotate_left(x, y):
    shift = to_int32(y) & 31
    x_u = to_uint32(x)
    result = ((x_u << shift) | (x_u >> (32 - shift))) & 0xFFFFFFFF
    return to_int32(result)


def rotate_right(x, y):
    shift = to_int32(y) & 31
    x_u = to_uint32(x)
    result = ((x_u >> shift) | (x_u << (32 - shift))) & 0xFFFFFFFF
    return to_int32(result)


def pk_long(a, b):
    return to_int64((to_uint64(to_int32(a)) & 0xFFFFFFFF) | (to_uint64(to_int32(b)) << 32))


class CkCipher:
    def __init__(self, ck_key):
        ld = [to_int32(ck_key), to_int32(to_uint64(ck_key) >> 32)]

        self.rk = [0] * ROUND_KEYS
        self.rk[0] = -1209970333
        for i in range(1, ROUND_KEYS):
            self.rk[i] = to_int32(self.rk[i - 1] + (-1640531527))

        a = 0
        b = 0
        i = 0
        j = 0

        for _ in range(3 * ROUND_KEYS):
            self.rk[i] = rotate_left(to_int32(self.rk[i] + to_int32(a + b)), 3)
            a = self.rk[i]
            ld[j] = rotate_left(to_int32(ld[j] + to_int32(a + b)), to_int32(a + b))
            b = ld[j]
            i = (i + 1) % ROUND_KEYS
            j = (j + 1) % 2

    def encrypt(self, in_val):
        a = to_int32(to_int32(in_val) + self.rk[0])
        b = to_int32(to_int32(to_uint64(in_val) >> 32) + self.rk[1])
        for r in range(1, ROUNDS + 1):
            a = to_int32(rotate_left(to_int32(a ^ b), b) + self.rk[2 * r])
            b = to_int32(rotate_left(to_int32(b ^ a), a) + self.rk[2 * r + 1])
        return pk_long(a, b)

    def decrypt(self, in_val):
        a = to_int32(in_val)
        b = to_int32(to_uint64(in_val) >> 32)
        for i in range(ROUNDS, 0, -1):
            b = to_int32(rotate_right(to_int32(b - self.rk[2 * i + 1]), a) ^ a)
            a = to_int32(rotate_right(to_int32(a - self.rk[2 * i]), b) ^ b)
        b = to_int32(b - self.rk[1])
        a = to_int32(a - self.rk[0])
        return pk_long(a, b)


def crack(text):
    name = text.encode("utf-8")
    length = len(name) + 4
    padded = ((-length) & 7) + length

    buff = struct.pack(">I", len(name)) + name
    buff += b"\x00" * (padded - len(buff))

    ck = CkCipher(CK_NAME)
    out_buff = bytearray()

    for i in range(0, padded, 8):
        now_var = struct.unpack(">q", buff[i:i + 8])[0]
        dd = ck.encrypt(now_var)
        for shift in range(56, -1, -8):
            out_buff.append((to_uint64(dd) >> shift) & 0xFF)

    n = 0
    for b in out_buff:
        signed_b = b - 256 if b >= 128 else b
        n = rotate_left(to_int32(n ^ signed_b), 3)

    prefix = to_int32(n ^ 0x54882F8A)
    suffix = random.randint(0, 0x7FFFFFFF)
    in_val = to_int64(to_int64(prefix) << 32)

    shifted = suffix >> 16
    if shifted in (0x0401, 0x0402, 0x0403):
        in_val = to_int64(in_val | suffix)
    else:
        in_val = to_int64(in_val | (0x01000000 | (suffix & 0xFFFFFF)))

    out = CkCipher(CK_KEY).decrypt(in_val)

    n2 = 0
    in_u = to_uint64(in_val)
    for i in range(56, -1, -8):
        n2 ^= (in_u >> i) & 0xFF

    vv = to_int32(n2 & 0xFF)
    if vv < 0:
        vv = -vv

    return f"{vv:02x}{to_uint64(out):016x}"


def main():
    if len(sys.argv) > 1:
        name = sys.argv[1]
    else:
        name = input("请输入用户名 (默认 charles): ").strip() or "charles"
    key = crack(name)
    print(f"name: {name}\nkey: {key}")


def pause():
    print("按任意键退出...", end="", flush=True)
    import msvcrt
    msvcrt.getch()


if __name__ == "__main__":
    main()
    pause()
