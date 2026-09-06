// Linux-only lab probe. Build this file directly with CGO_ENABLED=0 go build.
// Ports: HTTP 19090, TCP echo 19091, UDP echo 19092/19093.
// boundary uses total IP length (IPv4 header 20 / IPv6 header 40, UDP 8).
package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

func out(v any) { b, _ := json.Marshal(v); fmt.Println(string(b)) }
func number(i int) int {
	n, e := strconv.Atoi(os.Args[i])
	if e != nil {
		panic(e)
	}
	return n
}

var mu sync.Mutex
var counts = map[string]int64{}
var peers = map[string]map[string]bool{}

func record(kind, peer string, n int) {
	mu.Lock()
	defer mu.Unlock()
	counts[kind] += int64(n)
	if peers[kind] == nil {
		peers[kind] = map[string]bool{}
	}
	peers[kind][peer] = true
}
func server() {
	duration := number(2)
	if duration < 1 || duration > 3600 {
		panic("server duration must be 1..3600 seconds")
	}
	end := time.Duration(duration) * time.Second
	for _, port := range []int{19092, 19093} {
		p := port
		go func() {
			c, e := net.ListenPacket("udp", fmt.Sprintf(":%d", p))
			if e != nil {
				panic(e)
			}
			defer c.Close()
			buf := make([]byte, 9000)
			for {
				n, a, e := c.ReadFrom(buf)
				if e != nil {
					return
				}
				record(fmt.Sprint(p), a.String(), n)
				c.WriteTo(buf[:n], a)
			}
		}()
	}
	go func() {
		l, e := net.Listen("tcp", ":19091")
		if e != nil {
			panic(e)
		}
		for {
			c, e := l.Accept()
			if e != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				record("tcp", c.RemoteAddr().String(), 1)
				n, e := io.Copy(c, c)
				out(map[string]any{"event": "tcp_end", "remote": c.RemoteAddr().String(), "bytes": n, "error": fmt.Sprint(e), "time": time.Now().UTC()})
			}(c)
		}
	}()
	mux := http.NewServeMux()
	mux.HandleFunc("/source", func(w http.ResponseWriter, r *http.Request) {
		ip, _, _ := net.SplitHostPort(r.RemoteAddr)
		id := r.Header.Get("X-Lab-Test-ID")
		out(map[string]any{"event": "http", "remote": ip, "id": id, "time": time.Now().UTC()})
		w.Header().Set("Content-Type", "text/plain")
		fmt.Fprintf(w, "remote=%s test_id=%s\n", ip, id)
	})
	mux.HandleFunc("/stats", func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		ips := map[string]map[string]int{}
		for k, ps := range peers {
			ips[k] = map[string]int{}
			for peer := range ps {
				ip, _, _ := net.SplitHostPort(peer)
				ips[k][ip]++
			}
		}
		json.NewEncoder(w).Encode(map[string]any{"bytes": counts, "unique_peers_by_ip": ips, "time": time.Now().UTC()})
	})
	mux.HandleFunc("/stream", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		f := w.(http.Flusher)
		out(map[string]any{"event": "stream_start", "id": r.URL.Query().Get("id"), "remote": r.RemoteAddr, "time": time.Now().UTC()})
		for i := 0; i < 120; i++ {
			select {
			case <-r.Context().Done():
				return
			default:
			}
			_, e := fmt.Fprintf(w, "seq=%d remote=%s time=%s\n", i, r.RemoteAddr, time.Now().UTC().Format(time.RFC3339Nano))
			if e != nil {
				return
			}
			f.Flush()
			time.Sleep(time.Second)
		}
	})
	srv := &http.Server{Addr: ":19090", Handler: mux}
	go func() {
		e := srv.ListenAndServe()
		if e != nil && e != http.ErrServerClosed {
			panic(e)
		}
	}()
	out(map[string]any{"event": "ready", "pid": os.Getpid(), "time": time.Now().UTC()})
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT)
	select {
	case <-sig:
	case <-time.After(end):
	}
	srv.Close()
}
func stream() {
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(number(3))*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, "GET", os.Args[2], nil)
	client := &http.Client{Transport: &http.Transport{Proxy: nil}}
	r, e := client.Do(req)
	if e != nil {
		out(map[string]any{"event": "error", "error": e.Error()})
		os.Exit(1)
	}
	defer r.Body.Close()
	sc := bufio.NewScanner(r.Body)
	n := 0
	for sc.Scan() {
		out(map[string]any{"event": "line", "line": sc.Text(), "time": time.Now().UTC()})
		n++
	}
	out(map[string]any{"event": "end", "lines": n, "error": fmt.Sprint(sc.Err()), "time": time.Now().UTC()})
}
func load() {
	network, addr := os.Args[2], os.Args[3]
	seconds, parallel, size := number(4), number(5), number(6)
	mbps, err := strconv.ParseFloat(os.Args[7], 64)
	if err != nil || mbps <= 0 {
		panic("invalid rate")
	}
	deadline := time.Now().Add(time.Duration(seconds) * time.Second)
	start := time.Now()
	var sent, received, errs atomic.Int64
	var wg sync.WaitGroup
	for k := 0; k < parallel; k++ {
		wg.Add(1)
		go func(k int) {
			defer wg.Done()
			dialer := net.Dialer{Timeout: 3 * time.Second}
			if len(os.Args) > 8 && network[:3] == "tcp" {
				mss := number(8)
				dialer.Control = func(network, address string, raw syscall.RawConn) error {
					var se error
					ce := raw.Control(func(fd uintptr) { se = syscall.SetsockoptInt(int(fd), syscall.IPPROTO_TCP, syscall.TCP_MAXSEG, mss) })
					if ce != nil {
						return ce
					}
					return se
				}
			}
			c, e := dialer.Dial(network, addr)
			if e != nil {
				errs.Add(1)
				return
			}
			defer c.Close()
			data := bytes.Repeat([]byte{byte(k + 1)}, size)
			buf := make([]byte, size)
			interval := time.Duration(float64(size*8*parallel) / float64(mbps*1000000) * 1e9)
			next := time.Now()
			if network[:3] == "udp" {
				var rd sync.WaitGroup
				rd.Add(1)
				go func() {
					defer rd.Done()
					for {
						c.SetReadDeadline(deadline.Add(500 * time.Millisecond))
						n, e := c.Read(buf)
						if e != nil {
							return
						}
						if n == size {
							received.Add(int64(n))
						} else {
							errs.Add(1)
						}
					}
				}()
				for time.Now().Before(deadline) {
					n, e := c.Write(data)
					if e != nil {
						errs.Add(1)
						break
					}
					sent.Add(int64(n))
					next = next.Add(interval)
					if wait := time.Until(next); wait > 0 {
						time.Sleep(wait)
					}
				}
				rd.Wait()
			} else {
				for time.Now().Before(deadline) {
					c.SetDeadline(time.Now().Add(3 * time.Second))
					n, e := c.Write(data)
					if e != nil {
						errs.Add(1)
						break
					}
					sent.Add(int64(n))
					n, e = io.ReadFull(c, buf)
					if e != nil {
						errs.Add(1)
						break
					}
					received.Add(int64(n))
					if !bytes.Equal(data, buf) {
						errs.Add(1)
					}
					next = next.Add(interval)
					if wait := time.Until(next); wait > 0 {
						time.Sleep(wait)
					}
				}
			}
		}(k)
	}
	wg.Wait()
	duration := time.Since(start).Seconds()
	out(map[string]any{"network": network, "destination": addr, "seconds": duration, "streams": parallel, "payload": size, "rate_limit_mbps": mbps, "sent_bytes": sent.Load(), "received_bytes": received.Load(), "errors": errs.Load(), "receive_mbps": float64(received.Load()*8) / duration / 1e6, "time": time.Now().UTC()})
	if errs.Load() != 0 {
		os.Exit(1)
	}
}
func exhaust() {
	network, addr := os.Args[2], os.Args[3]
	count, hold := number(4), number(5)
	if count > 50000 || hold > 90 {
		panic("limit")
	}
	var lim syscall.Rlimit
	if syscall.Getrlimit(syscall.RLIMIT_NOFILE, &lim) == nil && lim.Cur < 65536 {
		lim.Cur = 65536
		if lim.Cur > lim.Max {
			lim.Cur = lim.Max
		}
		syscall.Setrlimit(syscall.RLIMIT_NOFILE, &lim)
	}
	conns := make([]*net.UDPConn, 0, count)
	var ack, errors atomic.Int64
	start := time.Now()
	done := make(chan struct{})
	var wg sync.WaitGroup
	for i := 0; i < count; i++ {
		ra, e := net.ResolveUDPAddr(network, addr)
		if e != nil {
			panic(e)
		}
		la := &net.UDPAddr{Port: 10000 + i}
		c, e := net.DialUDP(network, la, ra)
		if e != nil {
			errors.Add(1)
			continue
		}
		conns = append(conns, c)
		data := make([]byte, 32)
		binary.BigEndian.PutUint64(data, uint64(i))
		wg.Add(1)
		go func(c *net.UDPConn, data []byte) {
			defer wg.Done()
			seen := false
			buf := make([]byte, 64)
			for {
				c.SetReadDeadline(time.Now().Add(2 * time.Second))
				n, e := c.Read(buf)
				if e == nil && n == 32 && bytes.Equal(data, buf) && !seen {
					ack.Add(1)
					seen = true
				}
				select {
				case <-done:
					return
				default:
				}
			}
		}(c, data)
		c.Write(data)
		if i%128 == 127 {
			time.Sleep(32 * time.Millisecond)
		}
		if (i+1)%4000 == 0 {
			out(map[string]any{"event": "progress", "opened": len(conns), "acked": ack.Load(), "errors": errors.Load(), "time": time.Now().UTC()})
		}
	}
	end := time.Now().Add(time.Duration(hold) * time.Second)
	for time.Now().Before(end) {
		for i, c := range conns {
			b := make([]byte, 32)
			binary.BigEndian.PutUint64(b, uint64(c.LocalAddr().(*net.UDPAddr).Port-10000))
			c.Write(b)
			if i%128 == 127 {
				time.Sleep(16 * time.Millisecond)
			}
		}
		out(map[string]any{"event": "holding", "opened": len(conns), "acked": ack.Load(), "errors": errors.Load(), "time": time.Now().UTC()})
		time.Sleep(time.Second)
	}
	close(done)
	for _, c := range conns {
		c.Close()
	}
	wg.Wait()
	out(map[string]any{"event": "complete", "network": network, "opened": len(conns), "acked": ack.Load(), "unacked": int64(len(conns)) - ack.Load(), "socket_errors": errors.Load(), "seconds": time.Since(start).Seconds(), "time": time.Now().UTC()})
}
func newborn() {
	start := time.Now()
	out(map[string]any{"event": "start", "time": start.UTC()})
	tr := &http.Transport{Proxy: nil, DisableKeepAlives: true, DialContext: (&net.Dialer{Timeout: 400 * time.Millisecond}).DialContext}
	client := &http.Client{Transport: tr, Timeout: 700 * time.Millisecond}
	for i := 0; i < 40; i++ {
		for _, url := range os.Args[2:] {
			t := time.Now()
			req, _ := http.NewRequest("GET", url, nil)
			id := fmt.Sprintf("birth-%d-%d-%d", start.UnixNano(), i, len(url))
			req.Header.Set("X-Lab-Test-ID", id)
			r, e := client.Do(req)
			body := ""
			status := 0
			if e == nil {
				b, _ := io.ReadAll(r.Body)
				r.Body.Close()
				body = string(b)
				status = r.StatusCode
			}
			out(map[string]any{"event": "request", "id": id, "index": i, "url": url, "start": t.UTC(), "elapsed_ms": time.Since(start).Milliseconds(), "status": status, "body": body, "error": fmt.Sprint(e)})
		}
		time.Sleep(100 * time.Millisecond)
	}
}
func boundary() {
	network, addr := os.Args[2], os.Args[3]
	total, count := number(4), number(5)
	overhead := 28
	if network == "udp6" {
		overhead = 48
	}
	size := total - overhead
	if size < 16 || size > 9000 || count > 5 {
		panic("boundary limit")
	}
	dialer := net.Dialer{Timeout: 2 * time.Second}
	dialer.Control = func(network, address string, raw syscall.RawConn) error {
		var se error
		ce := raw.Control(func(fd uintptr) {
			if network == "udp4" {
				se = syscall.SetsockoptInt(int(fd), syscall.IPPROTO_IP, syscall.IP_MTU_DISCOVER, syscall.IP_PMTUDISC_DO)
			} else {
				se = syscall.SetsockoptInt(int(fd), syscall.IPPROTO_IPV6, syscall.IPV6_MTU_DISCOVER, syscall.IP_PMTUDISC_DO)
			}
		})
		if ce != nil {
			return ce
		}
		return se
	}
	c, e := dialer.Dial(network, addr)
	if e != nil {
		out(map[string]any{"error": e.Error(), "total_ip_bytes": total})
		return
	}
	defer c.Close()
	sent, acked := 0, 0
	errors := []string{}
	data := make([]byte, size)
	buf := make([]byte, 10000)
	for i := 0; i < count; i++ {
		binary.BigEndian.PutUint64(data, uint64(time.Now().UnixNano()))
		c.SetDeadline(time.Now().Add(650 * time.Millisecond))
		n, e := c.Write(data)
		if e != nil {
			errors = append(errors, "write: "+e.Error())
			continue
		}
		sent++
		n, e = c.Read(buf)
		if e != nil {
			errors = append(errors, "read: "+e.Error())
		} else if n == size && bytes.Equal(data, buf[:n]) {
			acked++
		} else {
			errors = append(errors, "unexpected echo")
		}
		time.Sleep(150 * time.Millisecond)
	}
	out(map[string]any{"network": network, "destination": addr, "local": c.LocalAddr().String(), "total_ip_bytes": total, "payload": size, "sent": sent, "acked": acked, "errors": errors, "time": time.Now().UTC()})
}
func main() {
	if len(os.Args) < 2 {
		panic("mode")
	}
	switch os.Args[1] {
	case "help":
		fmt.Println("server SECONDS | newborn URL4 URL6 | stream URL SECONDS | load tcp4|tcp6|udp4|udp6 HOST:PORT SECONDS STREAMS PAYLOAD MBPS [MSS] | boundary udp4|udp6 HOST:PORT TOTAL_IP_BYTES COUNT | exhaust udp4|udp6 HOST:PORT COUNT HOLD_SECONDS")
	case "boundary":
		boundary()
	case "newborn":
		newborn()
	case "server":
		server()
	case "stream":
		stream()
	case "load":
		load()
	case "exhaust":
		exhaust()
	default:
		panic("mode")
	}
}
