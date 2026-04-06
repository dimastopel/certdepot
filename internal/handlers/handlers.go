package handlers

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"
	"unicode"

	"github.com/dimastopel/certdepot/internal/certgen"
	"github.com/dimastopel/certdepot/internal/counter"
)

type Handlers struct {
	counter *counter.Counter
	cnLogPath string
}

func New(c *counter.Counter) *Handlers {
	return &Handlers{counter: c, cnLogPath: "data/cn_log.txt"}
}

func NewWithCNLog(c *counter.Counter, cnLogPath string) *Handlers {
	return &Handlers{counter: c, cnLogPath: cnLogPath}
}

type generateRequest struct {
	CommonName   string `json:"commonName"`
	Organization string `json:"organization"`
	OrgUnit      string `json:"orgUnit"`
	Country      string `json:"country"`
	State        string `json:"state"`
	City         string `json:"city"`
	Email        string `json:"email"`
	ValidityDays int    `json:"validityDays"`
	KeyType      string `json:"keyType"`
	OutputFormat string `json:"outputFormat"`
	PFXPassword  string   `json:"pfxPassword"`
	SANs         []string `json:"sans"`
}

type errorResponse struct {
	Error string `json:"error"`
}

var (
	countryRegex = regexp.MustCompile(`^[A-Z]{2}$`)
	emailRegex   = regexp.MustCompile(`^[^\s@]+@[^\s@]+\.[^\s@]+$`)
	validKeyTypes = map[string]certgen.KeyType{
		"rsa2048":   certgen.RSA2048,
		"rsa4096":   certgen.RSA4096,
		"ecdsaP256": certgen.ECDSAP256,
		"ecdsaP384": certgen.ECDSAP384,
	}
	validOutputFormats = map[string]certgen.OutputFormat{
		"zip": certgen.FormatZIP,
		"pfx": certgen.FormatPFX,
	}
)

func (h *Handlers) Generate(w http.ResponseWriter, r *http.Request) {
	// Cap request body size
	r.Body = http.MaxBytesReader(w, r.Body, 10*1024)

	var req generateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "Invalid JSON request body")
		return
	}

	// Sanitize all string fields
	req.CommonName = sanitizeString(req.CommonName, 253)
	req.Organization = sanitizeString(req.Organization, 64)
	req.OrgUnit = sanitizeString(req.OrgUnit, 64)
	req.Country = sanitizeString(req.Country, 2)
	req.State = sanitizeString(req.State, 64)
	req.City = sanitizeString(req.City, 64)
	req.Email = sanitizeString(req.Email, 254)
	req.PFXPassword = sanitizeString(req.PFXPassword, 128)

	// Validate required fields
	if req.CommonName == "" {
		writeError(w, http.StatusBadRequest, "commonName is required")
		return
	}

	// Validate validityDays
	if req.ValidityDays <= 0 {
		req.ValidityDays = 365
	}
	if req.ValidityDays > 3650 {
		writeError(w, http.StatusBadRequest, "validityDays must be 3650 or less")
		return
	}

	// Validate country
	if req.Country != "" && !countryRegex.MatchString(req.Country) {
		writeError(w, http.StatusBadRequest, "country must be a 2-letter uppercase ISO code (e.g., US)")
		return
	}

	// Validate email
	if req.Email != "" && !emailRegex.MatchString(req.Email) {
		writeError(w, http.StatusBadRequest, "invalid email address")
		return
	}

	// Validate keyType
	keyType, ok := validKeyTypes[req.KeyType]
	if !ok {
		if req.KeyType == "" {
			keyType = certgen.RSA2048
		} else {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid keyType: must be one of rsa2048, rsa4096, ecdsaP256, ecdsaP384"))
			return
		}
	}

	// Validate outputFormat
	outputFormat, ok := validOutputFormats[req.OutputFormat]
	if !ok {
		if req.OutputFormat == "" {
			outputFormat = certgen.FormatZIP
		} else {
			writeError(w, http.StatusBadRequest, "invalid outputFormat: must be zip or pfx")
			return
		}
	}

	// Validate PFX password
	if outputFormat == certgen.FormatPFX && len(req.PFXPassword) < 4 {
		writeError(w, http.StatusBadRequest, "pfxPassword must be at least 4 characters when outputFormat is pfx")
		return
	}

	// Validate and sanitize SANs
	if len(req.SANs) > 50 {
		writeError(w, http.StatusBadRequest, "maximum 50 Subject Alternative Names allowed")
		return
	}
	var sanitizedSANs []string
	for _, san := range req.SANs {
		san = sanitizeString(san, 253)
		if san != "" {
			sanitizedSANs = append(sanitizedSANs, san)
		}
	}

	result, err := certgen.Generate(certgen.Request{
		CommonName:   req.CommonName,
		Organization: req.Organization,
		OrgUnit:      req.OrgUnit,
		Country:      req.Country,
		State:        req.State,
		City:         req.City,
		Email:        req.Email,
		ValidityDays: req.ValidityDays,
		KeyType:      keyType,
		OutputFormat: outputFormat,
		PFXPassword:  req.PFXPassword,
		SANs:         sanitizedSANs,
	})
	if err != nil {
		log.Printf("ERROR: certificate generation failed: %v", err)
		writeError(w, http.StatusInternalServerError, "Certificate generation failed")
		return
	}

	h.counter.Increment()
	h.logCN(req.CommonName)

	w.Header().Set("Content-Type", result.ContentType)
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, result.Filename))
	w.Header().Set("Content-Length", fmt.Sprintf("%d", len(result.Data)))
	w.Write(result.Data)
}

func (h *Handlers) Stats(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]int64{
		"certificatesGenerated": h.counter.Value(),
	})
}

func (h *Handlers) Health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"ok"}`))
}

// sanitizeString strips whitespace, rejects control characters and null bytes, and enforces max length.
func sanitizeString(s string, maxLen int) string {
	s = strings.TrimSpace(s)
	// Reject any string containing control characters (0x00-0x1F except tab 0x09)
	var b strings.Builder
	for _, r := range s {
		if r == '\t' {
			b.WriteRune(' ') // normalize tabs to spaces
		} else if unicode.IsControl(r) {
			continue // strip control characters
		} else {
			b.WriteRune(r)
		}
	}
	s = b.String()
	if len(s) > maxLen {
		s = s[:maxLen]
	}
	return s
}

func (h *Handlers) logCN(cn string) {
	f, err := os.OpenFile(h.cnLogPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("WARNING: failed to open CN log: %v", err)
		return
	}
	defer f.Close()
	fmt.Fprintf(f, "%s %s\n", time.Now().UTC().Format("2006-01-02T15:04:05Z"), cn)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(errorResponse{Error: msg})
}
