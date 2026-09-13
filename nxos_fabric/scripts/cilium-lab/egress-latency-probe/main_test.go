package main

import (
	"bytes"
	"encoding/binary"
	"testing"
	"time"
)

func TestAccounting(t *testing.T) {
	token := []byte("12345678")
	start := time.Unix(100, 0)
	times := map[uint64]time.Time{0: start, 1: start, 2: start}
	dat := func(seq uint64) []byte {
		b := bytes.Repeat([]byte{0x5a}, 64)
		copy(b, magic)
		copy(b[8:], token)
		binary.BigEndian.PutUint64(b[16:], seq)
		binary.BigEndian.PutUint64(b[24:], uint64(start.UnixNano()))
		return b
	}
	r := report{Payload: 64, Duration: 1, CutoffNS: start.Add(time.Second).UnixNano(), Packets: []packet{{Seq: 0, SentNS: start.UnixNano()}, {Seq: 1, SentNS: start.UnixNano()}, {Seq: 2, SentNS: start.UnixNano()}}}
	bad := dat(2)
	bad[40] = 0
	samples := []received{{dat(1), start.Add(time.Millisecond)}, {dat(1), start.Add(2 * time.Millisecond)}, {dat(0), start.Add(2 * time.Second)}, {bad, start.Add(3 * time.Second)}, {dat(9), start.Add(4 * time.Second)}}
	summarize(&r, samples, token, times)
	if r.OnTime != 1 || r.Late != 1 || r.Missing != 1 || r.Duplicates != 1 || r.Invalid != 2 || r.Reordered != 1 {
		t.Fatalf("accounting: %+v", r)
	}
	if r.RTT["max"] != 2000 {
		t.Fatalf("RTT: %v", r.RTT)
	}
}
func TestRejectForeignAndTruncated(t *testing.T) {
	token := []byte("12345678")
	b := bytes.Repeat([]byte{0x5a}, 64)
	copy(b, magic)
	copy(b[8:], token)
	if _, _, ok := decode(b, token, 64); !ok {
		t.Fatal("valid rejected")
	}
	if _, _, ok := decode(b[:16], token, 64); ok {
		t.Fatal("short accepted")
	}
	if _, _, ok := decode(b, []byte("87654321"), 64); ok {
		t.Fatal("foreign accepted")
	}
}
