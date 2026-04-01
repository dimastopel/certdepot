package main

import (
	"embed"
	"io/fs"
	"log"
	"net"
	"net/http"
	"os"
	"sync"
	"time"

	"golang.org/x/time/rate"

	"github.com/dimastopel/certdepot/internal/counter"
	"github.com/dimastopel/certdepot/internal/handlers"
)

//go:embed static/*
var staticFiles embed.FS

func main() {
	addr := os.Getenv("CERTDEPOT_ADDR")
	if addr == "" {
		addr = "127.0.0.1:8234"
	}

	dataDir := os.Getenv("CERTDEPOT_DATA_DIR")
	if dataDir == "" {
		dataDir = "data"
	}

	cnt, err := counter.New(dataDir + "/counter.txt")
	if err != nil {
		log.Fatalf("Failed to initialize counter: %v", err)
	}

	h := handlers.New(cnt)

	mux := http.NewServeMux()

	// API routes
	mux.HandleFunc("POST /api/generate", h.Generate)
	mux.HandleFunc("GET /api/stats", h.Stats)
	mux.HandleFunc("GET /api/health", h.Health)

	// Static files
	staticFS, err := fs.Sub(staticFiles, "static")
	if err != nil {
		log.Fatalf("Failed to create static sub-filesystem: %v", err)
	}
	fileServer := http.FileServer(http.FS(staticFS))
	mux.Handle("GET /static/", http.StripPrefix("/static/", fileServer))

	// Serve verification and SEO files at root
	mux.HandleFunc("GET /robots.txt", func(w http.ResponseWriter, r *http.Request) {
		data, _ := staticFiles.ReadFile("static/robots.txt")
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write(data)
	})
	mux.HandleFunc("GET /google7bac6a38513c9ab9.html", func(w http.ResponseWriter, r *http.Request) {
		data, _ := staticFiles.ReadFile("static/google7bac6a38513c9ab9.html")
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(data)
	})
	mux.HandleFunc("GET /sitemap.xml", func(w http.ResponseWriter, r *http.Request) {
		data, _ := staticFiles.ReadFile("static/sitemap.xml")
		w.Header().Set("Content-Type", "application/xml; charset=utf-8")
		w.Write(data)
	})

	// Serve index.html at root
	mux.HandleFunc("GET /", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		data, err := staticFiles.ReadFile("static/index.html")
		if err != nil {
			http.Error(w, "Not Found", http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(data)
	})

	// Apply middleware
	handler := securityHeaders(rateLimiter(mux))

	log.Printf("Starting cert-depot on %s", addr)
	log.Printf("Counter at %d certificates", cnt.Value())

	server := &http.Server{
		Addr:         addr,
		Handler:      handler,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

// Rate limiter: 10 requests per minute per IP on /api/generate, generous for other endpoints
type ipLimiter struct {
	mu       sync.Mutex
	limiters map[string]*rate.Limiter
}

func newIPLimiter() *ipLimiter {
	return &ipLimiter{limiters: make(map[string]*rate.Limiter)}
}

func (l *ipLimiter) getLimiter(ip string) *rate.Limiter {
	l.mu.Lock()
	defer l.mu.Unlock()
	limiter, exists := l.limiters[ip]
	if !exists {
		// 10 requests per minute, burst of 3
		limiter = rate.NewLimiter(rate.Every(6*time.Second), 3)
		l.limiters[ip] = limiter
	}
	return limiter
}

var generateLimiter = newIPLimiter()

func rateLimiter(next http.Handler) http.Handler {
	// Periodically clean up old entries
	go func() {
		for {
			time.Sleep(5 * time.Minute)
			generateLimiter.mu.Lock()
			generateLimiter.limiters = make(map[string]*rate.Limiter)
			generateLimiter.mu.Unlock()
		}
	}()

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && r.URL.Path == "/api/generate" {
			ip := extractIP(r)
			limiter := generateLimiter.getLimiter(ip)
			if !limiter.Allow() {
				w.Header().Set("Content-Type", "application/json")
				w.Header().Set("Retry-After", "6")
				w.WriteHeader(http.StatusTooManyRequests)
				w.Write([]byte(`{"error":"Rate limit exceeded. Please wait before generating another certificate."}`))
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func extractIP(r *http.Request) string {
	// Trust X-Real-IP from nginx
	if ip := r.Header.Get("X-Real-IP"); ip != "" {
		return ip
	}
	if ip := r.Header.Get("X-Forwarded-For"); ip != "" {
		return ip
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "strict-origin-when-cross-origin")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; img-src 'self' data:; font-src 'self'")
		next.ServeHTTP(w, r)
	})
}
