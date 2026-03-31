package certgen

import (
	"archive/zip"
	"bytes"
	"crypto"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"time"

	"software.sslmate.com/src/go-pkcs12"
)

type KeyType string

const (
	RSA2048   KeyType = "rsa2048"
	RSA4096   KeyType = "rsa4096"
	ECDSAP256 KeyType = "ecdsaP256"
	ECDSAP384 KeyType = "ecdsaP384"
)

type OutputFormat string

const (
	FormatZIP OutputFormat = "zip"
	FormatPFX OutputFormat = "pfx"
)

type Request struct {
	CommonName   string
	Organization string
	OrgUnit      string
	Country      string
	State        string
	City         string
	Email        string
	ValidityDays int
	KeyType      KeyType
	OutputFormat OutputFormat
	PFXPassword  string
}

type Result struct {
	Data        []byte
	Filename    string
	ContentType string
}

func Generate(req Request) (*Result, error) {
	privKey, pubKey, err := generateKeyPair(req.KeyType)
	if err != nil {
		return nil, fmt.Errorf("generating key pair: %w", err)
	}

	serialNumber, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		return nil, fmt.Errorf("generating serial number: %w", err)
	}

	subject := pkix.Name{
		CommonName: req.CommonName,
	}
	if req.Organization != "" {
		subject.Organization = []string{req.Organization}
	}
	if req.OrgUnit != "" {
		subject.OrganizationalUnit = []string{req.OrgUnit}
	}
	if req.Country != "" {
		subject.Country = []string{req.Country}
	}
	if req.State != "" {
		subject.Province = []string{req.State}
	}
	if req.City != "" {
		subject.Locality = []string{req.City}
	}

	now := time.Now()
	template := &x509.Certificate{
		SerialNumber:          serialNumber,
		Subject:               subject,
		NotBefore:             now,
		NotAfter:              now.AddDate(0, 0, req.ValidityDays),
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth},
		BasicConstraintsValid: true,
		IsCA:                  true,
	}

	if req.Email != "" {
		template.EmailAddresses = []string{req.Email}
	}

	// Add SAN: if CN looks like an IP, add to IPAddresses; otherwise DNSNames
	if ip := net.ParseIP(req.CommonName); ip != nil {
		template.IPAddresses = []net.IP{ip}
	} else {
		template.DNSNames = []string{req.CommonName}
	}

	certDER, err := x509.CreateCertificate(rand.Reader, template, template, pubKey, privKey)
	if err != nil {
		return nil, fmt.Errorf("creating certificate: %w", err)
	}

	cert, err := x509.ParseCertificate(certDER)
	if err != nil {
		return nil, fmt.Errorf("parsing created certificate: %w", err)
	}

	switch req.OutputFormat {
	case FormatPFX:
		return encodePFX(privKey, cert, req.PFXPassword, req.CommonName)
	default:
		return encodeZIP(privKey, certDER, req.CommonName)
	}
}

func generateKeyPair(kt KeyType) (crypto.PrivateKey, crypto.PublicKey, error) {
	switch kt {
	case RSA2048:
		key, err := rsa.GenerateKey(rand.Reader, 2048)
		if err != nil {
			return nil, nil, err
		}
		return key, &key.PublicKey, nil
	case RSA4096:
		key, err := rsa.GenerateKey(rand.Reader, 4096)
		if err != nil {
			return nil, nil, err
		}
		return key, &key.PublicKey, nil
	case ECDSAP256:
		key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			return nil, nil, err
		}
		return key, &key.PublicKey, nil
	case ECDSAP384:
		key, err := ecdsa.GenerateKey(elliptic.P384(), rand.Reader)
		if err != nil {
			return nil, nil, err
		}
		return key, &key.PublicKey, nil
	default:
		return nil, nil, fmt.Errorf("unsupported key type: %s", kt)
	}
}

func encodeZIP(privKey crypto.PrivateKey, certDER []byte, cn string) (*Result, error) {
	keyDER, err := x509.MarshalPKCS8PrivateKey(privKey)
	if err != nil {
		return nil, fmt.Errorf("marshaling private key: %w", err)
	}

	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER})
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyDER})

	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)

	fw, err := zw.Create("certificate.pem")
	if err != nil {
		return nil, fmt.Errorf("creating zip entry: %w", err)
	}
	if _, err := fw.Write(certPEM); err != nil {
		return nil, fmt.Errorf("writing cert to zip: %w", err)
	}

	fw, err = zw.Create("private-key.pem")
	if err != nil {
		return nil, fmt.Errorf("creating zip entry: %w", err)
	}
	if _, err := fw.Write(keyPEM); err != nil {
		return nil, fmt.Errorf("writing key to zip: %w", err)
	}

	if err := zw.Close(); err != nil {
		return nil, fmt.Errorf("closing zip: %w", err)
	}

	filename := sanitizeFilename(cn) + ".zip"
	return &Result{
		Data:        buf.Bytes(),
		Filename:    filename,
		ContentType: "application/zip",
	}, nil
}

func encodePFX(privKey crypto.PrivateKey, cert *x509.Certificate, password, cn string) (*Result, error) {
	pfxData, err := pkcs12.Modern.Encode(privKey, cert, nil, password)
	if err != nil {
		return nil, fmt.Errorf("encoding PFX: %w", err)
	}

	filename := sanitizeFilename(cn) + ".pfx"
	return &Result{
		Data:        pfxData,
		Filename:    filename,
		ContentType: "application/x-pkcs12",
	}, nil
}

func sanitizeFilename(s string) string {
	var out []byte
	for i := 0; i < len(s) && i < 64; i++ {
		c := s[i]
		if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' {
			out = append(out, c)
		} else {
			out = append(out, '_')
		}
	}
	if len(out) == 0 {
		return "certificate"
	}
	return string(out)
}
