#!/usr/bin/env python3
"""Probe BPF_F_IPV6 without attaching a program or changing a network interface.
Exit 0: supported; 3: unsupported; 2: unknown (including permission/load failure).
Run with BPF privileges on the host or inside a privileged kind Node.
"""
import ctypes
import json
import os
import platform
import struct
import sys


def classify(rows):
    values = {r['flags']: r['helper_return'] for r in rows if r['test_errno'] == 0}
    if values.get(0) != 0 or values.get(16) != 0:
        return 'unknown'
    return {0: 'supported', -22: 'unsupported'}.get(values.get(144), 'unknown')


def probe():
    result = {'kernel': platform.release(), 'architecture': platform.machine(),
              'status': 'unknown', 'probe': 'unattached-sched-cls-zero-diff-v1', 'results': []}
    number = {'x86_64': 321, 'aarch64': 280}.get(platform.machine())
    if platform.system() != 'Linux' or number is None or sys.byteorder != 'little':
        result['error'] = 'unsupported probe platform'
        return result
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long

    def call(cmd, data):
        attr = ctypes.create_string_buffer(bytes(data), len(data))
        ctypes.set_errno(0)
        ret = libc.syscall(ctypes.c_long(number), ctypes.c_int(cmd),
                           ctypes.c_void_p(ctypes.addressof(attr)), ctypes.c_uint(len(data)))
        return ret, ctypes.get_errno() if ret == -1 else 0, attr.raw

    def put(data, offset, fmt, value):
        struct.pack_into('<' + fmt, data, offset, value)

    for flags in (0, 16, 144):
        # R1 holds __sk_buff. IPv6/TCP checksum field is Ethernet14 + IPv640 + TCP16.
        insns = [(0xb7, 2, 70), (0xb7, 3, 0), (0xb7, 4, 0),
                 (0xb7, 5, flags), (0x85, 0, 11), (0x95, 0, 0)]
        program = ctypes.create_string_buffer(b''.join(struct.pack('<BBhi', c, r, 0, i) for c, r, i in insns))
        license_buf = ctypes.create_string_buffer(b'GPL\0')
        verifier = ctypes.create_string_buffer(65536)
        attr = bytearray(120)
        for offset, fmt, val in [(0, 'I', 3), (4, 'I', len(insns)),
                                  (8, 'Q', ctypes.addressof(program)), (16, 'Q', ctypes.addressof(license_buf)),
                                  (24, 'I', 1), (28, 'I', len(verifier)), (32, 'Q', ctypes.addressof(verifier))]:
            put(attr, offset, fmt, val)
        fd, err, _ = call(5, attr)  # BPF_PROG_LOAD: SCHED_CLS, never attached/pinned
        if err:
            result.update(error=f'BPF_PROG_LOAD errno={err}', verifier=verifier.value.decode(errors='replace')[:2000])
            return result
        try:
            packet = bytearray(74)
            packet[12:14] = b'\x86\xdd'
            packet[14], packet[19], packet[20], packet[21] = 0x60, 20, 6, 64
            packet[29], packet[45], packet[66], packet[67] = 1, 2, 0x50, 2
            source = ctypes.create_string_buffer(bytes(packet), len(packet))
            output = ctypes.create_string_buffer(256)
            attr = bytearray(80)
            for offset, fmt, val in [(0, 'I', fd), (8, 'I', len(packet)), (12, 'I', len(output)),
                                      (16, 'Q', ctypes.addressof(source)), (24, 'Q', ctypes.addressof(output)), (32, 'I', 1)]:
                put(attr, offset, fmt, val)
            _, err, data = call(10, attr)  # BPF_PROG_TEST_RUN
            result['results'].append({'flags': flags, 'test_errno': err,
                                      'helper_return': struct.unpack_from('<i', data, 4)[0]})
            if err:
                result['error'] = f'BPF_PROG_TEST_RUN errno={err}'
                return result
        finally:
            os.close(fd)
    result['status'] = classify(result['results'])
    return result


if __name__ == '__main__':
    output = probe()
    print(json.dumps(output, indent=2))
    sys.exit({'supported': 0, 'unsupported': 3, 'unknown': 2}[output['status']])
