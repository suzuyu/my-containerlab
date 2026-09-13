// Lab-only UDP echo diagnostic. Build with: CGO_ENABLED=0 go build main.go
// Echo servers must return each datagram unchanged. No server changes are required.
package main

import (
	"bytes"
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"sort"
	"strconv"
	"sync"
	"time"
)

var magic = []byte("K02UDP01")

type packet struct {
	Seq        uint64  `json:"seq"`
	SentNS     int64   `json:"sent_ns"`
	ReceivedNS int64   `json:"received_ns,omitempty"`
	RTTMS      float64 `json:"rtt_ms,omitempty"`
	Late       bool    `json:"late,omitempty"`
}
type received struct {
	data []byte
	at   time.Time
}
type report struct {
	Network     string             `json:"network"`
	Destination string             `json:"destination"`
	Local       string             `json:"local"`
	RunID       string             `json:"run_id"`
	Payload     int                `json:"payload"`
	TargetMbps  float64            `json:"target_mbps"`
	Duration    float64            `json:"send_window_seconds"`
	Drain       float64            `json:"drain_seconds"`
	SendStartNS int64              `json:"send_start_ns"`
	CutoffNS    int64              `json:"legacy_cutoff_ns"`
	EndNS       int64              `json:"observation_end_ns"`
	Sent        int                `json:"sent"`
	OnTime      int                `json:"received_by_legacy_cutoff"`
	Late        int                `json:"received_late"`
	Missing     int                `json:"missing_at_observation_end"`
	Duplicates  int                `json:"duplicates"`
	Invalid     int                `json:"invalid"`
	Reordered   int                `json:"reordered"`
	ActualMbps  float64            `json:"actual_send_mbps"`
	RTT         map[string]float64 `json:"rtt_ms"`
	Errors      []string           `json:"errors"`
	Packets     []packet           `json:"packets"`
}

