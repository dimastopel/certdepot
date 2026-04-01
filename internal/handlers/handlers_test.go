package handlers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/dimastopel/certdepot/internal/counter"
)

func setupHandlers(t *testing.T) *Handlers {
	t.Helper()
	dir := t.TempDir()
	c, err := counter.New(filepath.Join(dir, "counter.txt"))
	if err != nil {
		t.Fatalf("failed to create counter: %v", err)
	}
	return New(c)
}

func TestGenerateHandler_ValidZIP(t *testing.T) {
	h := setupHandlers(t)

	body := `{"commonName":"test.com","validityDays":30,"keyType":"rsa2048","outputFormat":"zip"}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	if w.Header().Get("Content-Type") != "application/zip" {
		t.Errorf("expected content type application/zip, got %s", w.Header().Get("Content-Type"))
	}
	if w.Header().Get("Content-Disposition") != `attachment; filename="test.com.zip"` {
		t.Errorf("unexpected Content-Disposition: %s", w.Header().Get("Content-Disposition"))
	}
}

func TestGenerateHandler_MissingCommonName(t *testing.T) {
	h := setupHandlers(t)

	body := `{"validityDays":30}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestGenerateHandler_InvalidCountry(t *testing.T) {
	h := setupHandlers(t)

	body := `{"commonName":"test.com","country":"usa"}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestGenerateHandler_PFXRequiresPassword(t *testing.T) {
	h := setupHandlers(t)

	body := `{"commonName":"test.com","outputFormat":"pfx","pfxPassword":"ab"}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestGenerateHandler_InvalidKeyType(t *testing.T) {
	h := setupHandlers(t)

	body := `{"commonName":"test.com","keyType":"dsa1024"}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestGenerateHandler_ValidityTooHigh(t *testing.T) {
	h := setupHandlers(t)

	body := `{"commonName":"test.com","validityDays":5000}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestGenerateHandler_DefaultValues(t *testing.T) {
	h := setupHandlers(t)

	// Only commonName provided - should use defaults for everything else
	body := `{"commonName":"defaults.com"}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGenerateHandler_ControlCharsStripped(t *testing.T) {
	h := setupHandlers(t)

	body := `{"commonName":"test\u0000.com","organization":"Org\u0001Name"}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200 (control chars stripped), got %d: %s", w.Code, w.Body.String())
	}
}

func TestGenerateHandler_WithSANs(t *testing.T) {
	h := setupHandlers(t)

	body := `{"commonName":"test.com","sans":["www.test.com","api.test.com","10.0.0.1"]}`
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGenerateHandler_TooManySANs(t *testing.T) {
	h := setupHandlers(t)

	// Build a request with 51 SANs
	sans := make([]string, 51)
	for i := range sans {
		sans[i] = fmt.Sprintf("host%d.example.com", i)
	}
	sansJSON, _ := json.Marshal(sans)
	body := fmt.Sprintf(`{"commonName":"test.com","sans":%s}`, sansJSON)
	req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	h.Generate(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for >50 SANs, got %d", w.Code)
	}
}

func TestStatsHandler(t *testing.T) {
	h := setupHandlers(t)

	req := httptest.NewRequest("GET", "/api/stats", nil)
	w := httptest.NewRecorder()

	h.Stats(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	var stats map[string]int64
	json.NewDecoder(w.Body).Decode(&stats)
	if stats["certificatesGenerated"] != 0 {
		t.Errorf("expected 0 certificates, got %d", stats["certificatesGenerated"])
	}
}

func TestCounterIncrements(t *testing.T) {
	dir := t.TempDir()
	c, _ := counter.New(filepath.Join(dir, "counter.txt"))
	h := New(c)

	body := `{"commonName":"count.com"}`
	for i := 0; i < 3; i++ {
		req := httptest.NewRequest("POST", "/api/generate", bytes.NewBufferString(body))
		w := httptest.NewRecorder()
		h.Generate(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("request %d: expected 200, got %d", i, w.Code)
		}
	}

	if c.Value() != 3 {
		t.Errorf("expected counter 3, got %d", c.Value())
	}

	// Verify persisted
	data, err := os.ReadFile(filepath.Join(dir, "counter.txt"))
	if err != nil {
		t.Fatalf("failed to read counter file: %v", err)
	}
	if string(bytes.TrimSpace(data)) != "3" {
		t.Errorf("expected persisted value 3, got %s", data)
	}
}

func TestHealthHandler(t *testing.T) {
	h := setupHandlers(t)

	req := httptest.NewRequest("GET", "/api/health", nil)
	w := httptest.NewRecorder()

	h.Health(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
}

func TestSanitizeString(t *testing.T) {
	tests := []struct {
		input    string
		maxLen   int
		expected string
	}{
		{"  hello  ", 64, "hello"},
		{"ab\x00cd", 64, "abcd"},
		{"ab\x01cd", 64, "abcd"},
		{"ab\tcd", 64, "ab cd"},
		{"long string", 4, "long"},
		{"normal", 64, "normal"},
	}
	for _, tt := range tests {
		got := sanitizeString(tt.input, tt.maxLen)
		if got != tt.expected {
			t.Errorf("sanitizeString(%q, %d) = %q, want %q", tt.input, tt.maxLen, got, tt.expected)
		}
	}
}
