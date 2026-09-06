// Unattached SCHED_CLS helper flag probe; static fallback for kind Nodes without Python.
// Linux/amd64 only: no attachment, pinning, or interface changes. See probe-ipv6-checksum.py.
package main

import (
	"encoding/binary"
	"fmt"
	"os"
	"runtime"
	"syscall"
	"unsafe"
)

func ptr(b []byte) uint64           { return uint64(uintptr(unsafe.Pointer(&b[0]))) }
func u32(b []byte, o int, v uint32) { binary.LittleEndian.PutUint32(b[o:], v) }
func u64(b []byte, o int, v uint64) { binary.LittleEndian.PutUint64(b[o:], v) }
func bpf(cmd uintptr, b []byte) (uintptr, syscall.Errno) {
	r, _, e := syscall.Syscall(321, cmd, uintptr(unsafe.Pointer(&b[0])), uintptr(len(b)))
	runtime.KeepAlive(b)
	return r, e
}
func ins(code, reg byte, imm int32) []byte {
	b := make([]byte, 8)
	b[0] = code
	b[1] = reg
	u32(b, 4, uint32(imm))
	return b
}
func main() {
	if runtime.GOOS != "linux" || runtime.GOARCH != "amd64" {
		fmt.Println("unknown: probe requires linux/amd64")
		os.Exit(2)
	}
	for _, flag := range []int32{0, 16, 144} {
		prog := []byte{}
		for _, i := range [][]byte{ins(0xb7, 2, 70), ins(0xb7, 3, 0), ins(0xb7, 4, 0), ins(0xb7, 5, flag), ins(0x85, 0, 11), ins(0x95, 0, 0)} {
			prog = append(prog, i...)
		}
		license := []byte("GPL\x00")
		log := make([]byte, 65536)
		a := make([]byte, 120)
		u32(a, 0, 3)
		u32(a, 4, uint32(len(prog)/8))
		u64(a, 8, ptr(prog))
		u64(a, 16, ptr(license))
		u32(a, 24, 1)
		u32(a, 28, uint32(len(log)))
		u64(a, 32, ptr(log))
		fd, e := bpf(5, a)
		runtime.KeepAlive(prog)
		runtime.KeepAlive(license)
		runtime.KeepAlive(log)
		if e != 0 {
			fmt.Printf("load flags=%d error=%v log=%s\n", flag, e, log)
			os.Exit(1)
		}
		packet := make([]byte, 74)
		packet[12] = 0x86
		packet[13] = 0xdd
		packet[14] = 0x60
		packet[19] = 20
		packet[20] = 6
		packet[21] = 64
		packet[29] = 1
		packet[45] = 2
		packet[66] = 0x50
		packet[67] = 2
		out := make([]byte, 256)
		t := make([]byte, 80)
		u32(t, 0, uint32(fd))
		u32(t, 8, uint32(len(packet)))
		u32(t, 12, uint32(len(out)))
		u64(t, 16, ptr(packet))
		u64(t, 24, ptr(out))
		u32(t, 32, 1)
		_, e = bpf(10, t)
		runtime.KeepAlive(packet)
		runtime.KeepAlive(out)
		syscall.Close(int(fd))
		fmt.Printf("flags=%d test_syscall_errno=%d helper_return=%d\n", flag, e, int32(binary.LittleEndian.Uint32(t[4:8])))
		if e != 0 {
			os.Exit(2)
		}
	}
}
