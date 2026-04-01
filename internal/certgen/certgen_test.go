package certgen

import (
	"archive/zip"
	"bytes"
	"crypto/ecdsa"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"testing"

	"software.sslmate.com/src/go-pkcs12"
)

func TestGenerateZIP_RSA2048(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "test.example.com",
		Organization: "Test Org",
		Country:      "US",
		ValidityDays: 365,
		KeyType:      RSA2048,
		OutputFormat: FormatZIP,
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	if result.ContentType != "application/zip" {
		t.Errorf("expected content type application/zip, got %s", result.ContentType)
	}
	if result.Filename != "test.example.com.zip" {
		t.Errorf("expected filename test.example.com.zip, got %s", result.Filename)
	}

	cert, key := extractZIP(t, result.Data)
	verifyCert(t, cert, "test.example.com")
	if _, ok := key.(*rsa.PrivateKey); !ok {
		t.Errorf("expected RSA private key, got %T", key)
	}
}

func TestGenerateZIP_RSA4096(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "big.example.com",
		ValidityDays: 30,
		KeyType:      RSA4096,
		OutputFormat: FormatZIP,
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	_, key := extractZIP(t, result.Data)
	rsaKey, ok := key.(*rsa.PrivateKey)
	if !ok {
		t.Fatalf("expected RSA private key, got %T", key)
	}
	if rsaKey.N.BitLen() < 4096 {
		t.Errorf("expected 4096-bit key, got %d", rsaKey.N.BitLen())
	}
}

func TestGenerateZIP_ECDSA(t *testing.T) {
	for _, kt := range []KeyType{ECDSAP256, ECDSAP384} {
		t.Run(string(kt), func(t *testing.T) {
			result, err := Generate(Request{
				CommonName:   "ec.example.com",
				ValidityDays: 365,
				KeyType:      kt,
				OutputFormat: FormatZIP,
			})
			if err != nil {
				t.Fatalf("Generate failed: %v", err)
			}

			_, key := extractZIP(t, result.Data)
			if _, ok := key.(*ecdsa.PrivateKey); !ok {
				t.Errorf("expected ECDSA private key, got %T", key)
			}
		})
	}
}

func TestGeneratePFX(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "pfx.example.com",
		Organization: "PFX Org",
		ValidityDays: 365,
		KeyType:      RSA2048,
		OutputFormat: FormatPFX,
		PFXPassword:  "testpass",
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	if result.ContentType != "application/x-pkcs12" {
		t.Errorf("expected content type application/x-pkcs12, got %s", result.ContentType)
	}

	privKey, cert, _, err := pkcs12.DecodeChain(result.Data, "testpass")
	if err != nil {
		t.Fatalf("failed to decode PFX: %v", err)
	}
	if cert.Subject.CommonName != "pfx.example.com" {
		t.Errorf("expected CN pfx.example.com, got %s", cert.Subject.CommonName)
	}
	if _, ok := privKey.(*rsa.PrivateKey); !ok {
		t.Errorf("expected RSA private key from PFX, got %T", privKey)
	}
}

func TestGenerateIPAddress(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "192.168.1.1",
		ValidityDays: 30,
		KeyType:      RSA2048,
		OutputFormat: FormatZIP,
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	cert, _ := extractZIP(t, result.Data)
	if len(cert.IPAddresses) != 1 || cert.IPAddresses[0].String() != "192.168.1.1" {
		t.Errorf("expected IP SAN 192.168.1.1, got %v", cert.IPAddresses)
	}
	if len(cert.DNSNames) != 0 {
		t.Errorf("expected no DNS SANs for IP CN, got %v", cert.DNSNames)
	}
}

func TestGenerateDNSSAN(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "example.com",
		ValidityDays: 30,
		KeyType:      RSA2048,
		OutputFormat: FormatZIP,
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	cert, _ := extractZIP(t, result.Data)
	if len(cert.DNSNames) != 1 || cert.DNSNames[0] != "example.com" {
		t.Errorf("expected DNS SAN example.com, got %v", cert.DNSNames)
	}
}

func TestGenerateWithSANs(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "example.com",
		ValidityDays: 30,
		KeyType:      RSA2048,
		OutputFormat: FormatZIP,
		SANs:         []string{"www.example.com", "api.example.com", "10.0.0.1"},
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	cert, _ := extractZIP(t, result.Data)

	// CN should be included as DNS SAN automatically
	expectedDNS := []string{"example.com", "www.example.com", "api.example.com"}
	if len(cert.DNSNames) != len(expectedDNS) {
		t.Fatalf("expected %d DNS SANs, got %d: %v", len(expectedDNS), len(cert.DNSNames), cert.DNSNames)
	}
	for i, want := range expectedDNS {
		if cert.DNSNames[i] != want {
			t.Errorf("DNS SAN[%d] = %q, want %q", i, cert.DNSNames[i], want)
		}
	}

	// IP SAN
	if len(cert.IPAddresses) != 1 || cert.IPAddresses[0].String() != "10.0.0.1" {
		t.Errorf("expected IP SAN 10.0.0.1, got %v", cert.IPAddresses)
	}
}