func decode(data, token []byte, size int) (uint64, int64, bool) {
	if len(data) != size || size < 32 || !bytes.Equal(data[:8], magic) || !bytes.Equal(data[8:16], token) {
		return 0, 0, false
	}
	for _, b := range data[32:] {
		if b != 0x5a {
			return 0, 0, false
		}
	}
	return binary.BigEndian.Uint64(data[16:24]), int64(binary.BigEndian.Uint64(data[24:32])), true
}
func summarize(r *report, samples []received, token []byte, sentTimes map[uint64]time.Time) {
	index := map[uint64]int{}
	for i, p := range r.Packets {
		index[p.Seq] = i
	}
	var high uint64
	haveHigh := false
	rtts := []float64{}
	for _, s := range samples {
		seq, stamp, ok := decode(s.data, token, r.Payload)
		i, known := index[seq]
		if !ok || !known || stamp != r.Packets[i].SentNS {
			r.Invalid++
			continue
		}
		p := &r.Packets[i]
		if p.ReceivedNS != 0 {
			r.Duplicates++
			continue
		}
		p.ReceivedNS = s.at.UnixNano()
		p.RTTMS = float64(s.at.Sub(sentTimes[seq])) / float64(time.Millisecond)
		p.Late = p.ReceivedNS > r.CutoffNS
		if p.Late {
			r.Late++
		} else {
			r.OnTime++
		}
		if haveHigh && seq < high {
			r.Reordered++
		}
		if !haveHigh || seq > high {
			high = seq
			haveHigh = true
		}
		rtts = append(rtts, p.RTTMS)
	}
	r.Sent = len(r.Packets)
	r.Missing = r.Sent - r.OnTime - r.Late
	r.ActualMbps = float64(r.Sent*r.Payload*8) / r.Duration / 1e6
	r.RTT = map[string]float64{}
	sort.Float64s(rtts)
	if len(rtts) > 0 {
		for name, q := range map[string]float64{"min": 0, "p50": .5, "p95": .95, "p99": .99, "max": 1} {
			r.RTT[name] = rtts[int(float64(len(rtts)-1)*q)]
		}
	}
}
func main() {
	if len(os.Args) != 7 {
		fmt.Fprintln(os.Stderr, "usage: probe udp4|udp6 HOST:PORT SECONDS PAYLOAD MBPS DRAIN_SECONDS")
		os.Exit(2)
	}
	network, dest := os.Args[1], os.Args[2]
	seconds, e1 := strconv.ParseFloat(os.Args[3], 64)
	size, e2 := strconv.Atoi(os.Args[4])
	rate, e3 := strconv.ParseFloat(os.Args[5], 64)
	drain, e4 := strconv.ParseFloat(os.Args[6], 64)
	if (network != "udp4" && network != "udp6") || e1 != nil || e2 != nil || e3 != nil || e4 != nil || !(seconds >= 1 && seconds <= 30) || size < 32 || size > 8972 || !(rate > 0 && rate <= 20) || !(drain >= .5 && drain <= 10) {
		fmt.Fprintln(os.Stderr, "invalid arguments")
		os.Exit(2)
	}
	c, err := net.DialTimeout(network, dest, 3*time.Second)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer c.Close()
	token := make([]byte, 8)
	if _, err = rand.Read(token); err != nil {
		panic(err)
	}
	start := time.Now()
	end := start.Add(time.Duration(seconds * float64(time.Second)))
	cutoff := end.Add(500 * time.Millisecond)
	final := end.Add(time.Duration(drain * float64(time.Second)))
	r := report{Network: network, Destination: dest, Local: c.LocalAddr().String(), RunID: fmt.Sprintf("%x", token), Payload: size, TargetMbps: rate, Duration: seconds, Drain: drain, SendStartNS: start.UnixNano(), CutoffNS: cutoff.UnixNano(), EndNS: final.UnixNano(), Errors: []string{}}
	var wg sync.WaitGroup
	wg.Add(1)
	samples := []received{}
	go func() {
		defer wg.Done()
		buf := make([]byte, 65535)
		c.SetReadDeadline(final)
		for {
			n, e := c.Read(buf)
			at := time.Now()
			if e != nil {
				if ne, ok := e.(net.Error); !ok || !ne.Timeout() {
					r.Errors = append(r.Errors, "read: "+e.Error())
				}
				return
			}
			samples = append(samples, received{append([]byte(nil), buf[:n]...), at})
		}
	}()
	sentTimes := map[uint64]time.Time{}
	sendErrors := []string{}
	interval := time.Duration(float64(size*8) / rate / 1e6 * float64(time.Second))
	next := start
	for seq := uint64(0); time.Now().Before(end); seq++ {
		data := bytes.Repeat([]byte{0x5a}, size)
		copy(data, magic)
		copy(data[8:], token)
		binary.BigEndian.PutUint64(data[16:], seq)
		t := time.Now()
		binary.BigEndian.PutUint64(data[24:], uint64(t.UnixNano()))
		c.SetWriteDeadline(end)
		n, e := c.Write(data)
		if e != nil || n != size {
			sendErrors = append(sendErrors, fmt.Sprintf("write: n=%d err=%v", n, e))
			break
		}
		sentTimes[seq] = t
		r.Packets = append(r.Packets, packet{Seq: seq, SentNS: t.UnixNano()})
		// Do not emit catch-up bursts when the scheduler falls behind.
		next = next.Add(interval)
		if next.Before(time.Now()) {
			next = time.Now().Add(interval)
		}
		if next.After(end) {
			next = end
		}
		time.Sleep(time.Until(next))
	}
	wg.Wait()
	r.Errors = append(r.Errors, sendErrors...)
	summarize(&r, samples, token, sentTimes)
	json.NewEncoder(os.Stdout).Encode(r)
	if len(r.Errors) > 0 {
		os.Exit(1)
	}
}