func TestGenerateWithSANs_DuplicateCN(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "example.com",
		ValidityDays: 30,
		KeyType:      RSA2048,
		OutputFormat: FormatZIP,
		SANs:         []string{"example.com", "other.com"}, // CN duplicated in SANs
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	cert, _ := extractZIP(t, result.Data)
	// CN should not be duplicated
	if len(cert.DNSNames) != 2 {
		t.Errorf("expected 2 DNS SANs (deduped CN), got %d: %v", len(cert.DNSNames), cert.DNSNames)
	}
}

func TestGenerateWithSANs_Wildcard(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "example.com",
		ValidityDays: 30,
		KeyType:      RSA2048,
		OutputFormat: FormatZIP,
		SANs:         []string{"*.example.com"},
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	cert, _ := extractZIP(t, result.Data)
	found := false
	for _, dns := range cert.DNSNames {
		if dns == "*.example.com" {
			found = true
		}
	}
	if !found {
		t.Errorf("expected wildcard SAN *.example.com in %v", cert.DNSNames)
	}
}

func TestGenerateWithSANs_IPOnly(t *testing.T) {
	result, err := Generate(Request{
		CommonName:   "10.0.0.1",
		ValidityDays: 30,
		KeyType:      RSA2048,
		OutputFormat: FormatZIP,
		SANs:         []string{"10.0.0.2", "192.168.1.1"},
	})
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	cert, _ := extractZIP(t, result.Data)
	if len(cert.DNSNames) != 0 {
		t.Errorf("expected no DNS SANs, got %v", cert.DNSNames)
	}
	if len(cert.IPAddresses) != 3 {
		t.Errorf("expected 3 IP SANs, got %d: %v", len(cert.IPAddresses), cert.IPAddresses)
	}
}

func TestSanitizeFilename(t *testing.T) {
	tests := []struct {
		input, expected string
	}{
		{"example.com", "example.com"},
		{"*.example.com", "_.example.com"},
		{"my server/host", "my_server_host"},
		{"", "certificate"},
		{"a/b\\c:d", "a_b_c_d"},
	}
	for _, tt := range tests {
		got := sanitizeFilename(tt.input)
		if got != tt.expected {
			t.Errorf("sanitizeFilename(%q) = %q, want %q", tt.input, got, tt.expected)
		}
	}
}

func TestUnsupportedKeyType(t *testing.T) {
	_, err := Generate(Request{
		CommonName:   "test.com",
		ValidityDays: 30,
		KeyType:      "unknown",
		OutputFormat: FormatZIP,
	})
	if err == nil {
		t.Error("expected error for unsupported key type")
	}
}

// helpers

func extractZIP(t *testing.T, data []byte) (*x509.Certificate, interface{}) {
	t.Helper()
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		t.Fatalf("failed to open zip: %v", err)
	}

	var certPEM, keyPEM []byte
	for _, f := range zr.File {
		rc, err := f.Open()
		if err != nil {
			t.Fatalf("failed to open zip entry %s: %v", f.Name, err)
		}
		var buf bytes.Buffer
		buf.ReadFrom(rc)
		rc.Close()
		switch f.Name {
		case "certificate.pem":
			certPEM = buf.Bytes()
		case "private-key.pem":
			keyPEM = buf.Bytes()
		}
	}

	if certPEM == nil {
		t.Fatal("certificate.pem not found in zip")
	}
	if keyPEM == nil {
		t.Fatal("private-key.pem not found in zip")
	}

	block, _ := pem.Decode(certPEM)
	if block == nil {
		t.Fatal("failed to decode certificate PEM")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		t.Fatalf("failed to parse certificate: %v", err)
	}

	block, _ = pem.Decode(keyPEM)
	if block == nil {
		t.Fatal("failed to decode private key PEM")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		t.Fatalf("failed to parse private key: %v", err)
	}

	return cert, key
}

func verifyCert(t *testing.T, cert *x509.Certificate, expectedCN string) {
	t.Helper()
	if cert.Subject.CommonName != expectedCN {
		t.Errorf("expected CN %s, got %s", expectedCN, cert.Subject.CommonName)
	}
	if !cert.IsCA {
		t.Error("expected cert to be CA")
	}
	if cert.KeyUsage&x509.KeyUsageDigitalSignature == 0 {
		t.Error("expected KeyUsageDigitalSignature")
	}
	if cert.KeyUsage&x509.KeyUsageKeyEncipherment == 0 {
		t.Error("expected KeyUsageKeyEncipherment")
	}
}
